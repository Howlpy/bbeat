"""Handlers de los endpoints Subsonic.

Cada handler recibe `(params: dict, user: User, session: Session)` y devuelve:
  - un `dict` con el CUERPO de la respuesta (lo envuelve/serializa el dispatcher), o
  - un `fastapi.Response` directo (para binarios: stream/download/getCoverArt).

bbeat es un pool global: todos los usuarios ven todo el catálogo, así que el
browsing no filtra por dueño. Lo que sí es por-usuario: star/unstar (TrackLike) y
scrobble (Play).

Mapeo de entidades:
  Artist → artist · Album(kind='album') → album · Track → song
  Album(kind='playlist') → playlist (canciones vía AlbumTrack M:N)
IDs opacos con prefijo de tipo: ar-/al-/tr-/pl-.
"""
from __future__ import annotations

import random
import re
from datetime import datetime
from pathlib import Path

from fastapi import Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.stream import (
    CONTENT_TYPES,
    _iter_file_range,
    _parse_range,
)
from app.config import settings
from app.models import (
    Album,
    AlbumSave,
    AlbumTrack,
    Artist,
    Play,
    Track,
    TrackLike,
    User,
)
from app.services import access as access_svc
from app.services import library as library_svc
from app.services import presence as presence_svc

from .auth import (
    ERR_MISSING_PARAM,
    ERR_NOT_AUTHORIZED,
    ERR_NOT_FOUND,
    SubsonicError,
)

IGNORED_ARTICLES = "The El La Los Las Le Les"

# Presencia corta para un scrobble "ya reproducido" (submission=true): la pista
# acaba de sonar, la mostramos un momento sin dejarla clavada en el feed.
TTL_SUBSONIC_PLAYED = 60


def _mark_now_playing(session: Session, user: User, track_id: int, ttl: float) -> None:
    """Registra presencia en vivo para un evento Subsonic (now-playing/stream)."""
    try:
        from app.api.library import track_payload_by_id

        payload = track_payload_by_id(session, track_id, user)
        if payload:
            presence_svc.touch(user.id, user.username, payload, "subsonic", ttl)
    except Exception:  # noqa: BLE001 — la presencia nunca debe romper el stream/scrobble
        pass


# ─── Helpers de IDs y formato ────────────────────────────────────


def _iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parse_id(raw: str | None, prefix: str) -> int | None:
    if not raw or not raw.startswith(prefix):
        return None
    try:
        return int(raw[len(prefix):])
    except ValueError:
        return None


def _compact(d: dict) -> dict:
    """Quita claves con valor None (más limpio en JSON; en XML ya se ignoran)."""
    return {k: v for k, v in d.items() if v is not None}


def _track_cover_id(track: Track, album: Album | None) -> str | None:
    if getattr(track, "has_cover", False):
        return f"tr-{track.id}"
    if album and album.cover_path:
        return f"al-{album.id}"
    return None


# ─── Mapeadores entidad → dict Subsonic ──────────────────────────


def _song(track: Track, artist: Artist, album: Album | None, *, starred_at=None) -> dict:
    suffix = (track.file_format or "").lower()
    d = {
        "id": f"tr-{track.id}",
        "parent": f"al-{album.id}" if album else None,
        "isDir": False,
        "title": track.title,
        "album": album.title if album else None,
        "artist": artist.name,
        "track": track.track_number,
        "year": album.year if album else None,
        "coverArt": _track_cover_id(track, album),
        "size": track.file_size,
        "contentType": CONTENT_TYPES.get(suffix, "application/octet-stream"),
        "suffix": suffix or None,
        "duration": round(track.duration_ms / 1000) if track.duration_ms else 0,
        "bitRate": track.bitrate,
        "path": track.file_path,
        "isVideo": False,
        "discNumber": track.disc_number,
        "created": _iso(track.created_at),
        "albumId": f"al-{album.id}" if album else None,
        "artistId": f"ar-{artist.id}",
        "type": "music",
    }
    if starred_at:
        d["starred"] = _iso(starred_at)
    return _compact(d)


