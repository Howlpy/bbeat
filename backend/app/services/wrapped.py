"""Cálculo del Wrapped: un solo recorrido sobre los plays del periodo.

Devuelve ids y números; el endpoint hidrata las pistas. Las horas y los días
se cuentan en la zona horaria del cliente (`tz_min`, minutos al este de UTC).
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Play, Track

PERIOD_DAYS = {"week": 7, "month": 30, "year": 365, "all": None}


def _streak(days: set) -> int:
    """Racha más larga de días consecutivos dentro del conjunto."""
    best = 0
    for d in days:
        if d - timedelta(days=1) in days:
            continue  # no es el inicio de una racha
        n = 1
        while d + timedelta(days=n) in days:
            n += 1
        best = max(best, n)
    return best


def compute(
    session: Session,
    user_id: int,
    period: str,
    tz_min: int = 0,
    now: Optional[datetime] = None,
) -> dict:
    now = now or datetime.utcnow()
    days = PERIOD_DAYS[period]
    cutoff = now - timedelta(days=days) if days else None
    off = timedelta(minutes=tz_min)

    stmt = (
        select(Play.played_at, Play.track_id, Track.artist_id, Track.duration_ms, Track.genre)
        .join(Track, Track.id == Play.track_id)
        .where(Play.user_id == user_id)
    )
    if cutoff:
        stmt = stmt.where(Play.played_at >= cutoff)
    rows = session.exec(stmt).all()

    tracks: Counter = Counter()
    artists: Counter = Counter()
    genres: Counter = Counter()
    hours = [0] * 24
    weekdays = [0] * 7  # lunes = 0
    local_days: set = set()
    total_ms = 0
    for played_at, track_id, artist_id, dur, genre in rows:
        tracks[track_id] += 1
        artists[artist_id] += 1
        total_ms += dur or 0
        g = (genre or "").strip().lower()
        if g:
            genres[g] += 1
        local = played_at + off
        hours[local.hour] += 1
        weekdays[local.weekday()] += 1
        local_days.add(local.date())

    total_plays = len(rows)

    # Descubrimientos: pistas/artistas cuyo primer play de siempre cae en el periodo.
    new_tracks = new_artists = 0
    if total_plays and cutoff is not None:
        first = session.exec(
            select(Play.track_id, Track.artist_id, func.min(Play.played_at))
            .join(Track, Track.id == Play.track_id)
            .where(Play.user_id == user_id)
            .group_by(Play.track_id)
        ).all()
        art_first: dict = {}
        for tid, aid, fp in first:
            if fp >= cutoff:
                new_tracks += 1
            if aid not in art_first or fp < art_first[aid]:
                art_first[aid] = fp
        new_artists = sum(1 for fp in art_first.values() if fp >= cutoff)
    elif total_plays:
        # "Todo": todo lo escuchado es descubierto en el periodo.
        new_tracks, new_artists = len(tracks), len(artists)

    # Posición de minutos frente al resto de usuarios con plays en el periodo.
    rank_pct = None
    if total_plays:
        per_user = (
            select(func.coalesce(func.sum(Track.duration_ms), 0))
            .select_from(Play)
            .join(Track, Track.id == Play.track_id)
        )
        if cutoff:
            per_user = per_user.where(Play.played_at >= cutoff)
        mins = list(session.exec(per_user.group_by(Play.user_id)).all())
        if len(mins) > 1:
            below = sum(1 for m in mins if m < total_ms)
            rank_pct = round(100 * below / (len(mins) - 1))

    total_genre = sum(genres.values())
    return {
        "period": period,
        "total_plays": total_plays,
        "total_minutes": round(total_ms / 60000),
        "unique_tracks": len(tracks),
        "unique_artists": len(artists),
        "new_tracks": new_tracks,
        "new_artists": new_artists,
        "rank_pct": rank_pct,
        "best_streak": _streak(local_days),
        "active_days": len(local_days),
        "hours": hours,
        "weekdays": weekdays,
        "top_track_ids": tracks.most_common(5),
        "top_artist_ids": artists.most_common(5),
        "genres": [
            {"genre": g, "plays": n, "pct": round(100 * n / total_genre)}
            for g, n in genres.most_common(5)
        ],
    }
