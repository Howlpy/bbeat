"""Backends de descarga de audio: Votify (primario) + yt-dlp (fallback)."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from yt_dlp import YoutubeDL

from app.config import settings
from app.services.spotify import TrackMeta

log = logging.getLogger("bbeat.downloader")

# Callback que el caller (worker) inyecta para reportar progreso a la BD.
# Recibe (percent: int, stage: str). Es sincrono y debe ser barato (la BD
# se actualiza throttled dentro).
ProgressCb = Callable[[int, str], None]

AUDIO_EXTS = {".ogg", ".opus", ".m4a", ".mp3", ".flac", ".webm", ".aac"}
# Tolerancia generosa: YouTube tiene versiones remix, extendidas, etc.
# Si ninguna pasa el filtro estricto, caemos al "más cercano en duración".
DURATION_TOLERANCE_MS = 15000


@dataclass
class DownloadResult:
    file_path: Optional[Path]
    backend: str
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.file_path is not None and self.error is None


def cookies_path() -> Path:
    return settings.secrets_dir / "spotify_cookies.txt"


def cookies_available() -> bool:
    p = cookies_path()
    return p.exists() and p.stat().st_size > 0


# ─── Votify ─────────────────────────────────────────────────────


def _votify_quality() -> str:
    """Mapea BBEAT_AUDIO_QUALITY a las cadenas que entiende Votify."""
    q = settings.audio_quality
    if q in ("auto", "160"):
        return "vorbis-low"
    if q == "320":
        return "vorbis-high,vorbis-low"  # cae a baja si la cuenta no tiene premium
    if q == "96":
        return "vorbis-low"
    return "vorbis-low"


def download_with_votify(meta: TrackMeta) -> DownloadResult:
    cookies = cookies_path()
    if not cookies_available():
        return DownloadResult(None, "votify", "cookies not configured")

    spotify_url = f"https://open.spotify.com/track/{meta.spotify_id}"

    with tempfile.TemporaryDirectory(prefix="bbeat-votify-") as tmp:
        tmp_dir = Path(tmp)
        cmd = [
            sys.executable,
            "-m",
            "votify",
            "-c",
            str(cookies),
            "-o",
            str(tmp_dir),
            "--audio-quality",
            _votify_quality(),
            "--no-config-file",
            "--no-exceptions",
            "--log-level",
            "WARNING",
            spotify_url,
        ]
        # protobuf C-ext vs librespot 0.0.10 → tenemos que forzar la implementación python
        env = {**os.environ, "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION": "python"}
        log.info("votify ▶ %s", meta.search_query)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
        except subprocess.TimeoutExpired:
            return DownloadResult(None, "votify", "timeout 180s")

        if res.returncode != 0:
            err = (res.stderr or res.stdout or "").strip().splitlines()
            tail = "  ".join(err[-5:])[:500] if err else f"exit {res.returncode}"
            return DownloadResult(None, "votify", tail)

        audio = [p for p in tmp_dir.rglob("*") if p.suffix.lower() in AUDIO_EXTS and p.is_file()]
        if not audio:
            return DownloadResult(None, "votify", "no audio output")

        # Mover fuera del tempdir antes de que se borre
        src = audio[0]
        dst = tmp_dir.parent / f"bbeat-votify-{meta.spotify_id}{src.suffix}"
        shutil.move(str(src), dst)
        return DownloadResult(dst, "votify")


# ─── yt-dlp ────────────────────────────────────────────────────


def download_with_ytdlp(
    meta: TrackMeta, progress_cb: Optional[ProgressCb] = None
) -> DownloadResult:
    """Búsqueda en YouTube en dos pasadas:
    1. Resolver hasta 8 candidatos (con tolerancia a fallos) y ordenarlos por
       cercanía de duración.
    2. Intentar descargar el mejor; si falla por "no disponible" o similar,
       reintenta con el siguiente, etc.
    """
    out_dir = settings.data_dir / "downloads"
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("yt-dlp ▶ %s (objetivo %ds)", meta.search_query, meta.duration_ms // 1000)
    if progress_cb:
        progress_cb(0, "buscando")

    # ─── Pasada 1: extraer info sin descargar ───
    # ignoreerrors=True para que si UN candidato falla, no aborte todo el batch.
    # player_client web+android: si "web" da "not available", "android" suele funcionar.
    resolve_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": "in_playlist",  # solo lista IDs, no metadata profunda (más rápido)
        "default_search": "ytsearch8",
        "socket_timeout": 30,
        "ignoreerrors": True,
        "extractor_args": {"youtube": {"player_client": ["web", "android"]}},
    }
    try:
        with YoutubeDL(resolve_opts) as ydl:
            info = ydl.extract_info(f"ytsearch8:{meta.search_query}", download=False)
    except Exception as e:
        return DownloadResult(None, "yt-dlp", f"resolve: {str(e)[:400]}")

    entries = [e for e in ((info or {}).get("entries") or []) if e]
    if not entries:
        return DownloadResult(None, "yt-dlp", "sin resultados en YouTube")

    # Con extract_flat=in_playlist las entries traen solo {id, title, duration, url}.
    # Eso basta para ordenar por duración. Si duration falta, lo dejamos al final.
    target = meta.duration_ms / 1000 or 0
    scored: list[tuple[float, dict]] = []
    for e in entries:
        dur = e.get("duration") or 0
        # tolerancia "sin duración" → último de la lista
        diff = abs(dur - target) if target and dur > 0 else 1e9
        scored.append((diff, e))

    scored.sort(key=lambda x: x[0])
    log.info("yt-dlp: %d candidatos, intento desde el más cercano…", len(scored))

    # ─── Pasada 2: descargar candidato a candidato hasta que uno funcione ───
    out_tmpl = str(out_dir / f"ytdlp-{meta.spotify_id}.%(ext)s")
    download_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}],
        "concurrent_fragment_downloads": 1,
        "socket_timeout": 30,
        "extractor_args": {"youtube": {"player_client": ["web", "android"]}},
    }
    hook = _build_ytdlp_progress_hook(progress_cb)
    if hook:
        download_opts["progress_hooks"] = [hook]

    last_err: Optional[str] = None
    for diff, cand in scored[:5]:  # probamos hasta 5
        video_url = cand.get("webpage_url") or cand.get("url")
        cand_id = cand.get("id", "?")
        if not video_url and cand_id and cand_id != "?":
            video_url = f"https://www.youtube.com/watch?v={cand_id}"
        if not video_url:
            continue
        if target and diff != 1e9:
            log.info(
                "intento %s (diff %.1fs): %s",
                cand_id,
                diff,
                cand.get("title", "")[:60],
            )
        try:
            with YoutubeDL(download_opts) as ydl:
                ydl.download([video_url])
            audio = [
                p
                for p in sorted(out_dir.glob(f"ytdlp-{meta.spotify_id}.*"))
                if p.suffix.lower() in AUDIO_EXTS
            ]
            if audio:
                return DownloadResult(audio[0], "yt-dlp")
            last_err = "no audio output"
        except Exception as e:
            last_err = str(e)[:300]
            log.warning("candidato %s falló: %s", cand_id, last_err)
            # Limpiar restos parciales del candidato fallido
            for p in out_dir.glob(f"ytdlp-{meta.spotify_id}.*"):
                try:
                    p.unlink()
                except OSError:
                    pass
            continue

    return DownloadResult(
        None,
        "yt-dlp",
        f"todos los candidatos fallaron (último: {last_err or 'desconocido'})",
    )


# ─── yt-dlp directo (para YouTube/SoundCloud, sin búsqueda) ───


def _build_ytdlp_progress_hook(progress_cb: Optional[ProgressCb]):
    """Crea un hook de progreso throttled (max 1 update por segundo)."""
    if progress_cb is None:
        return None
    state = {"last_pct": -1, "last_t": 0.0}

    def hook(d: dict) -> None:
        try:
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes") or 0
                pct = int(done * 100 / total) if total else 0
                pct = max(0, min(99, pct))  # 100 lo dejamos para "finished"
                now = time.monotonic()
                if pct - state["last_pct"] >= 3 or (now - state["last_t"]) >= 0.5:
                    state["last_pct"] = pct
                    state["last_t"] = now
                    progress_cb(pct, "descargando")
            elif status == "finished":
                progress_cb(95, "convirtiendo")
        except Exception:
            pass

    return hook


def download_with_ytdlp_direct(
    meta: TrackMeta, progress_cb: Optional[ProgressCb] = None
) -> DownloadResult:
    """Descarga directa desde meta.source_url, sin buscar.

    Para YouTube/SoundCloud el usuario ya nos dio la URL exacta,
    no hay que adivinar nada.
    """
    out_dir = settings.data_dir / "downloads"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_id = meta.spotify_id.replace(":", "_").replace("/", "_")
    out_tmpl = str(out_dir / f"direct-{safe_id}.%(ext)s")

    opts = {
        "format": "bestaudio/best",
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}],
        "concurrent_fragment_downloads": 1,
        "socket_timeout": 30,
    }
    hook = _build_ytdlp_progress_hook(progress_cb)
    if hook:
        opts["progress_hooks"] = [hook]

    target_url = meta.source_url
    log.info("yt-dlp directo ▶ %s", target_url)
    if progress_cb:
        progress_cb(0, "preparando")
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([target_url])
    except Exception as e:
        return DownloadResult(None, "yt-dlp", f"direct: {str(e)[:400]}")

    candidates = sorted(out_dir.glob(f"direct-{safe_id}.*"))
    audio = [p for p in candidates if p.suffix.lower() in AUDIO_EXTS]
    if not audio:
        return DownloadResult(None, "yt-dlp", "no audio output tras descarga directa")
    return DownloadResult(audio[0], "yt-dlp")


# ─── Estrategia: dispatch por fuente ───────────────────────────


def download(
    meta: TrackMeta, progress_cb: Optional[ProgressCb] = None
) -> DownloadResult:
    """Elige backend según el ID/source.

    - `yt:...` o `sc:...` → descarga directa desde la URL original.
    - Spotify (ID raw) → Votify primario (si hay cookies), fallback yt-dlp por búsqueda.
    """
    sid = meta.spotify_id or ""
    if sid.startswith("yt:") or sid.startswith("sc:"):
        return download_with_ytdlp_direct(meta, progress_cb)

    # Camino Spotify
    primary = settings.download_backend
    tried: list[str] = []

    if primary == "votify":
        r = download_with_votify(meta)
        tried.append(f"votify: {r.error or 'ok'}")
        if r.success:
            return r
        log.warning("votify falló (%s), fallback yt-dlp...", r.error)
        if not settings.fallback_ytdlp:
            r.error = "; ".join(tried)
            return r
        r = download_with_ytdlp(meta, progress_cb)
        tried.append(f"yt-dlp: {r.error or 'ok'}")
        if not r.success:
            r.error = "; ".join(tried)
        return r

    # primary == 'yt-dlp'
    r = download_with_ytdlp(meta, progress_cb)
    if r.success or not settings.fallback_ytdlp:
        return r
    r2 = download_with_votify(meta)
    if r2.success:
        return r2
    r.error = f"yt-dlp: {r.error}; votify: {r2.error}"
    return r