def _album(album: Album, artist_name: str, song_count: int, duration_secs: int) -> dict:
    return _compact({
        "id": f"al-{album.id}",
        "name": album.title,
        "title": album.title,
        "artist": artist_name,
        "artistId": f"ar-{album.artist_id}",
        "coverArt": f"al-{album.id}" if album.cover_path else None,
        "songCount": song_count,
        "duration": duration_secs,
        "created": _iso(album.created_at),
        "year": album.year,
    })


def _artist(artist: Artist, album_count: int) -> dict:
    return _compact({
        "id": f"ar-{artist.id}",
        "name": artist.name,
        "albumCount": album_count,
    })


def _playlist(album: Album, song_count: int, duration_secs: int, owner_name: str) -> dict:
    return _compact({
        "id": f"pl-{album.id}",
        "name": album.title,
        "songCount": song_count,
        "duration": duration_secs,
        "public": True,
        "owner": owner_name,
        "created": _iso(album.created_at),
        "coverArt": f"pl-{album.id}" if album.cover_path else None,
    })


# ─── Consultas reutilizables ─────────────────────────────────────


def _album_stats(session: Session, album_ids: list[int]) -> dict[int, tuple[int, int]]:
    """{album_id: (song_count, duration_secs)} para un conjunto de álbumes,
    contando la pertenencia vía AlbumTrack (membresía canónica en bbeat)."""
    if not album_ids:
        return {}
    rows = session.exec(
        select(
            AlbumTrack.album_id,
            func.count(AlbumTrack.track_id),
            func.coalesce(func.sum(Track.duration_ms), 0),
        )
        .join(Track, Track.id == AlbumTrack.track_id)
        .where(AlbumTrack.album_id.in_(album_ids))
        .group_by(AlbumTrack.album_id)
    ).all()
    return {aid: (cnt, round((dur or 0) / 1000)) for aid, cnt, dur in rows}


def _album_songs(session: Session, album_id: int) -> list[dict]:
    """Canciones de un álbum/playlist en orden, mapeadas a song dicts."""
    rows = session.exec(
        select(Track, Artist, Album, AlbumTrack.position)
        .join(AlbumTrack, AlbumTrack.track_id == Track.id)
        .join(Artist, Artist.id == Track.artist_id)
        .outerjoin(Album, Album.id == Track.album_id)
        .where(AlbumTrack.album_id == album_id)
        .order_by(AlbumTrack.position, Track.disc_number, Track.track_number, Track.title)
    ).all()
    return [_song(t, ar, al) for t, ar, al, _pos in rows]


def _resolve_song_row(session: Session, track_id: int):
    return session.exec(
        select(Track, Artist, Album)
        .join(Artist, Artist.id == Track.artist_id)
        .outerjoin(Album, Album.id == Track.album_id)
        .where(Track.id == track_id)
    ).first()


# ─── Sistema ─────────────────────────────────────────────────────


def ping(params, user, session) -> dict:
    return {}


def getLicense(params, user, session) -> dict:
    return {"license": {"valid": True}}


def getOpenSubsonicExtensions(params, user, session) -> dict:
    return {"openSubsonicExtensions": []}


def getUser(params, user, session) -> dict:
    return {"user": {
        "username": user.username,
        "email": user.email,
        "scrobblingEnabled": True,
        "adminRole": bool(user.is_admin),
        "settingsRole": False,
        "downloadRole": True,
        "uploadRole": False,
        "playlistRole": False,
        "coverArtRole": True,
        "commentRole": False,
        "podcastRole": False,
        "streamRole": True,
        "jukeboxRole": False,
        "shareRole": False,
        "folder": [0],
    }}


def getMusicFolders(params, user, session) -> dict:
    return {"musicFolders": {"musicFolder": [{"id": 0, "name": "Bbeat"}]}}


def getGenres(params, user, session) -> dict:
    return {"genres": {"genre": []}}


# ─── Browsing (ID3) ──────────────────────────────────────────────


