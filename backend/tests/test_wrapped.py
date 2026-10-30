"""Wrapped: periodos, horas en zona del cliente, rachas, descubrimientos y ranking."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, delete

from app.api import library
from app.db import engine, init_db
from app.models import Artist, Play, Track, User
from app.services import auth as auth_svc

# Fecha fija a mediodía para que "hace N días" no cruce medianoche.
NOW = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)


@pytest.fixture()
def db():
    init_db()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for model in (Play, Track, Artist, User):
            s.exec(delete(model))
        s.commit()
        a1 = Artist(name="A1", name_normalized="a1")
        a2 = Artist(name="A2", name_normalized="a2")
        s.add_all([a1, a2])
        users = [
            User(username=f"u{i}", email=f"u{i}@x.com", password_hash="x", is_approved=True)
            for i in range(3)
        ]
        s.add_all(users)
        s.commit()
        yield s, (a1, a2), users


@pytest.fixture()
def client(db):
    _, _, users = db
    app = FastAPI()
    app.include_router(library.router, prefix="/api")
    app.dependency_overrides[auth_svc.get_current_user] = lambda: users[0]
    return TestClient(app)


def _track(s, artist, n, genre="rap", ms=60000):
    t = Track(
        title=f"t{n}", artist_id=artist.id, genre=genre, duration_ms=ms, file_path=f"/m/{artist.id}-{n}.mp3"
    )
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


def _play(s, user, track, ago=timedelta(hours=1), times=1, at=None):
    for _ in range(times):
        s.add(Play(user_id=user.id, track_id=track.id, played_at=at or (NOW - ago)))
    s.commit()


def _get(client, **q):
    return client.get("/api/library/me/wrapped", params=q).json()


def test_totales_y_tops(db, client):
    s, (a1, a2), users = db
    t1, t2 = _track(s, a1, 1), _track(s, a2, 2, genre="pop", ms=120000)
    _play(s, users[0], t1, times=3)
    _play(s, users[0], t2)
    d = _get(client)
    assert d["total_plays"] == 4
    assert d["total_minutes"] == 5  # 3x1 + 2 min
    assert d["unique_tracks"] == 2 and d["unique_artists"] == 2
    assert d["top_tracks"][0]["id"] == t1.id and d["top_tracks"][0]["plays"] == 3
    assert d["top_artists"][0] == {"id": a1.id, "name": "A1", "plays": 3}
    assert [g["genre"] for g in d["genres"]] == ["rap", "pop"]
    assert d["genres"][0]["pct"] == 75 and d["genres"][0]["name"]


def test_periodo_filtra_y_vacio(db, client):
    s, (a1, _), users = db
    t = _track(s, a1, 1)
    _play(s, users[0], t, ago=timedelta(days=20))
    assert _get(client, period="week")["total_plays"] == 0
    assert _get(client, period="month")["total_plays"] == 1
    assert _get(client, period="week")["top_tracks"] == []
    assert client.get("/api/library/me/wrapped?period=bad").status_code == 422


def test_horas_en_zona_del_cliente(db, client):
    s, (a1, _), users = db
    t = _track(s, a1, 1)
    _play(s, users[0], t, at=NOW.replace(hour=23))  # 23h UTC
    assert _get(client, tz=0)["hours"][23] == 1
    # UTC+2: ya es la 01h del día siguiente
    assert _get(client, tz=120)["hours"][1] == 1


def test_racha_mas_larga_y_dias_activos(db, client):
    s, (a1, _), users = db
    t = _track(s, a1, 1)
    for d in (1, 2, 3, 6, 7):
        _play(s, users[0], t, ago=timedelta(days=d))
    d = _get(client, period="month")
    assert d["best_streak"] == 3 and d["active_days"] == 5
    assert sum(d["weekdays"]) == 5


def test_descubrimientos_solo_primer_play_en_periodo(db, client):
    s, (a1, a2), users = db
    viejo, nuevo = _track(s, a1, 1), _track(s, a2, 2)
    _play(s, users[0], viejo, ago=timedelta(days=60))
    _play(s, users[0], viejo, ago=timedelta(days=2))
    _play(s, users[0], nuevo, ago=timedelta(days=2))
    d = _get(client, period="month")
    assert d["unique_tracks"] == 2
    assert d["new_tracks"] == 1 and d["new_artists"] == 1


def test_ranking_frente_a_otros(db, client):
    s, (a1, _), users = db
    t = _track(s, a1, 1)
    assert _get(client)["rank_pct"] is None  # sin plays
    _play(s, users[0], t, times=5)
    assert _get(client)["rank_pct"] is None  # solo tú
    _play(s, users[1], t, times=2)
    _play(s, users[2], t, times=9)
    assert _get(client)["rank_pct"] == 50  # superas a 1 de los otros 2
