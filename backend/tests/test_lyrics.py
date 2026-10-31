"""Tests de letras (LRCLIB): limpieza, validación, reintentos y caché. Sin red."""
from datetime import datetime, timedelta

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import LyricsCache
from app.services import lyrics as L


@pytest.fixture(autouse=True)
def _sin_esperas(monkeypatch):
    monkeypatch.setattr(L, "_sleep", lambda s: None)


def _lrc(name="Song", artist="Artist", dur=200, synced=True, **kw):
    d = {"trackName": name, "artistName": artist, "duration": dur,
         "plainLyrics": "la la", "syncedLyrics": "[00:01.00] la" if synced else None,
         "instrumental": False}
    d.update(kw)
    return d


def _run(handler, **kw):
    kw.setdefault("artist", "Artist")
    kw.setdefault("title", "Song")
    kw.setdefault("duration_seconds", 200)
    return L.fetch_lyrics(transport=httpx.MockTransport(handler), **kw)


# ─── Limpieza ────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("“Enemy”", "Enemy"),
    ("Enemy (from Arcane Season 2) [Official Visualizer]", "Enemy"),
    ("Song [Audio]", "Song"),
    ("Song (feat. X)", "Song"),
    ("Song ft. X", "Song"),
    ("Song - 2015 Remaster", "Song"),
    ("Song - Live at NPR's Tiny Desk", "Song"),
    ("Song - En directo 1997", "Song"),
    ("Song - Remix", "Song"),
    ("Dash - Title Real", "Dash - Title Real"),
])
def test_clean_title(raw, expected):
    assert L.clean_title(raw) == expected


def test_main_artist_y_partes():
    assert L.main_artist("A / B") == "A"
    assert L.main_artist("A & B") == "A"
    assert L.main_artist("A feat. B") == "A"
    assert L.main_artist("Solo") == "Solo"
    assert L.artist_parts("A & B")[0] == "A"
    assert "B" in L.artist_parts("A & B")


def test_norm():
    assert L._norm("Ñandú, Café!") == "nandu cafe"


# ─── Validación de candidatas ────────────────────────────────

def test_rechaza_artista_equivocado():
    cands = [_lrc("Other Thing", "Someone Else", 200)]
    assert L.pick_candidate(cands, ["Artist"], "Song", 200) is None


def test_rechaza_duracion_lejana_y_instrumental():
    assert L.pick_candidate([_lrc(dur=300)], ["Artist"], "Song", 200) is None
    assert L.pick_candidate([_lrc(instrumental=True)], ["Artist"], "Song", 200) is None


def test_prefiere_artista_y_duracion_cercana():
    a = _lrc("Song", "Artist", 210, synced=True)
    b = _lrc("Song", "Artist", 201, synced=False)
    assert L.pick_candidate([a, b], ["Artist"], "Song", 200) is b


# ─── Reintentos y cadena ─────────────────────────────────────

def test_reintenta_503_y_acierta():
    calls = {"n": 0}

    def h(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=_lrc())

    res = _run(h)
    assert res["found"] and not res["approx"] and calls["n"] == 2


def test_get_503_sigue_con_busqueda():
    def h(req):
        if req.url.path.endswith("/get"):
            return httpx.Response(503)
        return httpx.Response(200, json=[_lrc()])

    res = _run(h)
    assert res["found"] and res["approx"]


def test_todo_falla_devuelve_error():
    res = _run(lambda req: httpx.Response(503))
    assert not res["found"] and res.get("error")


def test_instrumental_exacto():
    def h(req):
        return httpx.Response(200, json=_lrc(plainLyrics=None, syncedLyrics=None, instrumental=True))

    res = _run(h)
    assert not res["found"] and res["instrumental"] and not res.get("error")


def test_no_envia_album_si_none():
    seen = []

    def h(req):
        seen.append(dict(req.url.params))
        return httpx.Response(200, json=_lrc())

    _run(h, album=None)
    assert "album_name" not in seen[0]


# ─── Caché ───────────────────────────────────────────────────

@pytest.fixture()
def session():
    eng = create_engine("sqlite://")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


def _fake(monkeypatch, results):
    calls = []

    def f(*a, **k):
        calls.append(1)
        return results[min(len(calls) - 1, len(results) - 1)]

    monkeypatch.setattr(L, "fetch_lyrics", f)
    return calls


FOUND = {"found": True, "plain": "x", "synced": None, "source": "lrclib",
         "track_name": "S", "artist_name": "A", "approx": False, "instrumental": False}
MISS = {**FOUND, "found": False, "plain": None}


def test_acierto_se_cachea(session, monkeypatch):
    calls = _fake(monkeypatch, [FOUND])
    assert L.lookup(session, 1, "A", "S", None, 100)["cached"] is False
    assert L.lookup(session, 1, "A", "S", None, 100)["cached"] is True
    assert len(calls) == 1


def test_negativo_ttl(session, monkeypatch):
    calls = _fake(monkeypatch, [MISS, FOUND])
    L.lookup(session, 1, "A", "S", None, 100)
    assert L.lookup(session, 1, "A", "S", None, 100)["found"] is False  # cacheado
    assert len(calls) == 1
    row = session.get(LyricsCache, 1)
    row.fetched_at = datetime.utcnow() - timedelta(days=4)
    session.add(row)
    session.commit()
    assert L.lookup(session, 1, "A", "S", None, 100)["found"] is True
    assert len(calls) == 2


def test_error_no_se_cachea(session, monkeypatch):
    calls = _fake(monkeypatch, [{**MISS, "error": "503"}, FOUND])
    assert L.lookup(session, 1, "A", "S", None, 100).get("error")
    assert session.get(LyricsCache, 1) is None
    assert L.lookup(session, 1, "A", "S", None, 100)["found"] is True
    assert len(calls) == 2


def test_refresh_ignora_cache_e_invalidate(session, monkeypatch):
    calls = _fake(monkeypatch, [FOUND])
    L.lookup(session, 1, "A", "S", None, 100)
    L.lookup(session, 1, "A", "S", None, 100, refresh=True)
    assert len(calls) == 2
    L.invalidate(session, 1)
    assert session.get(LyricsCache, 1) is None