def _artists_with_counts(session: Session):
    """[(Artist, album_count)] de artistas con ≥1 álbum (kind='album') o ≥1 pista."""
    album_counts = dict(session.exec(
        select(Album.artist_id, func.count(Album.id))
        .where(Album.kind == "album")
        .group_by(Album.artist_id)
    ).all())
    track_artist_ids = set(session.exec(select(Track.artist_id).distinct()).all())
    keep_ids = set(album_counts) | track_artist_ids
    if not keep_ids:
        return []
    artists = session.exec(
        select(Artist).where(Artist.id.in_(keep_ids)).order_by(Artist.name)
    ).all()
    return [(a, album_counts.get(a.id, 0)) for a in artists]


def _index_letter(name: str) -> str:
    ch = (name or "#").strip()
    for art in ("The ", "El ", "La ", "Los ", "Las ", "Le ", "Les "):
        if ch.startswith(art):
            ch = ch[len(art):]
            break
    first = (ch[:1] or "#").upper()
    return first if first.isalpha() else "#"


def _build_index(session: Session) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for artist, count in _artists_with_counts(session):
        buckets.setdefault(_index_letter(artist.name), []).append(_artist(artist, count))
    return [
        {"name": letter, "artist": buckets[letter]}
        for letter in sorted(buckets)
    ]


def getArtists(params, user, session) -> dict:
    return {"artists": {
        "ignoredArticles": IGNORED_ARTICLES,
        "index": _build_index(session),
    }}


def getIndexes(params, user, session) -> dict:
    return {"indexes": {
        "ignoredArticles": IGNORED_ARTICLES,
        "lastModified": 0,
        "index": _build_index(session),
    }}


def getArtist(params, user, session) -> dict:
    aid = _parse_id(params.get("id"), "ar-")
    artist = session.get(Artist, aid) if aid else None
    if not artist:
        raise SubsonicError(ERR_NOT_FOUND, "Artista no encontrado")
    albums = session.exec(
        select(Album)
        .where(Album.artist_id == artist.id, Album.kind == "album")
        .order_by(Album.year, Album.title)
    ).all()
    stats = _album_stats(session, [al.id for al in albums])
    album_dicts = [
        _album(al, artist.name, *stats.get(al.id, (0, 0))) for al in albums
    ]
    return {"artist": _compact({
        "id": f"ar-{artist.id}",
        "name": artist.name,
        "albumCount": len(album_dicts),
        "album": album_dicts,
    })}


def getAlbum(params, user, session) -> dict:
    alid = _parse_id(params.get("id"), "al-") or _parse_id(params.get("id"), "pl-")
    album = session.get(Album, alid) if alid else None
    if not album:
        raise SubsonicError(ERR_NOT_FOUND, "Álbum no encontrado")
    artist = session.get(Artist, album.artist_id)
    songs = _album_songs(session, album.id)
    duration = sum(s.get("duration", 0) for s in songs)
    body = _album(album, artist.name if artist else "Unknown Artist", len(songs), duration)
    body["song"] = songs
    return {"album": body}


def getSong(params, user, session) -> dict:
    tid = _parse_id(params.get("id"), "tr-")
    row = _resolve_song_row(session, tid) if tid else None
    if not row:
        raise SubsonicError(ERR_NOT_FOUND, "Canción no encontrada")
    t, ar, al = row
    return {"song": _song(t, ar, al)}


