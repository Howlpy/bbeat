"""Listas semanales por género: ranking, ventana, umbral y límite."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, delete

from app.api import library
from app.db import engine, init_db
from app.models import Artist, Play, Track, User
from app.services import auth as auth_svc

NOW = datetime.utcnow()


@pytest.fixture()
def db():
    init_db()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for model in (Play, Track, Artist, User):
            s.exec(delete(model))
        s.commit()
        artist = Artist(name="A", name_normalized="a")
        s.add(artist)
        users = [
            User(username=f"u{i}", email=f"u{i}@x.com", password_hash="x", is_approved=True)
            for i in range(4)
        ]
        s.add_all(users)
        s.commit()
        yield s, artist, users


@pytest.fixture()
def client(db):
    _, _, users = db
    app = FastAPI()
    app.include_router(library.router, prefix="/api")
    app.dependency_overrides[auth_svc.get_current_user] = lambda: users[0]
    return TestClient(app)


def _track(s, artist, n, genre="rap"):
    t = Track(title=f"t{n}", artist_id=artist.id, genre=genre, file_path=f"/m/{genre}-{n}.mp3")
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


def _play(s, user, track, times=1, ago=timedelta(hours=1)):
    for _ in range(times):
        s.add(Play(user_id=user.id, track_id=track.id, played_at=NOW - ago))
    s.commit()


def _rap_genre(s, artist, users, count=5):
    """`count` pistas de rap, cada una escuchada una vez por users[0]."""
    ts = [_track(s, artist, i) for i in range(count)]
    for t in ts:
        _play(s, users[0], t)
    return ts


def test_oyentes_distintos_ganan_a_plays_en_bucle(db, client):
    s, artist, users = db
    ts = _rap_genre(s, artist, users)
    bucle, popular = ts[0], ts[1]
    _play(s, users[0], bucle, times=20)
    for u in users[1:4]:
        _play(s, u, popular)
    items = client.get("/api/library/charts/rap").json()["items"]
    assert items[0]["id"] == popular.id and items[0]["listeners"] == 4
    assert items[1]["id"] == bucle.id and items[1]["plays"] == 21
    assert [i["rank"] for i in items] == [1, 2, 3, 4, 5]


def test_ventana_excluye_plays_antiguos(db, client):
    s, artist, users = db
    ts = _rap_genre(s, artist, users)
    _play(s, users[1], ts[4], times=10, ago=timedelta(days=9))
    items = client.get("/api/library/charts/rap?days=7").json()["items"]
    assert items[-1]["id"] == ts[4].id and items[-1]["plays"] == 1
    # Con ventana de 30 días sí cuentan.
    wide = client.get("/api/library/charts/rap?days=30").json()["items"]
    assert wide[0]["id"] == ts[4].id


def test_umbral_de_pistas_por_genero(db, client):
    s, artist, users = db
    _rap_genre(s, artist, users, count=5)
    for i in range(4):  # pop se queda en 4 pistas: no entra
        _play(s, users[0], _track(s, artist, i, genre="pop"))
    data = client.get("/api/library/charts").json()
    assert [g["genre"] for g in data["items"]] == ["rap"]
    assert data["items"][0]["name"] == "Rap / Hip-Hop"
    assert data["items"][0]["track_count"] == 5
    assert client.get("/api/library/charts/pop").status_code == 404
    # Una pista antigua de pop no hace subir el recuento de la ventana.
    _play(s, users[0], _track(s, artist, 9, genre="pop"), ago=timedelta(days=20))
    assert [g["genre"] for g in client.get("/api/library/charts").json()["items"]] == ["rap"]


def test_limit_recorta_y_se_acota(db, client):
    s, artist, users = db
    _rap_genre(s, artist, users, count=8)
    assert len(client.get("/api/library/charts/rap?limit=3").json()["items"]) == 3
    assert client.get("/api/library/charts?limit=3").json()["items"][0]["track_count"] == 3
    assert client.get("/api/library/charts/rap?limit=51").status_code == 422


def test_genero_se_normaliza_a_minusculas(db, client):
    s, artist, users = db
    for i in range(5):
        _play(s, users[0], _track(s, artist, i, genre="Rap " if i % 2 else "rap"))
    assert client.get("/api/library/charts/RAP").json()["track_count"] == 5
