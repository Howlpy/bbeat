import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import auth, health, ingest, jobs, library, stream
from app.api import subsonic
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
    # Comprime HTML/JS/CSS/JSON de respuesta (no toca audio/imágenes, ya
    # comprimidos). Alivia el ancho de banda del frontend en una conexión casera.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    app.include_router(health.router, prefix="/api")
    app.include_router(users_api.router, prefix="/api")
    app.include_router(users_api.admin_router, prefix="/api")
    app.include_router(library.router, prefix="/api")
    app.include_router(stream.router, prefix="/api")
    app.include_router(ingest.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    # API Subsonic: va en /rest (sin /api). Debe registrarse ANTES del catch-all
    # del SPA, o las peticiones /rest/* las absorbería el fallback de index.html.
    app.include_router(subsonic.router)

    # ─── Servir frontend estático (modo prod) ────────────────────
    # En dev (Vite), no existe el build y este mount no se monta.
    build_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "build"
    if build_dir.is_dir():
        log.info("Sirvo frontend desde %s", build_dir)
        # Recursos del build (JS, CSS, assets)
        app.mount("/_app", StaticFiles(directory=str(build_dir / "_app")), name="static_app")

        # Catch-all para SPA: cualquier path no-API devuelve el fichero
        # estático correspondiente, o index.html para deep links.
        index_html = build_dir / "index.html"
        build_root = build_dir.resolve()

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str, request: Request):
            # Las rutas /api/* ya están registradas arriba, no llegamos aquí.
            if full_path:
                # CONTENCIÓN: resolver y exigir que el fichero quede DENTRO del
                # build. Sin esto, '..%2f..' (o '../') se sirve fuera de build/
                # y filtra .env, claves JWT, etc. — path traversal crítico.
                candidate = (build_dir / full_path).resolve()
                try:
                    candidate.relative_to(build_root)
                except ValueError:
                    return FileResponse(index_html)
                if candidate.is_file():
                    return FileResponse(candidate)
                # Un path con pinta de fichero (tiene extensión) que no existe es
                # un 404 real, no el SPA: así los escáneres que piden /admin/config.php
                # reciben 404 en vez de un 200 con el index.
                if "." in Path(full_path).name:
                    return FileResponse(index_html, status_code=404)
            return FileResponse(index_html)
    else:
        log.info("Sin build de frontend (modo dev). Usa npm run dev para servirlo.")

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