def getMusicDirectory(params, user, session) -> dict:
    """Browsing por carpetas (clientes legacy). Carpeta de artista → sus álbumes
    + singles sueltos; carpeta de álbum/playlist → sus canciones."""
    raw = params.get("id")
    aid = _parse_id(raw, "ar-")
    if aid is not None:
        artist = session.get(Artist, aid)
        if not artist:
            raise SubsonicError(ERR_NOT_FOUND, "No encontrado")
        albums = session.exec(
            select(Album)
            .where(Album.artist_id == artist.id, Album.kind == "album")
            .order_by(Album.year, Album.title)
        ).all()
        stats = _album_stats(session, [al.id for al in albums])
        children = [
            _compact({
                "id": f"al-{al.id}",
                "parent": f"ar-{artist.id}",
                "isDir": True,
                "title": al.title,
                "name": al.title,
                "artist": artist.name,
                "artistId": f"ar-{artist.id}",
                "coverArt": f"al-{al.id}" if al.cover_path else None,
                "songCount": stats.get(al.id, (0, 0))[0],
                "year": al.year,
            })
            for al in albums
        ]
        # Singles sueltos del artista (sin álbum)
        loose = session.exec(
            select(Track, Artist, Album)
            .join(Artist, Artist.id == Track.artist_id)
            .outerjoin(Album, Album.id == Track.album_id)
            .where(Track.artist_id == artist.id, Track.album_id.is_(None))
            .order_by(Track.title)
        ).all()
        children.extend(_song(t, ar, al) for t, ar, al in loose)
        return {"directory": {
            "id": f"ar-{artist.id}",
            "name": artist.name,
            "child": children,
        }}

    alid = _parse_id(raw, "al-") or _parse_id(raw, "pl-")
    album = session.get(Album, alid) if alid else None
    if not album:
        raise SubsonicError(ERR_NOT_FOUND, "No encontrado")
    return {"directory": {
        "id": f"al-{album.id}",
        "name": album.title,
        "child": _album_songs(session, album.id),
    }}


# ─── Listas ──────────────────────────────────────────────────────


def _albums_query_ordered(session: Session, list_type: str, size: int, offset: int):
    base = select(Album).where(Album.kind == "album")
    if list_type == "alphabeticalByName":
        base = base.order_by(Album.title)
    elif list_type == "alphabeticalByArtist":
        base = base.join(Artist, Artist.id == Album.artist_id).order_by(Artist.name, Album.title)
    elif list_type == "newest":
        base = base.order_by(Album.created_at.desc())
    elif list_type == "recent":
        base = base.order_by(Album.created_at.desc())
    elif list_type == "byYear":
        base = base.order_by(Album.year)
    elif list_type == "random":
        rows = session.exec(base).all()
        random.shuffle(rows)
        return rows[offset:offset + size]
    elif list_type == "starred":
        return []  # bbeat no marca álbumes con estrella (solo canciones)
    else:  # frequent y desconocidos → por novedad
        base = base.order_by(Album.created_at.desc())
    return session.exec(base.limit(size).offset(offset)).all()


def _album_list_body(session: Session, list_type: str, size: int, offset: int) -> list[dict]:
    albums = _albums_query_ordered(session, list_type, size, offset)
    stats = _album_stats(session, [al.id for al in albums])
    out = []
    for al in albums:
        artist = session.get(Artist, al.artist_id)
        out.append(_album(al, artist.name if artist else "Unknown Artist", *stats.get(al.id, (0, 0))))
    return out


def getAlbumList2(params, user, session) -> dict:
    list_type = params.get("type", "newest")
    size = min(int(params.get("size", 10) or 10), 500)
    offset = int(params.get("offset", 0) or 0)
    return {"albumList2": {"album": _album_list_body(session, list_type, size, offset)}}


def getAlbumList(params, user, session) -> dict:
    list_type = params.get("type", "newest")
    size = min(int(params.get("size", 10) or 10), 500)
    offset = int(params.get("offset", 0) or 0)
    return {"albumList": {"album": _album_list_body(session, list_type, size, offset)}}


def getRandomSongs(params, user, session) -> dict:
    size = min(int(params.get("size", 10) or 10), 500)
    ids = session.exec(select(Track.id)).all()
    random.shuffle(ids)
    songs = []
    for tid in ids[:size]:
        row = _resolve_song_row(session, tid)
        if row:
            songs.append(_song(*row))
    return {"randomSongs": {"song": songs}}


def _starred_songs(session: Session, user: User) -> list[dict]:
    rows = session.exec(
        select(Track, Artist, Album, TrackLike.created_at)
        .join(TrackLike, TrackLike.track_id == Track.id)
        .join(Artist, Artist.id == Track.artist_id)
        .outerjoin(Album, Album.id == Track.album_id)
        .where(TrackLike.user_id == user.id)
        .order_by(TrackLike.created_at.desc())
    ).all()
    return [_song(t, ar, al, starred_at=starred) for t, ar, al, starred in rows]


