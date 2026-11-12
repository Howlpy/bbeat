"""Un error no controlado debe llegar a la app como 500 con cabeceras CORS."""
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import create_app


def _boom():
    raise RuntimeError("fallo")


def test_unhandled_error_returns_500_with_cors_headers():
    app = create_app()
    app.router.routes.insert(0, APIRoute("/api/__boom", _boom, methods=["DELETE"]))
    client = TestClient(app, raise_server_exceptions=False)

    res = client.delete("/api/__boom", headers={"Origin": "https://localhost"})

    assert res.status_code == 500
    assert res.headers.get("access-control-allow-origin") == "https://localhost"
    assert res.json() == {"detail": "error interno del servidor"}
