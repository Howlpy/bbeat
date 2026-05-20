from fastapi import APIRouter

from app import __version__
from app.config import settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "setup_complete": settings.setup_complete,
    }


@router.get("/setup/status")
def setup_status() -> dict:
    return {
        "setup_complete": settings.setup_complete,
        "checks": {
            "spotify_client_id": bool(settings.spotify_client_id),
            "spotify_client_secret": bool(settings.spotify_client_secret),
            "music_dir_exists": settings.music_dir.exists(),
            "music_dir_writable": settings.music_dir.exists()
            and settings.music_dir.is_dir(),
        },
    }