def getStarred2(params, user, session) -> dict:
    return {"starred2": {"artist": [], "album": [], "song": _starred_songs(session, user)}}


def getStarred(params, user, session) -> dict:
    return {"starred": {"artist": [], "album": [], "song": _starred_songs(session, user)}}


def getSongsByGenre(params, user, session) -> dict:
    return {"songsByGenre": {"song": []}}


# ─── Búsqueda ────────────────────────────────────────────────────


def _do_search(session, params) -> dict:
    # Convención Subsonic/OpenSubsonic: una query VACÍA (o `""`) significa
    # "devuelve TODO". Symfonium (y otros) sincroniza la biblioteca entera
    # llamando a search3 con query="" y paginando por offsets. Hay que tratar
    # tanto la cadena vacía como las comillas literales `""` como match-all.
    raw = params.get("query") or ""
    query = raw.strip().strip('"').strip()
    match_all = query == ""
    like = f"%{query.lower()}%"

    artist_count = min(int(params.get("artistCount", 20) or 20), 500)
    album_count = min(int(params.get("albumCount", 20) or 20), 500)
    song_count = min(int(params.get("songCount", 20) or 20), 500)
    artist_off = int(params.get("artistOffset", 0) or 0)
    album_off = int(params.get("albumOffset", 0) or 0)
    song_off = int(params.get("songOffset", 0) or 0)

    artists, albums, songs = [], [], []

    # Artistas
    if artist_count > 0:
        pairs = _artists_with_counts(session)  # ya ordenado por nombre
        if not match_all:
            pairs = [(a, c) for a, c in pairs if query.lower() in a.name.lower()]
        artists = [_artist(a, c) for a, c in pairs[artist_off:artist_off + artist_count]]

    # Álbumes
    if album_count > 0:
        stmt = select(Album).where(Album.kind == "album")
        if not match_all:
            stmt = stmt.where(func.lower(Album.title).like(like))
        alrows = session.exec(
            stmt.order_by(Album.title).offset(album_off).limit(album_count)
        ).all()
        stats = _album_stats(session, [al.id for al in alrows])
        for al in alrows:
            ar = session.get(Artist, al.artist_id)
            albums.append(_album(al, ar.name if ar else "Unknown Artist", *stats.get(al.id, (0, 0))))

    # Canciones
    if song_count > 0:
        stmt = (
            select(Track, Artist, Album)
            .join(Artist, Artist.id == Track.artist_id)
            .outerjoin(Album, Album.id == Track.album_id)
        )
        if not match_all:
            stmt = stmt.where(func.lower(Track.title).like(like))
        srows = session.exec(
            stmt.order_by(Track.title).offset(song_off).limit(song_count)
        ).all()
        songs = [_song(t, ar, al) for t, ar, al in srows]

    return {"artist": artists, "album": albums, "song": songs}


def search3(params, user, session) -> dict:
    return {"searchResult3": _do_search(session, params)}


def search2(params, user, session) -> dict:
    return {"searchResult2": _do_search(session, params)}


# ─── Playlists (= álbumes kind='playlist') ───────────────────────


def getPlaylists(params, user, session) -> dict:
    albums = session.exec(
        select(Album).where(Album.kind == "playlist").order_by(Album.title)
    ).all()
    stats = _album_stats(session, [al.id for al in albums])
    owners: dict[int, str] = {}
    out = []
    for al in albums:
        owner_name = "bbeat"
        if al.owner_id:
            if al.owner_id not in owners:
                ow = session.get(User, al.owner_id)
                owners[al.owner_id] = ow.username if ow else "bbeat"
            owner_name = owners[al.owner_id]
        cnt, dur = stats.get(al.id, (0, 0))
        out.append(_playlist(al, cnt, dur, owner_name))
    return {"playlists": {"playlist": out}}


def getPlaylist(params, user, session) -> dict:
    plid = _parse_id(params.get("id"), "pl-") or _parse_id(params.get("id"), "al-")
    album = session.get(Album, plid) if plid else None
    if not album:
        raise SubsonicError(ERR_NOT_FOUND, "Playlist no encontrada")
    songs = _album_songs(session, album.id)
    owner_name = "bbeat"
    if album.owner_id:
        ow = session.get(User, album.owner_id)
        owner_name = ow.username if ow else "bbeat"
    body = _playlist(album, len(songs), sum(s.get("duration", 0) for s in songs), owner_name)
    body["entry"] = songs
    return {"playlist": body}


