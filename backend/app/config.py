from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field("0.0.0.0", alias="BBEAT_HOST")
    port: int = Field(8787, alias="BBEAT_PORT")
    debug: bool = Field(False, alias="BBEAT_DEBUG")

    data_dir: Path = Field(BACKEND_ROOT.parent / "data", alias="BBEAT_DATA_DIR")
    music_dir: Path = Field(BACKEND_ROOT.parent / "data" / "music", alias="BBEAT_MUSIC_DIR")
    covers_dir: Path = Field(BACKEND_ROOT.parent / "data" / "covers", alias="BBEAT_COVERS_DIR")
    secrets_dir: Path = Field(BACKEND_ROOT.parent / "data" / "secrets", alias="BBEAT_SECRETS_DIR")
    db_path: Path = Field(BACKEND_ROOT.parent / "data" / "library.db", alias="BBEAT_DB_PATH")

    # Deprecated: ya no se usan. Se mantienen como opcionales por compatibilidad
    # con .env antiguos. Bbeat ahora resuelve metadata vía SpotifyScraper (sin auth).
    spotify_client_id: str = Field("", alias="SPOTIFY_CLIENT_ID")
    spotify_client_secret: str = Field("", alias="SPOTIFY_CLIENT_SECRET")

    download_backend: Literal["votify", "yt-dlp"] = Field("votify", alias="BBEAT_DOWNLOAD_BACKEND")
    audio_format: Literal["ogg", "mp3", "flac"] = Field("ogg", alias="BBEAT_AUDIO_FORMAT")
    audio_quality: str = Field("auto", alias="BBEAT_AUDIO_QUALITY")
    max_concurrent_jobs: int = Field(1, alias="BBEAT_MAX_CONCURRENT_JOBS")
    fallback_ytdlp: bool = Field(True, alias="BBEAT_FALLBACK_YTDLP")

    cors_origins: str = Field("http://localhost:5173", alias="BBEAT_CORS_ORIGINS")

    @property
    def cors_origin_list(self) -> list[str]:
        configured = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        # Orígenes del WebView de la app nativa (Capacitor): Android sirve el
        # frontend desde https://localhost, iOS desde capacitor://localhost.
        # Siempre permitidos para que la APK pueda hablar con la API aunque el
        # .env no los liste.
        native = ["https://localhost", "capacitor://localhost"]
        return list(dict.fromkeys(configured + native))

    @property
    def setup_complete(self) -> bool:
        # SpotifyScraper no requiere credenciales; consideramos el setup completo
        # si los directorios base existen y son escribibles.
        return self.music_dir.exists() and self.data_dir.exists()

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.music_dir, self.covers_dir, self.secrets_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
