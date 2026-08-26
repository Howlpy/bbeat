"""Descarga de audio mediante yt-dlp."""
from __future__ import annotations

import logging
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

# yt-dlp necesita un runtime JS para resolver el desafío de YouTube. Sin él
# cae a un cliente de respaldo cuyas URLs de stream YouTube rechaza a menudo
# con "HTTP Error 403: Forbidden" (visto en lotes de playlists: la mitad de
# las pistas fallaba en <2s). Por defecto yt-dlp solo habilita deno; aquí
# habilitamos también node, que suele estar instalado en el servidor.
JS_RUNTIMES = {"deno": {}, "node": {}}
# Reintentos ante 403 en la descarga directa: es intermitente por URL, un
# reintento con URL fresca suele funcionar.
DIRECT_MAX_ATTEMPTS = 3
DIRECT_RETRY_BACKOFF_S = (2, 5)


def _is_forbidden(err: str) -> bool:
    return "403" in err or "Forbidden" in err


def _ytdlp_format_and_pp() -> tuple[str, list[dict]]:
    """Selector de formato + postprocesador de yt-dlp según settings.

    Para opus/ogg:
    - `audio_quality` numérico (96/128/160/320) → recodifica a ESE bitrate
      (más control de tamaño; ligera pérdida al re-encodear).
    - `audio_quality='auto'` → copia el stream Opus nativo de YouTube sin
      recodificar (`-c:a copy`): máxima calidad, sin control de tamaño.
    Para mp3/m4a/flac recodifica al códec pedido.
    """
    fmt = settings.audio_format
    q = settings.audio_quality
    if fmt in ("opus", "ogg"):
        pp = {"key": "FFmpegExtractAudio", "preferredcodec": "opus"}
        if q.isdigit():
            pp["preferredquality"] = q  # fuerza -b:a {q}k (recodifica)
            return "bestaudio/best", [pp]
        return "bestaudio[acodec=opus]/bestaudio/best", [pp]
    return "bestaudio/best", [{"key": "FFmpegExtractAudio", "preferredcodec": fmt}]


@dataclass
class DownloadResult:
    file_path: Optional[Path]
    backend: str
    error: Optional[str] = None
    source_url: Optional[str] = None  # URL del vídeo/track de donde se descargó

    @property
    def success(self) -> bool:
        return self.file_path is not None and self.error is None


def _norm_text(s: str) -> str:
    """Normaliza para comparación: lowercase, SIN ACENTOS, sin signos, espacios
    colapsados. Quitar acentos es clave para que 'reacción'→'reaccion' y casen
    las keywords (antes la ó se volvía espacio y rompía el match)."""
    import re as _re
    import unicodedata

    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Conservar cualquier alfabeto, no solo a-z: con [^a-z0-9 ] un titulo en
    # cirilico ("Дико красивая") quedaba vacio y el solape con el candidato
    # daba 0, de modo que la comparacion de titulos no podia decidir nada.
    s = "".join(c if (c.isalnum() or c.isspace()) else " " for c in s)
    return _re.sub(r"\s+", " ", s).strip()


def _artist_in_text(artist_norm: str, text_norm: str) -> bool:
    """Compara artistas tolerando separadores visuales en nombres de marca.

    Por ejemplo, Spotify usa ``Nadal015`` mientras su canal oficial de
    YouTube figura como ``NADAL 015``. Se mantiene un minimo de cuatro
    caracteres para que la comparacion compacta no acepte siglas ambiguas.
    """
    if not artist_norm or not text_norm:
        return False
    if artist_norm in text_norm:
        return True
    compact_artist = artist_norm.replace(" ", "")
    compact_text = text_norm.replace(" ", "")
    return len(compact_artist) >= 4 and compact_artist in compact_text


