"""Gestión de credenciales/cookies para los backends de descarga."""
import logging
import os
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services import downloader

log = logging.getLogger("bbeat.auth")

router = APIRouter(prefix="/auth/spotify", tags=["auth"])


@router.get("/status")
def status() -> dict:
    p = downloader.cookies_path()
    info = {
        "cookies_configured": downloader.cookies_available(),
        "cookies_path": str(p),
    }
    if p.exists():
        info["size"] = p.stat().st_size
        info["mtime"] = p.stat().st_mtime
    return info


@router.post("/cookies")
async def upload_cookies(file: UploadFile = File(...)) -> dict:
    dst = downloader.cookies_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()

    if not content or len(content) > 1_000_000:
        raise HTTPException(400, "fichero vacío o demasiado grande")

    text = content.decode("utf-8", errors="ignore")
    # Validación liviana: cabecera Netscape o al menos contiene .spotify.com
    if "spotify.com" not in text.lower():
        raise HTTPException(
            400,
            "no parece un cookies.txt de Spotify (no veo 'spotify.com' en el contenido)",
        )

    dst.write_bytes(content)
    try:
        os.chmod(dst, 0o600)
    except OSError:
        pass
    log.info("cookies subidas: %d bytes", len(content))
    return {"ok": True, "size": len(content)}


@router.delete("/cookies")
def delete_cookies() -> dict:
    p = downloader.cookies_path()
    if p.exists():
        p.unlink()
    return {"ok": True}
