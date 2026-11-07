"""Busqueda de candidatos en download_with_ytdlp (sin red)."""
from app.services import downloader
from app.services.spotify import TrackMeta

ALBUM_RESULTS = [
    {"id": "other", "title": "La Pantera - SHIPEO (Visualizer) | FILIPENSES",
     "channel": "La Pantera", "duration": 118},
    {"id": "wanted", "title": "La Pantera -  NO se XQ (Visualizer) | FILIPENSES",
     "channel": "La Pantera", "duration": 77},
]


def _meta(album: str = "FILIPENSES") -> TrackMeta:
    return TrackMeta(
        spotify_id="sp1", title="NO se XQ", artists=["La Pantera"], album=album,
        album_artist="La Pantera", track_number=6, disc_number=1, total_tracks=12,
        duration_ms=76_000, isrc=None, year=2026, cover_url=None,
    )


class FakeYDL:
    """YouTube devuelve vacio cualquier busqueda con el titulo; el disco no."""

    queries: list[str] = []
    downloaded: list[str] = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, query, download=False):
        FakeYDL.queries.append(query)
        if query.startswith("ytsearch") and "FILIPENSES" in query:
            return {"entries": ALBUM_RESULTS}
        return {"entries": []}

    def download(self, urls):
        FakeYDL.downloaded.extend(urls)
        out = self.opts["outtmpl"].replace("%(ext)s", "opus")
        open(out, "wb").close()


def _run(monkeypatch, meta):
    FakeYDL.queries, FakeYDL.downloaded = [], []
    monkeypatch.setattr(downloader, "YoutubeDL", FakeYDL)
    return downloader.download_with_ytdlp(meta)


def test_album_search_finds_track_youtube_hides_by_title(monkeypatch):
    result = _run(monkeypatch, _meta())

    assert result.file_path is not None
    assert FakeYDL.downloaded == ["https://www.youtube.com/watch?v=wanted"]
    result.file_path.unlink()


def test_album_search_runs_before_soundcloud(monkeypatch):
    _run(monkeypatch, _meta())

    assert not any(q.startswith("scsearch") for q in FakeYDL.queries)


def test_no_album_search_when_album_equals_title(monkeypatch):
    result = _run(monkeypatch, _meta(album="NO se XQ"))

    assert result.file_path is None
    assert not any("FILIPENSES" in q for q in FakeYDL.queries)