# Palabras que aparecen en casi cualquier titulo musical y no identifican la
# cancion. Contarlas como coincidencia inflaba el solape: "Ma Vie (feat. Yay)"
# y "I'm Ballin (feat. Yay)" compartian 'feat' y 'yay', llegaban al 50% exigido
# y una se descargaba encima de la otra.
TITLE_NOISE_WORDS = frozenset({
    "official", "oficial", "video", "videoclip", "audio", "music", "musica",
    "lyric", "lyrics", "letra", "visualizer", "hd", "4k", "prod", "by",
    "feat", "ft", "featuring", "with", "con",
    "the", "a", "de", "la", "el", "y", "x", "vs",
})
# Separadores tras los cuales empieza la lista de invitados EN EL TITULO PEDIDO,
# que Spotify escribe como "Cancion (feat. X)". Solo se recorta ahi: YouTube usa
# el orden contrario ("Artista ft. X - Cancion"), asi que aplicar el mismo corte
# al candidato borraria justo el titulo que hay que comparar.
FEAT_SEPARATORS = (" feat ", " ft ", " featuring ", " with ")


def _title_core(title_norm: str) -> str:
    """Titulo pedido sin la coletilla de featurings."""
    for sep in FEAT_SEPARATORS:
        idx = title_norm.find(sep)
        if idx > 0:
            return title_norm[:idx].strip()
    return title_norm


def _title_tokens(title_norm: str) -> set[str]:
    """Palabras significativas del titulo PEDIDO."""
    return {w for w in _title_core(title_norm).split() if w not in TITLE_NOISE_WORDS}


def _cand_tokens(cand_title_norm: str) -> set[str]:
    """Palabras significativas del titulo del CANDIDATO (sin recortar)."""
    return {w for w in cand_title_norm.split() if w not in TITLE_NOISE_WORDS}


# Numeros romanos que se usan como marca de secuela. Se dejan fuera "i", "v" y
# "x" sueltos porque tambien son palabras corrientes en ingles y espanol.
ROMAN_NUMERALS = {"ii": 2, "iii": 3, "iv": 4, "vi": 6, "vii": 7, "viii": 8, "ix": 9}


def _as_sequel_number(token: Optional[str]) -> Optional[int]:
    """Interpreta un token como marca de secuela, o None.

    Solo cuentan enteros de una o dos cifras: los de cuatro suelen ser el ano
    del videoclip ("Y Que Si No Hay Amor? 2016"), no una entrega.
    """
    if not token:
        return None
    if token.isdigit() and len(token) <= 2:
        return int(token)
    return ROMAN_NUMERALS.get(token)


def _find_subsequence(haystack: list[str], needle: list[str]) -> Optional[int]:
    """Indice donde `needle` aparece seguido dentro de `haystack`."""
    if not needle or len(needle) > len(haystack):
        return None
    for i in range(len(haystack) - len(needle) + 1):
        if haystack[i:i + len(needle)] == needle:
            return i
    return None


def _sequel_mismatch(title_norm: str, cand_title_norm: str) -> bool:
    """True si el candidato es OTRA entrega de la misma serie.

    "Bando Boyz Free" y "Bando Boyz Free 4" son canciones distintas, pero el
    titulo de la primera esta contenida entera en el de la segunda: el solape
    da 100% y encima la secuela puntua mejor por estar en el canal oficial.

    Solo se mira el numero PEGADO al titulo. Los demas numeros de un titulo de
    YouTube casi nunca son secuelas: son volumenes y numeros de pista
    ("[Hijos de la Ruina Vol. 3]", "02. GUERRERO PSICODELICO"). Si el titulo
    pedido no se localiza dentro del candidato no se juzga nada.
    """
    requested = _title_core(title_norm).split()
    if not requested:
        return False
    expected = _as_sequel_number(requested[-1])
    base = requested[:-1] if expected is not None else requested
    if not base:
        return False
    candidate = cand_title_norm.split()
    idx = _find_subsequence(candidate, base)
    if idx is None:
        return False
    tail = idx + len(base)
    following = candidate[tail] if tail < len(candidate) else None
    return _as_sequel_number(following) != expected


