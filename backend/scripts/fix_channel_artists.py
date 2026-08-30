"""Sustituye nombres de canal de YouTube por el artista real de la pista.

Muchas pistas se guardaron con el nombre del CANAL en vez del artista:
`arceperroviejo` en vez de Arce, `Los Chikos del Maiz oficial` en vez de
Los Chikos del Maíz, `DelinquentHabitsMusic` en vez de Delinquent Habits.

Eso rompe más de lo que parece: la vista de artista, la búsqueda, el Wrapped y
—lo que motivó este script— la resolución de género, porque esos nombres no
existen en ningún catálogo musical.

YouTube sí sabe cuál es el artista: para los vídeos con metadatos de YouTube
Music, yt-dlp devuelve `artist` y `track` limpios, distintos del `channel`. (No
devuelve género: esa clave no existe, y `categories` es solo `['Music']`.)

Cada cambio se contrasta con Deezer/iTunes antes de aplicarlo: si el artista
nuevo no lo conoce nadie, se deja el que había. Un nombre de canal es feo, pero
un artista inventado es peor.

Uso:
    python -m scripts.fix_channel_artists                 # simulacro
    python -m scripts.fix_channel_artists --apply
    python -m scripts.fix_channel_artists --solo-sin-genero
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import Artist, Track
from app.services import genres as genres_svc
from app.services.scanner import _get_or_create_artist


def _yt_meta(url: str) -> tuple[Optional[str], Optional[str]]:
    """(artist, track) según YouTube Music, o (None, None)."""
    import yt_dlp

    opts = {"quiet": True, "skip_download": True, "no_warnings": True, "extract_flat": False}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return None, None
    return (info.get("artist") or None), (info.get("track") or None)


def _primero(nombre: str) -> str:
    """'Los Chikos del Maíz, Ricardo Romero' -> 'Los Chikos del Maíz'.

    YouTube lista todos los intérpretes separados por coma. Para el artista
    principal de la pista nos quedamos con el primero, igual que hace el resto
    de bbeat.
    """
    return nombre.split(",")[0].strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="escribe de verdad")
    ap.add_argument(
        "--solo-sin-genero",
        action="store_true",
        help="solo las pistas que hoy no tienen género (las que más urge arreglar)",
    )
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    with Session(engine) as session:
        stmt = (
            select(Track, Artist)
            .join(Artist, Artist.id == Track.artist_id)
            .where(Track.source_url.is_not(None))
            .order_by(Track.id)
        )
        if args.solo_sin_genero:
            stmt = stmt.where(Track.genre.is_(None))
        rows = [
            (t, a) for t, a in session.exec(stmt).all()
            if t.source_url and "youtu" in t.source_url
        ]

    if args.limit:
        rows = rows[: args.limit]

    modo = "APLICANDO" if args.apply else "SIMULACRO (usa --apply para escribir)"
    print(f"{len(rows)} pistas con URL de YouTube · {modo}\n")

    cambios: list[tuple[int, str, str, Optional[str]]] = []
    sin_datos = igual = rechazados = 0

    for i, (track, artist) in enumerate(rows, 1):
        yt_artist, _yt_track = _yt_meta(track.source_url)
        if not yt_artist:
            sin_datos += 1
            print(f"[{i}/{len(rows)}] ---- {artist.name[:28]} · YouTube no da artista")
            continue

        nuevo = _primero(yt_artist)
        if genres_svc._norm_tight(nuevo) == genres_svc._norm_tight(artist.name):
            igual += 1
            continue

        # Que alguien más lo conozca antes de escribirlo.
        genero = genres_svc.resolve(nuevo, track.title)
        if genero is None:
            rechazados += 1
            print(f"[{i}/{len(rows)}] xxxx {artist.name[:24]} → {nuevo[:24]} · sin confirmar, se deja")
            continue

        cambios.append((track.id, artist.name, nuevo, genero))
        print(f"[{i}/{len(rows)}] OK   {artist.name[:24]} → {nuevo[:24]}  ({genero})")

    if args.apply and cambios:
        import mutagen

        errores = []
        with Session(engine) as session:
            for tid, _viejo, nuevo, genero in cambios:
                track = session.get(Track, tid)
                if track is None:
                    continue
                path = settings.music_dir / track.file_path
                try:
                    audio = mutagen.File(path, easy=True)
                    if audio is None:
                        raise ValueError("no es un fichero de audio")
                    if audio.tags is None:
                        audio.add_tags()
                    audio["artist"] = nuevo
                    # Ya que sabemos el género de paso, se escribe también: nos
                    # ahorra una vuelta entera del backfill sobre estas pistas.
                    if not track.genre and genero:
                        audio["genre"] = genero
                    audio.save()
                except Exception as e:
                    errores.append((tid, str(e)))
                    continue
                track.artist_id = _get_or_create_artist(session, nuevo).id
                if not track.genre and genero:
                    track.genre = genero
                session.add(track)
            session.commit()
        if errores:
            print(f"\n{len(errores)} errores al escribir:")
            for tid, err in errores:
                print(f"  #{tid}: {err}")

    print()
    print(f"artistas corregidos    : {len(cambios)}")
    print(f"ya estaban bien        : {igual}")
    print(f"YouTube no da artista  : {sin_datos}")
    print(f"rechazados sin confirmar: {rechazados}")
    if not args.apply:
        print("\nsimulacro: no se ha tocado ni un fichero ni una fila")
    return 0


if __name__ == "__main__":
    sys.exit(main())
