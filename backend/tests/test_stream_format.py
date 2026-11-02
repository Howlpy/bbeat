"""GET /library/stream/{id}?format=: transcodificado para navegadores sin Ogg Opus."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, delete

from app.api import stream
from app.config import settings
from app.db import engine, init_db
from app.models import Artist, Track, User
from app.services import auth as auth_svc


@pytest.fixture()
def env():
    init_db()
    SQLModel.metadata.create_all(engine)
    settings.music_dir.mkdir(parents=True, exist_ok=True)
    (settings.music_dir / "a.opus").write_bytes(b"OggS" + b"o" * 100)
    (settings.music_dir / "b.mp3").write_bytes(b"ID3" + b"m" * 50)
    with Session(engine) as s:
        for model in (Track, Artist, User):
            s.exec(delete(model))
        s.commit()
        artist = Artist(name="A", name_normalized="a")
        user = User(username="u", email="u@x.com", password_hash="x", is_approved=True)
        s.add_all([artist, user])
        s.commit()
        opus = Track(title="o", artist_id=artist.id, file_path="a.opus", file_format="opus")
        mp3 = Track(title="m", artist_id=artist.id, file_path="b.mp3", file_format="mp3")
        s.add_all([opus, mp3])
        s.commit()
        s.refresh(opus)
        s.refresh(mp3)
        app = FastAPI()
        app.include_router(stream.router, prefix="/api")
        app.dependency_overrides[auth_svc.get_current_user] = lambda: user
        yield TestClient(app), opus.id, mp3.id


def _fake_transcode(calls):
    def fake(track_id, src, fmt):
        calls.append((track_id, fmt))
        out = settings.transcache_dir
        out.mkdir(parents=True, exist_ok=True)
        f = out / f"{track_id}.{fmt}"
        f.write_bytes(b"T" * 200)
        return f
    return fake


def test_sin_format_sirve_el_original(env):
    client, opus_id, _ = env
    r = client.get(f"/api/library/stream/{opus_id}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/ogg"


def test_format_desconocido_da_400(env):
    client, opus_id, _ = env
    assert client.get(f"/api/library/stream/{opus_id}?format=wma").status_code == 400


def test_format_m4a_transcodifica(env, monkeypatch):
    client, opus_id, _ = env
    calls = []
    monkeypatch.setattr(stream, "get_transcoded", _fake_transcode(calls))
    r = client.get(f"/api/library/stream/{opus_id}?format=m4a")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mp4"
    assert len(r.content) == 200
    assert calls == [(opus_id, "m4a")]


def test_format_mp3_con_range(env, monkeypatch):
    client, opus_id, _ = env
    monkeypatch.setattr(stream, "get_transcoded", _fake_transcode([]))
    r = client.get(f"/api/library/stream/{opus_id}?format=mp3", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.headers["content-range"] == "bytes 0-9/200"


def test_format_igual_al_del_fichero_no_transcodifica(env, monkeypatch):
    client, _, mp3_id = env
    calls = []
    monkeypatch.setattr(stream, "get_transcoded", _fake_transcode(calls))
    r = client.get(f"/api/library/stream/{mp3_id}?format=mp3")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert calls == []


def test_fallo_de_ffmpeg_da_500(env, monkeypatch):
    client, opus_id, _ = env

    def boom(*a):
        raise RuntimeError("ffmpeg")

    monkeypatch.setattr(stream, "get_transcoded", boom)
    assert client.get(f"/api/library/stream/{opus_id}?format=m4a").status_code == 500