def _title_overlap(title_words: set[str], title_norm: str, cand_title_norm: str) -> float:
    """Fraccion del titulo pedido que aparece en el del candidato.

    Ademas del solape por palabras se compara la forma compacta: YouTube
    escribe titulos como hashtag ("#BACKTOTHEFUTURE") y sin esto no casaban
    con "Back to the Future".
    """
    if not title_words:
        return 0.0
    ratio = len(title_words & _cand_tokens(cand_title_norm)) / len(title_words)
    compact_target = _title_core(title_norm).replace(" ", "")
    if len(compact_target) >= 6 and compact_target in cand_title_norm.replace(" ", ""):
        return 1.0
    return ratio


# Keywords que casi nunca son la canción real (reacciones, podcasts, vídeos
# educativos, etc.): penalización dura. En español e inglés, ya sin acentos.
HARD_BAD_KEYWORDS = (
    "reaccion", "reacciona", "reaccionando", "reaction", "react", "reacting",
    "review", "reseña", "resena", "podcast", "entrevista", "interview",
    "explained", "explicacion", "explicado", "analisis", "analysis",
    "documental", "documentary", "trailer", "gameplay", "tutorial",
    "lecture", "conferencia", "clase", "speedrun", "noticias", "news",
)
# Versiones no-originales: penalización media (no descalifican del todo).
SOFT_BAD_KEYWORDS = (
    "cover", "tribute", "instrumental", "karaoke", "lyric video", "lyrics",
    "live", "en vivo", "directo", "concert", "concierto", "acoustic", "acustico",
    "8 hours", "1 hour", "loop", "extended", "sped up", "slowed", "nightcore",
    "mashup",
)

# Versiones distintas de la grabacion pedida. El scoring puede penalizar
# videos con letras o una presentacion visual diferente, pero estas variantes
# cambian el propio audio y no deben aceptarse salvo que Spotify las nombre.
NON_ORIGINAL_VARIANT_KEYWORDS = (
    "cover", "tribute", "instrumental", "karaoke", "live", "en vivo",
    "directo", "concert", "concierto", "acoustic", "acustico", "mashup",
    "remix",
)

# Transformaciones que alteran perceptiblemente el audio original. A diferencia
# de un videoclip/lyrics, nunca son un sustituto válido si Spotify no las pide
# explícitamente en el título.
ALTERED_AUDIO_KEYWORDS = (
    "audio aumentado", "sonido aumentado", "volumen aumentado",
    "bass boosted", "boosted audio", "audio boosted",
    "slowed reverb", "slowed and reverb", "slowed", "reverb", "reverbed",
    "sped up", "speed up", "nightcore", "8d audio", "audio 8d",
    "nueva version", "version nueva", "version extendida",
)