# ─── Playlists: escritura (create/update/delete) ─────────────────
# Una playlist Subsonic es una lista ORDENADA de referencias a canciones. En
# bbeat se materializa como un Album kind='playlist' con la pertenencia en
# AlbumTrack (position = orden). Estas operaciones NUNCA tocan ficheros de audio.

_NORM_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _NORM_RE.sub(" ", (text or "").strip().lower()) or "playlist"


def _parse_playlist_id(raw: str | None) -> int | None:
    return _parse_id(raw, "pl-") or _parse_id(raw, "al-")


def _song_ids_from(params: dict, key: str) -> list[int]:
    out = []
    for raw in params.get("_lists", {}).get(key, []):
        tid = _parse_id(raw, "tr-")
        if tid:
            out.append(tid)
    return out


def _require_mutate(album: Album, user: User) -> None:
    if not access_svc.can_mutate_album(album, user):
        raise SubsonicError(ERR_NOT_AUTHORIZED, "No tienes permiso para modificar esta playlist")


def _append_songs(session: Session, album_id: int, song_ids: list[int], start_pos: int) -> None:
    """Añade canciones al final de la playlist (dedup: una pista no se repite)."""
    existing = {
        r for r in session.exec(
            select(AlbumTrack.track_id).where(AlbumTrack.album_id == album_id)
        ).all()
    }
    pos = start_pos
    for sid in song_ids:
        if sid in existing or not session.get(Track, sid):
            continue
        session.add(AlbumTrack(album_id=album_id, track_id=sid, position=pos))
        existing.add(sid)
        pos += 1


def _clear_songs(session: Session, album_id: int) -> None:
    for at in session.exec(select(AlbumTrack).where(AlbumTrack.album_id == album_id)).all():
        session.delete(at)
    session.flush()


def _delete_playlist_keep_tracks(session: Session, album: Album) -> None:
    """Borra la playlist (contenedor + enlaces + guardados) SIN borrar ficheros.
    Las pistas cuyo album_id apuntaba a esta colección pasan a sueltas."""
    album_id = album.id
    _clear_songs(session, album_id)
    for sv in session.exec(select(AlbumSave).where(AlbumSave.album_id == album_id)).all():
        session.delete(sv)
    for t in session.exec(select(Track).where(Track.album_id == album_id)).all():
        t.album_id = None
        session.add(t)
    session.flush()
    library_svc._delete_album_record(session, album_id)  # borra carátula + fila Album


def createPlaylist(params, user, session) -> dict:
    """Crea una playlist nueva (con `name`) o reemplaza las canciones de una
    existente (con `playlistId`). Devuelve la playlist resultante (Subsonic ≥1.14)."""
    pl_id = _parse_playlist_id(params.get("playlistId"))
    song_ids = _song_ids_from(params, "songId")

    if pl_id:
        album = session.get(Album, pl_id)
        if not album:
            raise SubsonicError(ERR_NOT_FOUND, "Playlist no encontrada")
        _require_mutate(album, user)
        _clear_songs(session, album.id)
        _append_songs(session, album.id, song_ids, 0)
        target_id = album.id
    else:
        name = (params.get("name") or "").strip() or "Nueva playlist"
        artist = library_svc._get_or_create_artist(session, "Various Artists")
        album = Album(
            title=name,
            title_normalized=_normalize(name),
            artist_id=artist.id,
            kind="playlist",
            owner_id=user.id,
        )
        session.add(album)
        session.flush()
        _append_songs(session, album.id, song_ids, 0)
        if not session.get(AlbumSave, (user.id, album.id)):
            session.add(AlbumSave(user_id=user.id, album_id=album.id))
        target_id = album.id

    session.flush()
    return getPlaylist({"id": f"pl-{target_id}", "_lists": {}}, user, session)


