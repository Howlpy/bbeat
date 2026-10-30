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

    # Clasificación de géneros con IA (todo opcional; desactivada por defecto).
    # Cualquier proveedor: openai | gemini | anthropic | ollama | none. Ver README.
    ai_provider: str = Field("none", alias="BBEAT_AI_PROVIDER")
    ai_base_url: str = Field("", alias="BBEAT_AI_BASE_URL")
    ai_api_key: str = Field("", alias="BBEAT_AI_API_KEY")
    ai_model: str = Field("", alias="BBEAT_AI_MODEL")
    # Peticiones por minuto al proveedor (conservador: cuotas gratuitas bajas).
    ai_rpm: float = Field(10, alias="BBEAT_AI_RPM")
    ai_timeout: float = Field(60, alias="BBEAT_AI_TIMEOUT")
    # Por debajo de esta confianza la sugerencia va a revisión, no se aplica.
    ai_min_confidence: float = Field(0.75, alias="BBEAT_AI_MIN_CONFIDENCE")
    # Artistas pequeños que se agrupan en una sola petición (ahorra cuota).
    ai_batch_artists: int = Field(5, alias="BBEAT_AI_BATCH_ARTISTS")
    # Búsqueda web como evidencia: searxng | none.
    search_provider: str = Field("none", alias="BBEAT_SEARCH_PROVIDER")
    searxng_url: str = Field("", alias="BBEAT_SEARXNG_URL")
    # Coherencia por artista al importar (funciona sin IA).
    artist_consistency: bool = Field(True, alias="BBEAT_ARTIST_CONSISTENCY")

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