def _score_candidate(
    e: dict, target_secs: float, artist_norm: str, title_norm: str, title_words: set[str]
) -> tuple[float, str]:
    """Puntúa un candidato de YouTube. Menor score = mejor."""
    score = 0.0
    reasons: list[str] = []

    # 1. Duración (1 punto por segundo de diferencia)
    dur = e.get("duration") or 0
    if target_secs and dur > 0:
        d_diff = abs(dur - target_secs)
        score += d_diff
        if d_diff <= 3:
            reasons.append(f"dur✓({d_diff:.0f}s)")
        elif d_diff > 15:
            score += 20
    else:
        score += 50

    uploader = _norm_text(e.get("uploader") or e.get("channel") or "")
    cand_title = _norm_text(e.get("title") or "")
    artist_in_uploader = _artist_in_text(artist_norm, uploader)
    artist_in_title = _artist_in_text(artist_norm, cand_title)

    # 2. Canal oficial "- Topic" / artista en el canal
    if "- topic" in uploader or " topic" in uploader:
        score -= 40
        reasons.append("topic")
    if artist_in_uploader:
        score -= 25
        reasons.append("artist✓")

    # 3. Keywords malas (solo si NO están en el título original de la pista)
    for kw in HARD_BAD_KEYWORDS:
        if kw in cand_title and kw not in title_norm:
            score += 150
            reasons.append(f"-{kw}!")
            break
    for kw in SOFT_BAD_KEYWORDS:
        if kw in cand_title and kw not in title_norm:
            score += 35
            reasons.append(f"-{kw}")

    # 4. Solape de palabras del título
    overlap = _title_overlap(title_words, title_norm, cand_title)
    score -= overlap * 20
    if overlap >= 0.8:
        reasons.append("title✓")
    elif overlap < 0.34:
        score += 40
        reasons.append("title✗")

    # 5. Ni el artista ni apenas el título aparecen → probablemente no tiene que ver
    if not artist_in_uploader and not artist_in_title and overlap < 0.5:
        score += 30
        reasons.append("noartist")

    return score, ",".join(reasons)