def updatePlaylist(params, user, session) -> dict:
    """Modifica una playlist: renombrar, añadir canciones, quitar por índice."""
    pl_id = _parse_playlist_id(params.get("playlistId"))
    album = session.get(Album, pl_id) if pl_id else None
    if not album:
        raise SubsonicError(ERR_NOT_FOUND, "Playlist no encontrada")
    _require_mutate(album, user)

    # Renombrar (comment/public no aplican en bbeat → se ignoran sin error)
    name = params.get("name")
    if name is not None and name.strip():
        album.title = name.strip()
        album.title_normalized = _normalize(name)
        session.add(album)

    # Quitar por índice (0-based, sobre el orden actual) ANTES de añadir
    remove_idx = set()
    for raw in params.get("_lists", {}).get("songIndexToRemove", []):
        try:
            remove_idx.add(int(raw))
        except (TypeError, ValueError):
            pass
    if remove_idx:
        current = session.exec(
            select(AlbumTrack).where(AlbumTrack.album_id == album.id)
            .order_by(AlbumTrack.position)
        ).all()
        for i, at in enumerate(current):
            if i in remove_idx:
                session.delete(at)
        session.flush()

    # Añadir al final
    to_add = _song_ids_from(params, "songIdToAdd")
    if to_add:
        remaining = session.exec(
            select(AlbumTrack).where(AlbumTrack.album_id == album.id)
            .order_by(AlbumTrack.position)
        ).all()
        start = (max((r.position or 0) for r in remaining) + 1) if remaining else 0
        _append_songs(session, album.id, to_add, start)

    session.flush()
    return {}


def deletePlaylist(params, user, session) -> dict:
    pl_id = _parse_playlist_id(params.get("id"))
    album = session.get(Album, pl_id) if pl_id else None
    if not album:
        raise SubsonicError(ERR_NOT_FOUND, "Playlist no encontrada")
    _require_mutate(album, user)
    _delete_playlist_keep_tracks(session, album)
    return {}


# ─── Anotaciones ─────────────────────────────────────────────────


def star(params, user, session) -> dict:
    for raw in params.get("id_list", []):
        tid = _parse_id(raw, "tr-")
        if tid and session.get(Track, tid):
            if not session.get(TrackLike, (user.id, tid)):
                session.add(TrackLike(user_id=user.id, track_id=tid))
    return {}


def unstar(params, user, session) -> dict:
    for raw in params.get("id_list", []):
        tid = _parse_id(raw, "tr-")
        if tid:
            existing = session.get(TrackLike, (user.id, tid))
            if existing:
                session.delete(existing)
    return {}


def scrobble(params, user, session) -> dict:
    # submission=false es la notificación "now playing"; true es "ya reproducido".
    submission = str(params.get("submission", "true")).lower() != "false"
    for raw in params.get("id_list", []):
        tid = _parse_id(raw, "tr-")
        if not (tid and session.get(Track, tid)):
            continue
        if submission:
            session.add(Play(user_id=user.id, track_id=tid))
            _mark_now_playing(session, user, tid, TTL_SUBSONIC_PLAYED)
        else:
            _mark_now_playing(session, user, tid, presence_svc.TTL_SUBSONIC_NOW)
    return {}


def setRating(params, user, session) -> dict:
    return {}  # no-op: bbeat no tiene ratings


# ─── Media (binarios: devuelven Response directo) ────────────────


def _stream_response(track: Track, params: dict) -> Response:
    path = (settings.music_dir / track.file_path).resolve()
    if not path.is_file():
        raise SubsonicError(ERR_NOT_FOUND, "Fichero no encontrado")
    try:
        path.relative_to(settings.music_dir.resolve())
    except ValueError:
        raise SubsonicError(ERR_NOT_FOUND, "Ruta inválida")
    file_size = path.stat().st_size
    media_type = CONTENT_TYPES.get((track.file_format or "").lower(), "application/octet-stream")
    base_headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}

    range_header = params.get("_range")
    if range_header:
        parsed = _parse_range(range_header, file_size)
        if parsed:
            start, end = parsed
            return StreamingResponse(
                _iter_file_range(path, start, end),
                status_code=206,
                media_type=media_type,
                headers={
                    **base_headers,
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(end - start + 1),
                },
            )
    return FileResponse(
        path, media_type=media_type,
        headers={**base_headers, "Content-Length": str(file_size)},
    )


