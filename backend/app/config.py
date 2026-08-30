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
    transcache_dir: Path = Field(BACKEND_ROOT.parent / "data" / "transcache", alias="BBEAT_TRANSCACHE_DIR")
    db_path: Path = Field(BACKEND_ROOT.parent / "data" / "library.db", alias="BBEAT_DB_PATH")

    # opus = preferimos el stream Opus de YouTube y lo copiamos al contenedor
    # (sin recodificar): mínimo tamaño, máxima calidad. Es el default.
    audio_format: Literal["opus", "ogg", "m4a", "mp3", "flac"] = Field("opus", alias="BBEAT_AUDIO_FORMAT")
    audio_quality: str = Field("auto", alias="BBEAT_AUDIO_QUALITY")
    max_concurrent_jobs: int = Field(1, alias="BBEAT_MAX_CONCURRENT_JOBS")
    # Máximo de procesos ffmpeg de transcoding Subsonic simultáneos. Limita el
    # pico de CPU cuando varios clientes piden formatos no cacheados a la vez.
    transcode_concurrency: int = Field(2, alias="BBEAT_TRANSCODE_CONCURRENCY")
    # Tope de la caché de transcoding en disco (MB). Al superarlo se borran los
    # ficheros menos usados recientemente. 0 = sin límite.
    transcache_max_mb: int = Field(1024, alias="BBEAT_TRANSCACHE_MAX_MB")

    cors_origins: str = Field("http://localhost:5173", alias="BBEAT_CORS_ORIGINS")

    # Last.fm: solo lectura de tags para deducir el género. Basta la api_key
    # (el shared secret es para escribir, y no escribimos nada). Sin clave,
    # la resolución de género simplemente se salta esa fuente.
    lastfm_api_key: str = Field("", alias="BBEAT_LASTFM_API_KEY")

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
        for d in (self.data_dir, self.music_dir, self.covers_dir, self.secrets_dir, self.transcache_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