def _candidate_matches(
    e: dict,
    target_secs: float,
    artist_norm: str,
    title_norm: str,
    title_words: set[str],
) -> bool:
    """Exige una coincidencia real antes de permitir una descarga.

    El scoring sirve para ordenar candidatos válidos, no para convertir un
    resultado sin relación en una coincidencia. Título y artista son
    obligatorios; la duración, cuando existe, debe ser razonablemente cercana.
    """
    cand_title = _norm_text(e.get("title") or "")
    uploader = _norm_text(e.get("uploader") or e.get("channel") or "")
    overlap = _title_overlap(title_words, title_norm, cand_title)
    artist_in_uploader = _artist_in_text(artist_norm, uploader)
    artist_matches = bool(artist_in_uploader or _artist_in_text(artist_norm, cand_title))

    if any(kw in cand_title and kw not in title_norm for kw in HARD_BAD_KEYWORDS):
        return False
    if any(kw in cand_title and kw not in title_norm for kw in ALTERED_AUDIO_KEYWORDS):
        return False
    if any(
        f" {kw} " in f" {cand_title} " and f" {kw} " not in f" {title_norm} "
        for kw in NON_ORIGINAL_VARIANT_KEYWORDS
    ):
        return False

    duration = e.get("duration") or 0
    if target_secs and duration:
        tolerance = max(20.0, target_secs * 0.08)
        if abs(duration - target_secs) > tolerance:
            return False

    # Un solape del 50% puede apoyarse en una palabra sin valor: "No Mercy" y
    # "No Hard Feelings" comparten "no"; "4 DÍAS" y "Bando Boyz Free 4"
    # comparten "4"; "GANG LIFE" y "LOCO ft. Dark Polo Gang" comparten "gang".
    # Se exige que lo compartido sume texto suficiente para identificar algo,
    # salvo que el título pedido aparezca entero en el del candidato.
    # Una secuela contiene el titulo del original entero ("Bando Boyz Free" ⊂
    # "Bando Boyz Free 4"), asi que el solape da 100% y encima la secuela suele
    # puntuar mejor por estar en el canal oficial. Los numeros los separan.
    if _sequel_mismatch(title_norm, cand_title):
        return False

    shared = title_words & _cand_tokens(cand_title)
    distinctive = overlap >= 0.999 or sum(len(w) for w in shared) >= 6

    # El título es obligatorio. Existió una excepción que aceptaba cualquier
    # vídeo del canal del artista si la duración caía dentro de un 4%, pensada
    # para títulos localizados ("PIERDO EL CONTROL" → "I LOSE CONTROL"). Medida
    # sobre la biblioteca real aceptó 27 descargas y 19 eran de OTRA canción del
    # mismo artista que casualmente duraba parecido: entre 30 temas de alguien
    # casi siempre hay uno. Un fallo de descarga es visible y el usuario puede
    # pegar la URL exacta; un audio equivocado no se nota hasta meses después.
    return overlap >= 0.5 and artist_matches and distinctive


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
        "js_runtimes": JS_RUNTIMES,
    }
    artist_norm = _norm_text(meta.primary_artist)
    title_norm = _norm_text(meta.title)
    title_words = _title_tokens(title_norm)
    target_secs = meta.duration_ms / 1000 if meta.duration_ms else 0
    entries: list[tuple[dict, str]] = []
    resolve_errors: list[str] = []

    searches = [
        ("YouTube exacta", "youtube", f"ytsearch8:{meta.search_query}"),
        # Algunas ediciones de album solo aparecen en los canales oficiales
        # autogenerados (Topic), mientras la busqueda normal prioriza el
        # videoclip, que puede tener una duracion distinta. Pedir Topic de
        # forma explicita recupera la version exacta sin relajar los filtros de
        # artista, titulo o duracion que evitan falsos positivos.
        (
            "YouTube Topic",
            "youtube",
            f"ytsearch12:{meta.primary_artist} {meta.title} Topic",
        ),
        (
            "YouTube ampliada",
            "youtube",
            f"ytsearch30:{meta.primary_artist} canciones {meta.title}",
        ),
        # NO añadir aquí una búsqueda solo por artista (`ytsearch30:{artista}`):
        # devuelve 30 temas suyos sin relación con el que se pide y era la
        # munición que alimentaba las coincidencias cruzadas. Toda consulta
        # debe llevar el título.
        ("SoundCloud", "soundcloud", f"scsearch20:{meta.search_query}"),
    ]
    for label, provider, query in searches:
        try:
            with YoutubeDL(resolve_opts) as ydl:
                info = ydl.extract_info(query, download=False)
        except Exception as e:
            resolve_errors.append(f"{label}: {str(e)[:200]}")
            log.warning("búsqueda %s falló: %s", label, str(e)[:200])
            continue

        found = [e for e in ((info or {}).get("entries") or []) if e]
        found = [
            e
            for e in found
            if _candidate_matches(
                e, target_secs, artist_norm, title_norm, title_words
            )
        ]
        if found:
            entries = [(e, provider) for e in found]
            log.info("%s: %d candidatos fiables", label, len(found))
            break

    if not entries:
        if resolve_errors:
            return DownloadResult(None, "yt-dlp", f"resolve: {resolve_errors[-1][:400]}")
        return DownloadResult(
            None,
            "yt-dlp",
            "sin coincidencias fiables en YouTube ni SoundCloud",
        )

    # Scoring multi-factor: cuanto menor el score, mejor candidato.
    scored: list[tuple[float, dict, str, str]] = []
    for e, provider in entries:
        score, reasons = _score_candidate(e, target_secs, artist_norm, title_norm, title_words)
        scored.append((score, e, reasons, provider))

    scored.sort(key=lambda x: x[0])
    log.info("yt-dlp: %d candidatos", len(scored))
    for rank, (s, e, r, provider) in enumerate(scored[:5], 1):
        log.info(
            "  #%d %s score=%+.1f %s · %s",
            rank,
            provider,
            s,
            r,
            (e.get("title") or "")[:60],
        )

    # ─── Pasada 2: descargar candidato a candidato hasta que uno funcione ───
    out_tmpl = str(out_dir / f"ytdlp-{meta.spotify_id}.%(ext)s")
    fmt_selector, postprocessors = _ytdlp_format_and_pp()
    download_opts = {
        "format": fmt_selector,
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": postprocessors,
        "concurrent_fragment_downloads": 1,
        "socket_timeout": 30,
        "extractor_args": {"youtube": {"player_client": ["web", "android"]}},
        "js_runtimes": JS_RUNTIMES,
    }
    hook = _build_ytdlp_progress_hook(progress_cb)
    if hook:
        download_opts["progress_hooks"] = [hook]

    last_err: Optional[str] = None
    for sc, cand, _, provider in scored[:5]:  # probamos hasta 5
        video_url = cand.get("webpage_url") or cand.get("url")
        cand_id = cand.get("id", "?")
        if provider == "youtube" and not video_url and cand_id and cand_id != "?":
            video_url = f"https://www.youtube.com/watch?v={cand_id}"
        if not video_url:
            continue
        log.info("descarga intento %s (score %+.1f)", cand_id, sc)
        try:
            with YoutubeDL(download_opts) as ydl:
                ydl.download([video_url])
            audio = [
                p
                for p in sorted(out_dir.glob(f"ytdlp-{meta.spotify_id}.*"))
                if p.suffix.lower() in AUDIO_EXTS
            ]
            if audio:
                return DownloadResult(audio[0], "yt-dlp", source_url=video_url)
            last_err = "no audio output"
        except Exception as e:
            last_err = str(e)[:300]
            if provider == "soundcloud" and "DRM protected" in last_err:
                last_err = (
                    "SoundCloud encontró la canción exacta, pero está protegida "
                    "por DRM y no permite descargarla"
                )
            log.warning("candidato %s falló: %s", cand_id, last_err)
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

    fmt_selector, postprocessors = _ytdlp_format_and_pp()
    opts = {
        "format": fmt_selector,
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": postprocessors,
        "concurrent_fragment_downloads": 1,
        "socket_timeout": 30,
        "js_runtimes": JS_RUNTIMES,
    }
    hook = _build_ytdlp_progress_hook(progress_cb)
    if hook:
        opts["progress_hooks"] = [hook]

    target_url = meta.source_url
    log.info("yt-dlp directo ▶ %s", target_url)
    if progress_cb:
        progress_cb(0, "preparando")
    last_err = ""
    for attempt in range(1, DIRECT_MAX_ATTEMPTS + 1):
        try:
            with YoutubeDL(opts) as ydl:
                ydl.download([target_url])
            last_err = ""
            break
        except Exception as e:
            last_err = str(e)[:400]
            for p in out_dir.glob(f"direct-{safe_id}.*"):
                try:
                    p.unlink()
                except OSError:
                    pass
            if not _is_forbidden(last_err) or attempt == DIRECT_MAX_ATTEMPTS:
                break
            wait = DIRECT_RETRY_BACKOFF_S[min(attempt - 1, len(DIRECT_RETRY_BACKOFF_S) - 1)]
            log.warning(
                "yt-dlp directo 403 en %s (intento %d/%d), reintento en %ds",
                target_url, attempt, DIRECT_MAX_ATTEMPTS, wait,
            )
            if progress_cb:
                progress_cb(0, f"reintentando ({attempt + 1}/{DIRECT_MAX_ATTEMPTS})")
            time.sleep(wait)
    if last_err:
        return DownloadResult(None, "yt-dlp", f"direct: {last_err}")

    candidates = sorted(out_dir.glob(f"direct-{safe_id}.*"))
    audio = [p for p in candidates if p.suffix.lower() in AUDIO_EXTS]
    if not audio:
        return DownloadResult(None, "yt-dlp", "no audio output tras descarga directa")
    return DownloadResult(audio[0], "yt-dlp", source_url=target_url)


# ─── Estrategia: dispatch por fuente ───────────────────────────


def download(
    meta: TrackMeta, progress_cb: Optional[ProgressCb] = None
) -> DownloadResult:
    """Descarga directamente URLs de YouTube/SoundCloud o busca en YouTube
    cuando la pista procede de Spotify.
    """
    sid = meta.spotify_id or ""
    if sid.startswith("yt:") or sid.startswith("sc:"):
        return download_with_ytdlp_direct(meta, progress_cb)
    return download_with_ytdlp(meta, progress_cb)