def stream(params, user, session):
    tid = _parse_id(params.get("id"), "tr-")
    track = session.get(Track, tid) if tid else None
    if not track:
        raise SubsonicError(ERR_NOT_FOUND, "Canción no encontrada")
    # Presencia en vivo: cubre clientes que no mandan now-playing. TTL ≈ duración.
    dur_secs = (track.duration_ms or 0) / 1000 or presence_svc.TTL_SUBSONIC_NOW
    _mark_now_playing(session, user, tid, min(dur_secs, presence_svc.TTL_SUBSONIC_STREAM_MAX))
    return _stream_response(track, params)


def download(params, user, session):
    return stream(params, user, session)


def _cover_file_for(session: Session, raw: str | None) -> Path | None:
    """Resuelve el fichero de carátula a partir de un id Subsonic (al-/pl-/tr-)."""
    alid = _parse_id(raw, "al-") or _parse_id(raw, "pl-")
    if alid:
        album = session.get(Album, alid)
        if album and album.cover_path:
            p = (settings.covers_dir / album.cover_path).resolve()
            if p.is_file():
                return p
        return None
    tid = _parse_id(raw, "tr-")
    if tid:
        for ext in (".jpg", ".png"):
            p = (settings.covers_dir / f"track-{tid}{ext}").resolve()
            if p.is_file():
                return p
        # Fallback al álbum de la pista
        track = session.get(Track, tid)
        if track and track.album_id:
            album = session.get(Album, track.album_id)
            if album and album.cover_path:
                p = (settings.covers_dir / album.cover_path).resolve()
                if p.is_file():
                    return p
    return None


def getCoverArt(params, user, session):
    path = _cover_file_for(session, params.get("id"))
    if not path:
        raise SubsonicError(ERR_NOT_FOUND, "Carátula no encontrada")
    try:
        path.relative_to(settings.covers_dir.resolve())
    except ValueError:
        raise SubsonicError(ERR_NOT_FOUND, "Ruta inválida")
    media_type = "image/jpeg" if path.suffix == ".jpg" else "image/png"
    return FileResponse(
        path, media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


def getLyrics(params, user, session) -> dict:
    return {"lyrics": {
        "artist": params.get("artist", ""),
        "title": params.get("title", ""),
        "value": "",
    }}


# ─── Registro de acciones ────────────────────────────────────────

HANDLERS = {
    "ping": ping,
    "getLicense": getLicense,
    "getOpenSubsonicExtensions": getOpenSubsonicExtensions,
    "getUser": getUser,
    "getMusicFolders": getMusicFolders,
    "getGenres": getGenres,
    "getArtists": getArtists,
    "getIndexes": getIndexes,
    "getArtist": getArtist,
    "getAlbum": getAlbum,
    "getSong": getSong,
    "getMusicDirectory": getMusicDirectory,
    "getAlbumList": getAlbumList,
    "getAlbumList2": getAlbumList2,
    "getRandomSongs": getRandomSongs,
    "getStarred": getStarred,
    "getStarred2": getStarred2,
    "getSongsByGenre": getSongsByGenre,
    "search2": search2,
    "search3": search3,
    "getPlaylists": getPlaylists,
    "getPlaylist": getPlaylist,
    "createPlaylist": createPlaylist,
    "updatePlaylist": updatePlaylist,
    "deletePlaylist": deletePlaylist,
    "star": star,
    "unstar": unstar,
    "scrobble": scrobble,
    "setRating": setRating,
    "stream": stream,
    "download": download,
    "getCoverArt": getCoverArt,
    "getLyrics": getLyrics,
}

# Acciones que escriben en BD → la sesión debe hacer commit tras el handler.
WRITE_ACTIONS = {
    "star", "unstar", "scrobble", "setRating",
    "createPlaylist", "updatePlaylist", "deletePlaylist",
}
