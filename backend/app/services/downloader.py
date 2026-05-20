"""Backends de descarga de audio: Votify (primario) + yt-dlp (fallback)."""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from yt_dlp import YoutubeDL

from app.config import settings
from app.services.spotify import TrackMeta

log = logging.getLogger("bbeat.downloader")

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
        log.info("votify ▶ %s", meta.search_query)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
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


def download_with_ytdlp(meta: TrackMeta) -> DownloadResult:
    """Búsqueda en YouTube en dos pasadas:
    1. Resolver 5 candidatos sin descargar y elegir el más cercano en duración.
    2. Descargar el ganador con extracción de audio.
    Esto evita rechazar todo cuando ninguno cae en ±15s.
    """
    out_dir = settings.data_dir / "downloads"
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("yt-dlp ▶ %s (objetivo %ds)", meta.search_query, meta.duration_ms // 1000)

    # ─── Pasada 1: extraer info sin descargar ───
    resolve_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
        "default_search": "ytsearch5",
        "socket_timeout": 30,
    }
    try:
        with YoutubeDL(resolve_opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{meta.search_query}", download=False)
    except Exception as e:
        return DownloadResult(None, "yt-dlp", f"resolve: {str(e)[:400]}")

    entries = (info or {}).get("entries") or []
    if not entries:
        return DownloadResult(None, "yt-dlp", "sin resultados en YouTube")

    target = meta.duration_ms / 1000 or 0
    scored: list[tuple[float, dict]] = []
    for e in entries:
        if not e:
            continue
        dur = e.get("duration") or 0
        if dur <= 0:
            continue
        # Penalizar fuertemente vídeos largos (mezclas) y muy cortos (clips)
        diff = abs(dur - target) if target else 9999
        scored.append((diff, e))

    if not scored:
        return DownloadResult(None, "yt-dlp", "sin candidatos con duración")

    scored.sort(key=lambda x: x[0])
    best_diff, best = scored[0]
    if target and best_diff > DURATION_TOLERANCE_MS / 1000:
        log.warning(
            "yt-dlp: mejor match a %.1fs del objetivo (>%ds tolerancia). Lo cojo igual.",
            best_diff,
            DURATION_TOLERANCE_MS // 1000,
        )

    video_url = best.get("webpage_url") or best.get("url")
    if not video_url:
        return DownloadResult(None, "yt-dlp", "sin URL en el candidato ganador")

    # ─── Pasada 2: descargar el ganador ───
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
    }
    try:
        with YoutubeDL(download_opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        return DownloadResult(None, "yt-dlp", f"download: {str(e)[:400]}")

    candidates = sorted(out_dir.glob(f"ytdlp-{meta.spotify_id}.*"))
    audio = [p for p in candidates if p.suffix.lower() in AUDIO_EXTS]
    if not audio:
        return DownloadResult(None, "yt-dlp", "no audio output tras descarga")
    return DownloadResult(audio[0], "yt-dlp")


# ─── Estrategia: primario + fallback ───────────────────────────


def download(meta: TrackMeta) -> DownloadResult:
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
        r = download_with_ytdlp(meta)
        tried.append(f"yt-dlp: {r.error or 'ok'}")
        if not r.success:
            r.error = "; ".join(tried)
        return r

    # primary == 'yt-dlp'
    r = download_with_ytdlp(meta)
    if r.success or not settings.fallback_ytdlp:
        return r
    r2 = download_with_votify(meta)
    if r2.success:
        return r2
    r.error = f"yt-dlp: {r.error}; votify: {r2.error}"
    return r
