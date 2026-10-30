"""Cola de importación compartida: todos ven todo, con quién lo lanzó."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, delete

from app.api import jobs as jobs_api
from app.db import engine, init_db
from app.models import Job, Play, User
from app.services import auth as auth_svc


@pytest.fixture()
def env():
    init_db()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for model in (Job, Play, User):
            s.exec(delete(model))
        s.commit()
        ana = User(username="ana", email="a@x.com", password_hash="x", is_approved=True)
        luis = User(username="luis", email="l@x.com", password_hash="x", is_approved=True)
        s.add_all([ana, luis])
        s.commit()
        s.refresh(ana)
        s.refresh(luis)
        s.add(Job(source_url="u1", spotify_track_id="a", title="de ana", user_id=ana.id, status="failed"))
        s.add(Job(source_url="u2", spotify_track_id="b", title="de luis", user_id=luis.id))
        s.add(Job(source_url="u3", spotify_track_id="c", title="viejo"))
        s.commit()
        ids = {j.title: j.id for j in s.exec(__import__("sqlmodel").select(Job)).all()}
        app = FastAPI()
        app.include_router(jobs_api.router, prefix="/api")
        app.dependency_overrides[auth_svc.get_current_user] = lambda: ana
        yield TestClient(app), ids
        # Limpieza: otras suites borran users y no deben chocar con nuestros jobs.
        s.exec(delete(Job))
        s.exec(delete(User))
        s.commit()


def test_lista_todos_con_username(env):
    client, _ = env
    data = client.get("/api/jobs").json()
    by_title = {j["title"]: j["username"] for j in data["items"]}
    assert by_title == {"de ana": "ana", "de luis": "luis", "viejo": None}
    assert data["stats"]["total"] == 1  # lo propio
    assert data["stats_all"]["total"] == 3


def test_acciones_solo_del_dueno(env):
    client, ids = env
    assert client.delete(f"/api/jobs/{ids['de luis']}").status_code == 403
    assert client.post(f"/api/jobs/{ids['de ana']}/retry").status_code == 200
