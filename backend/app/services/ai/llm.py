"""Cliente de chat mínimo y agnóstico del proveedor (solo httpx, sin SDKs).

Proveedores (BBEAT_AI_PROVIDER):
  openai     API de OpenAI o CUALQUIER servidor compatible (BBEAT_AI_BASE_URL:
             OpenRouter, Groq, Together, LM Studio, vLLM, Mistral, DeepSeek...)
  gemini     endpoint compatible-OpenAI de Google (mismo código que openai)
  ollama     Ollama local por su endpoint /v1 compatible-OpenAI
  anthropic  API nativa Messages
  none       desactivado (por defecto)

Pide JSON, lo extrae con tolerancia (vallas ```, texto alrededor), lo valida y
reintenta una vez si es inválido. Ante 429/5xx hace backoff exponencial
respetando Retry-After; si la cuota no se recupera lanza QuotaExceeded para que
los procesos por lotes paren y se reanuden más tarde.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx

from app.config import settings

log = logging.getLogger("bbeat.ai.llm")

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULTS: dict[str, tuple[str, str]] = {
    # proveedor: (base_url, modelo)
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "gemini": (GEMINI_BASE, "gemini-2.5-flash-lite"),
    "ollama": ("http://localhost:11434/v1", "llama3.2"),
    "anthropic": ("https://api.anthropic.com", "claude-haiku-4-5"),
}
PROVIDERS = tuple(DEFAULTS) + ("none",)

MAX_RETRIES = 4
BACKOFF_BASE_S = 2.0
BACKOFF_MAX_S = 60.0
# Un Retry-After mayor que esto se considera cuota diaria agotada: no esperamos.
QUOTA_WAIT_LIMIT_S = 120.0


class LLMError(Exception):
    """Fallo del proveedor que no se arregla reintentando."""


class LLMNotConfigured(LLMError):
    pass


class InvalidResponse(LLMError):
    """El modelo no devolvió un JSON válido según el esquema."""


class QuotaExceeded(LLMError):
    """Cuota/límite agotado: parar y reanudar más tarde."""

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class LLMConfig:
    provider: str = "none"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    rpm: float = 10.0
    timeout: float = 60.0

    @classmethod
    def from_settings(cls) -> "LLMConfig":
        provider = (settings.ai_provider or "none").strip().lower()
        base, model = DEFAULTS.get(provider, ("", ""))
        return cls(
            provider=provider,
            base_url=(settings.ai_base_url or base).strip().rstrip("/"),
            api_key=settings.ai_api_key.strip(),
            model=(settings.ai_model or model).strip(),
            rpm=float(settings.ai_rpm),
            timeout=float(settings.ai_timeout),
        )

    @property
    def enabled(self) -> bool:
        if self.provider not in DEFAULTS:
            return False
        # Ollama y los servidores locales no necesitan clave.
        needs_key = self.provider in ("gemini", "anthropic") or (
            self.provider == "openai" and "api.openai.com" in self.base_url
        )
        return bool(self.model and self.base_url and (self.api_key or not needs_key))


# ─── Extracción y validación de JSON ─────────────────────────────


def extract_json(text: str) -> Any:
    """Primer objeto/array JSON de un texto, tolerando vallas y charla extra."""
    if not isinstance(text, str) or not text.strip():
        raise InvalidResponse("respuesta vacía")
    t = text.strip()
    t = re.sub(r"^```[a-zA-Z0-9]*\s*|\s*```$", "", t).strip()
    dec = json.JSONDecoder()
    for m in re.finditer(r"[\{\[]", t):
        try:
            obj, _ = dec.raw_decode(t[m.start():])
        except ValueError:
            continue
        return obj
    raise InvalidResponse("no hay JSON en la respuesta")


def _retry_after(resp: httpx.Response) -> Optional[float]:
    """Segundos de espera pedidos por el servidor (cabecera o cuerpo de Gemini)."""
    h = resp.headers.get("retry-after")
    if h:
        try:
            return max(0.0, float(h))
        except ValueError:
            pass
    m = re.search(r'"retryDelay"\s*:\s*"([\d.]+)s"', resp.text or "")
    if m:
        return float(m.group(1))
    return None


def _looks_daily(resp: httpx.Response) -> bool:
    body = (resp.text or "").lower()
    return any(k in body for k in ("per day", "perday", "daily", "insufficient_quota", "billing"))


# ─── Cliente ─────────────────────────────────────────────────────


class LLMClient:
    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        *,
        transport: Optional[httpx.BaseTransport] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.cfg = config or LLMConfig.from_settings()
        self._http = httpx.Client(timeout=self.cfg.timeout, transport=transport)
        self._sleep = sleep
        self._clock = clock
        self._last = None  # instante de la última petición (para el RPM)
        self._json_mode = True
        self.requests = 0  # peticiones HTTP enviadas (para informes)

    # --- ritmo ---

    def _throttle(self) -> None:
        if self.cfg.rpm <= 0:
            return
        gap = 60.0 / self.cfg.rpm
        now = self._clock()
        if self._last is not None and now - self._last < gap:
            self._sleep(gap - (now - self._last))
        self._last = self._clock()

    # --- transporte ---

    def _build(self, system: str, messages: list[dict]) -> tuple[str, dict, dict]:
        c = self.cfg
        if c.provider == "anthropic":
            url = f"{c.base_url}/v1/messages"
            headers = {
                "x-api-key": c.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            body = {"model": c.model, "max_tokens": 4096, "temperature": 0,
                    "system": system, "messages": messages}
        else:
            url = f"{c.base_url}/chat/completions"
            headers = {"content-type": "application/json"}
            if c.api_key:
                headers["authorization"] = f"Bearer {c.api_key}"
            body = {"model": c.model, "temperature": 0,
                    "messages": [{"role": "system", "content": system}, *messages]}
            if self._json_mode:
                body["response_format"] = {"type": "json_object"}
        return url, headers, body

    @staticmethod
    def _text(provider: str, data: dict) -> str:
        try:
            if provider == "anthropic":
                return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise InvalidResponse("estructura de respuesta inesperada")

    def _post(self, system: str, messages: list[dict]) -> str:
        """Una petición con backoff. Devuelve el texto de la respuesta."""
        attempt = 0
        while True:
            self._throttle()
            url, headers, body = self._build(system, messages)
            self.requests += 1
            try:
                resp = self._http.post(url, headers=headers, json=body)
            except httpx.HTTPError as e:
                resp = None
                err = f"red: {e.__class__.__name__}"
            else:
                err = f"HTTP {resp.status_code}"

            if resp is not None and resp.status_code < 400:
                try:
                    return self._text(self.cfg.provider, resp.json())
                except ValueError:
                    raise InvalidResponse("respuesta no es JSON")

            status = resp.status_code if resp is not None else 0
            # Algunos servidores compatibles no admiten response_format.
            if status in (400, 422) and self._json_mode and self.cfg.provider != "anthropic":
                self._json_mode = False
                continue
            if status in (401, 403):
                raise LLMError(f"proveedor rechazó la clave o el acceso ({err})")
            if status == 404:
                raise LLMError(f"modelo o URL no encontrados ({err}): revisa BBEAT_AI_MODEL/BASE_URL")
            if status == 429 or status >= 500 or resp is None:
                wait = _retry_after(resp) if resp is not None else None
                if status == 429 and (
                    (wait is not None and wait > QUOTA_WAIT_LIMIT_S) or _looks_daily(resp)
                ):
                    raise QuotaExceeded("cuota agotada en el proveedor", wait)
                attempt += 1
                if attempt > MAX_RETRIES:
                    if status == 429:
                        raise QuotaExceeded("límite de peticiones sostenido (429)", wait)
                    raise LLMError(f"el proveedor sigue fallando ({err})")
                delay = wait if wait is not None else min(BACKOFF_BASE_S * 2 ** (attempt - 1), BACKOFF_MAX_S)
                log.warning("ia: %s, reintento %d/%d en %.0fs", err, attempt, MAX_RETRIES, delay)
                self._sleep(delay)
                continue
            detail = (resp.text or "")[:200] if resp is not None else ""
            raise LLMError(f"error del proveedor ({err}): {detail}")

    # --- API pública ---

    def chat_json(
        self,
        system: str,
        user: str,
        validate: Optional[Callable[[Any], Any]] = None,
    ) -> Any:
        """Pide JSON, lo extrae y valida; reintenta UNA vez si es inválido.

        `validate` recibe el JSON y devuelve el valor final o lanza ValueError.
        """
        if not self.cfg.enabled:
            raise LLMNotConfigured("IA no configurada (BBEAT_AI_PROVIDER / modelo / clave)")
        messages = [{"role": "user", "content": user}]
        last: Optional[Exception] = None
        for intento in range(2):
            text = self._post(system, messages)
            try:
                data = extract_json(text)
                return validate(data) if validate else data
            except (InvalidResponse, ValueError) as e:
                last = e
                log.warning("ia: respuesta inválida (%s)", e)
                messages = [
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": text[:2000]},
                    {"role": "user", "content": (
                        f"Tu respuesta no es válida ({e}). Responde SOLO con el objeto JSON "
                        "pedido, sin texto ni vallas de código."
                    )},
                ]
        raise InvalidResponse(str(last))

    def close(self) -> None:
        self._http.close()
