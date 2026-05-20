import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health
from app.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
)
log = logging.getLogger("bbeat")


def create_app() -> FastAPI:
    settings.ensure_dirs()

    app = FastAPI(
        title="Bbeat",
        description="Self-hosted personal music server",
        version=__version__,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")

    @app.on_event("startup")
    async def _startup() -> None:
        log.info("Bbeat %s arrancando en %s:%s", __version__, settings.host, settings.port)
        log.info("Setup wizard %s", "PENDIENTE" if not settings.setup_complete else "COMPLETO")
        log.info("Música en %s", settings.music_dir)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
