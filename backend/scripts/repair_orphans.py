"""Reparación puntual (2026-05-28): secuelas del bug de indexado de opus.

- Borra duplicados de pistas creados al re-importar la playlist ZorjMix
  (las copias sin carátula; se conserva la versión con carátula / el single).
- Rellena external_id + source_url en las pistas que indexó el scanner
  (no los tenía → el dedup fallaba y se duplicaban), emparejando con su Job.
- Enlaza pistas con album_id pero sin fila AlbumTrack.
- Rellena la carátula propia de cada pista desde la art embebida (opus incluido).

Uso:  python -m scripts.repair_orphans            (dry-run)
      python -m scripts.repair_orphans --apply
"""
from __future__ import annotations

import sys

from sqlmodel import select

from app.db import session_scope
from app.models import AlbumTrack, Job, Track
from app.services import library as library_svc, scanner

DRY = "--apply" not in sys.argv

# Duplicados a borrar (se conserva el otro de cada par, ya enlazado a ZorjMix).
DUP_TRACKS_TO_DELETE = [120, 121, 153, 148]


def _source_url_for(spotify_track_id: str | None) -> str | None:
    if not spotify_track_id:
        return None
    if spotify_track_id.startswith("yt:"):
        return f"https://www.youtube.com/watch?v={spotify_track_id[3:]}"
    if spotify_track_id.startswith("sc:"):
        return None  # el id de soundcloud no reconstruye URL fiable
    return f"https://open.spotify.com/track/{spotify_track_id}"


def delete_dups() -> None:
    for tid in DUP_TRACKS_TO_DELETE:
        with session_scope() as s:
            t = s.get(Track, tid)
            if not t:
                print(f"  dup {tid}: ya no existe, skip")
                continue
            print(f"  dup {tid}: '{t.title}' · {t.file_path}")
        if not DRY:
            library_svc.delete_track(tid)


def backfill_ids() -> None:
    """Empareja cada Job done-sin-track con su pista por (album, título) y
    rellena external_id + source_url + result_track_id."""
    matched = ambiguous = unmatched = 0
    with session_scope() as s:
        jobs = s.exec(
            select(Job).where(Job.status == "done", Job.result_track_id.is_(None))
        ).all()
        for j in jobs:
            stmt = select(Track).where(Track.title == j.title)
            if j.target_album_id:
                stmt = stmt.where(Track.album_id == j.target_album_id)
            else:
                stmt = stmt.where(Track.album_id.is_(None))
            cands = s.exec(stmt).all()
            if len(cands) != 1:
                if cands:
                    ambiguous += 1
                else:
                    unmatched += 1
                continue
            t = cands[0]
            changed = []
            if not t.external_id and j.spotify_track_id:
                t.external_id = j.spotify_track_id
                changed.append("external_id")
            src = _source_url_for(j.spotify_track_id)
            if not t.source_url and src:
                t.source_url = src
                changed.append("source_url")
            j.result_track_id = t.id
            changed.append("job.result_track_id")
            if changed:
                matched += 1
                s.add(t)
                s.add(j)
                print(f"  job {j.id} → track {t.id} '{t.title}': {', '.join(changed)}")
        if DRY:
            s.rollback()
    print(f"  emparejados={matched} ambiguos={ambiguous} sin_match={unmatched}")


def link_orphans() -> None:
    """Crea AlbumTrack para pistas con album_id pero sin fila M:N en su álbum."""
    with session_scope() as s:
        tracks = s.exec(select(Track).where(Track.album_id.is_not(None))).all()
        for t in tracks:
            exists = s.exec(
                select(AlbumTrack).where(
                    AlbumTrack.album_id == t.album_id, AlbumTrack.track_id == t.id
                )
            ).first()
            if not exists:
                print(f"  link track {t.id} '{t.title}' → album {t.album_id}")
                if not DRY:
                    s.add(AlbumTrack(album_id=t.album_id, track_id=t.id, position=t.track_number))
        if DRY:
            s.rollback()


def main() -> None:
    print(f"=== repair_orphans ({'DRY-RUN' if DRY else 'APPLY'}) ===")
    print("[1] borrar duplicados")
    delete_dups()
    print("[2] rellenar external_id + source_url")
    backfill_ids()
    print("[3] enlazar pistas sin M:N")
    link_orphans()
    print("[4] carátulas por pista (embebidas)")
    if DRY:
        print("  (se omite en dry-run; backfill_track_covers escribe ficheros)")
    else:
        res = scanner.backfill_track_covers()
        print(f"  {res}")
    print("=== fin ===")


if __name__ == "__main__":
    main()
