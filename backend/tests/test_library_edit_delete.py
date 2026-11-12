"""Borrado y edicion de pistas: FK de sugerencias de genero y fichero en disco."""
import pytest
from sqlmodel import Session, SQLModel, delete, select

from app.config import settings
from app.db import engine, init_db
from app.models import (
    Album, AlbumTrack, Artist, GenreSuggestion, Job, Play, Track, TrackLike,
)
from app.services import library as library_svc, organizer
from app.services.ytdlp_resolver import _split_artist_title


def _clean():
    with Session(engine) as s:
        for m in (GenreSuggestion, AlbumTrack, TrackLike, Play, Job, Track, Album, Artist):
            s.exec(delete(m))
        s.commit()


@pytest.fixture()
def music(monkeypatch, tmp_path):
    init_db()
    SQLModel.metadata.create_all(engine)
    _clean()
    monkeypatch.setattr(organizer, "write_tags", lambda *a, **k: None)
    monkeypatch.setattr(settings, "music_dir", tmp_path)
    yield tmp_path
    _clean()


def _track_with_ai_genre(music_dir):
    """Pista cuyo artista ya clasifico la IA (fila en genre_suggestions)."""
    (music_dir / "RETRICA").mkdir()
    (music_dir / "RETRICA" / "Lucho RK.opus").write_bytes(b"x")
    with Session(engine) as s:
        a = Artist(name="RETRICA", name_normalized="retrica")
        s.add(a)
        s.commit()
        t = Track(title="Lucho RK", artist_id=a.id, file_path="RETRICA/Lucho RK.opus")
        s.add(t)
        s.commit()
        s.add(GenreSuggestion(artist_id=a.id, genre="reggaeton", status="applied"))
        s.add(GenreSuggestion(artist_id=a.id, track_id=t.id, genre="trap", status="applied"))
        s.commit()
        return t.id, a.id


def test_delete_track_removes_orphan_artist_with_ai_genre(music):
    tid, aid = _track_with_ai_genre(music)

    assert library_svc.delete_track(tid) is True

    with Session(engine) as s:
        assert s.get(Track, tid) is None
        assert s.get(Artist, aid) is None
        assert s.exec(select(GenreSuggestion)).all() == []


def test_edit_track_swaps_artist_and_title(music):
    tid, aid = _track_with_ai_genre(music)

    res = library_svc.edit_track(tid, title="RETRICA", artist="Lucho RK")

    assert res["ok"]
    with Session(engine) as s:
        t = s.get(Track, tid)
        assert t.title == "RETRICA"
        assert s.get(Artist, t.artist_id).name == "Lucho RK"
        assert s.get(Artist, aid) is None
    assert (music / res["file_path"]).is_file()


def test_edit_track_restores_file_when_db_fails(music, monkeypatch):
    tid, _ = _track_with_ai_genre(music)

    def boom(*a, **k):
        raise RuntimeError("fallo al guardar")

    monkeypatch.setattr(library_svc, "_delete_artist_if_orphan", boom)

    with pytest.raises(RuntimeError):
        library_svc.edit_track(tid, artist="Lucho RK")

    with Session(engine) as s:
        path = music / s.get(Track, tid).file_path
    assert path.is_file()


def test_delete_track_keeps_files_when_db_fails(music, monkeypatch, tmp_path_factory):
    tid, _ = _track_with_ai_genre(music)
    covers = tmp_path_factory.mktemp("covers")
    monkeypatch.setattr(settings, "covers_dir", covers)
    cover = covers / f"track-{tid}.jpg"
    cover.write_bytes(b"jpg")

    def boom(*a, **k):
        raise RuntimeError("fallo al guardar")

    monkeypatch.setattr(library_svc, "_delete_artist_if_orphan", boom)

    with pytest.raises(RuntimeError):
        library_svc.delete_track(tid)

    assert (music / "RETRICA" / "Lucho RK.opus").is_file()
    assert cover.is_file()


def test_split_reversed_song_artist_title():
    assert _split_artist_title("RETRICA - Lucho RK (Video oficial)", "Lucho RK") == (
        "RETRICA", "Lucho RK",
    )


def test_split_artist_song_title_unchanged():
    assert _split_artist_title("Lucho RK - RETRICA (Video oficial)", "Lucho RK") == (
        "RETRICA", "Lucho RK",
    )
