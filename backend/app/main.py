import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import auth, health, ingest, jobs, library, stream
from app.api import users as users_api
from app.config import settings
from app.db import init_db
from app.services import jobs as jobs_svc

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
)
log = logging.getLogger("bbeat")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_db()
    log.info("Bbeat %s arrancando en %s:%s", __version__, settings.host, settings.port)
    log.info("Setup wizard %s", "PENDIENTE" if not settings.setup_complete else "COMPLETO")
    log.info("Música en %s", settings.music_dir)
    jobs_svc.start_worker()
    yield
    log.info("Bbeat parando")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Bbeat",
        description="Self-hosted personal music server",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(users_api.router, prefix="/api")
    app.include_router(users_api.admin_router, prefix="/api")
    app.include_router(library.router, prefix="/api")
    app.include_router(stream.router, prefix="/api")
    app.include_router(ingest.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")

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
