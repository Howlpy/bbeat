"""Rellena el género de las pistas que no lo tienen.

El género se escribe en el TAG del fichero además de en la base de datos, y en
ese orden. El tag es la fuente de la verdad: `scanner._index_one()` reconstruye
`tracks.genre` desde el tag en cada escaneo, así que un relleno que solo tocara
la BD se borraría solo en la siguiente pasada.

Solo toca pistas con `genre IS NULL`. Eso hace el script reejecutable sin
riesgo: lo que ya tenga género —puesto a mano o por una pasada anterior— no se
pisa nunca.

Uso:
    python -m scripts.backfill_genres                  # simulacro (no toca nada)
    python -m scripts.backfill_genres --apply
    python -m scripts.backfill_genres --apply --limit 50
    python -m scripts.backfill_genres --json informe.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from collections import Counter

from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import Album, Artist, Track
from app.services import genres as genres_svc


def _album_majorities(session: Session) -> dict[int, str]:
    """Género mayoritario por álbum REAL (kind='album'), para heredarlo.

    Un álbum de verdad es homogéneo: si 8 de sus 10 pistas son rap, las 2 que
    la cascada no resolvió casi seguro también lo son. Es un respaldo local,
    sin red, y más fino que el del artista (un disco concreto no cruza géneros
    como cruza una discografía).

    Las playlists NO entran: son bolsas mixtas por definición y heredar ahí
    inventaría géneros. Y los mínimos son los mismos que el respaldo por
    artista: al menos 2 votos y la mitad del total, para que una sola pista
    etiquetada no decida por todo el disco.
    """
    rows = session.exec(
        select(Track.album_id, Track.genre)
        .join(Album, Album.id == Track.album_id)
        .where(Album.kind == "album", Track.genre.is_not(None))
    ).all()
    votos: dict[int, Counter[str]] = {}
    for album_id, genre in rows:
        g = (genre or "").strip().lower()
        if g and album_id is not None:
            votos.setdefault(album_id, Counter())[g] += 1
    out: dict[int, str] = {}
    for album_id, c in votos.items():
        top, n = c.most_common(1)[0]
        if n >= 2 and n / sum(c.values()) >= 0.5:
            out[album_id] = top
    return out


def _write_tag(rel_path: str, genre: str) -> Optional[str]:
    """Escribe el tag de género en el fichero. Devuelve el error, o None si fue bien."""
    import mutagen

    path = settings.music_dir / rel_path
    if not path.is_file():
        return "el fichero no está en disco"
    try:
        audio = mutagen.File(path, easy=True)
        if audio is None:
            return "no es un fichero de audio reconocible"
        if audio.tags is None:
            audio.add_tags()
        audio["genre"] = genre
        audio.save()
    except Exception as e:
        return str(e)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="escribe de verdad (por defecto simulacro)")
    ap.add_argument("--limit", type=int, default=0, help="procesa como mucho N pistas")
    ap.add_argument(
        "--reprocesar",
        action="store_true",
        help="vuelve a resolver TODAS las pistas, no solo las que no tienen género "
             "(para cuando mejora la cascada). Solo escribe si el resultado cambia.",
    )
    ap.add_argument("--json", dest="json_out", help="vuelca el informe a un fichero")
    ap.add_argument(
        "--no-artist-fallback",
        action="store_true",
        help="solo género por pista, sin caer al del artista",
    )
    args = ap.parse_args()

    with Session(engine) as session:
        stmt = (
            select(Track, Artist, Album.title)
            .join(Artist, Artist.id == Track.artist_id)
            .outerjoin(Album, Album.id == Track.album_id)
            .order_by(Track.id)
        )
        if not args.reprocesar:
            stmt = stmt.where(Track.genre.is_(None))
        rows = session.exec(stmt).all()
        herencia = _album_majorities(session)

    if args.limit:
        rows = rows[: args.limit]

    total = len(rows)
    if not total:
        print("no hay pistas que procesar")
        return 0

    modo = "APLICANDO" if args.apply else "SIMULACRO (usa --apply para escribir)"
    print(f"{total} pistas sin género · {modo}\n")

    if not settings.lastfm_api_key:
        # Sin Last.fm no solo se pierde la mejor fuente: también las reglas
        # que corrigen a Deezer (artista unánime, consenso) dependen de sus
        # tags. La calidad baja de forma visible — medido: "Corrido Espacial"
        # de Kidd Keo sale "electronica" sin la clave y "rap" con ella.
        print(
            "AVISO: BBEAT_LASTFM_API_KEY no está configurada. La cascada corre\n"
            "sin su mejor fuente y sin las correcciones por artista; espera\n"
            "bastantes más géneros vacíos o imprecisos. La clave es gratuita:\n"
            "https://www.last.fm/api/account/create\n"
        )

    resueltas: list[dict] = []
    sin_genero: list[dict] = []
    errores: list[dict] = []

    heredadas = 0
    for i, (track, artist, album_title) in enumerate(rows, 1):
        genre = genres_svc.resolve(
            artist.name,
            track.title,
            album=album_title,
            allow_artist_fallback=not args.no_artist_fallback,
        )
        # Lo que la red no resuelve puede resolverlo el propio álbum: si el
        # resto del disco ya tiene un género mayoritario, la pista lo hereda.
        if not genre and track.album_id in herencia:
            genre = herencia[track.album_id]
            heredadas += 1
        etiqueta = f"{artist.name} — {track.title}"

        if not genre:
            sin_genero.append({"id": track.id, "artista": artist.name, "titulo": track.title})
            if not args.reprocesar:
                print(f"[{i}/{total}] ---- {etiqueta[:66]}")
            continue

        if genre == track.genre:
            # Ya estaba bien: ni se toca el fichero ni se imprime ruido.
            resueltas.append({"id": track.id, "artista": artist.name,
                              "titulo": track.title, "genero": genre})
            continue

        if args.apply:
            err = _write_tag(track.file_path, genre)
            if err:
                errores.append({"id": track.id, "titulo": track.title, "error": err})
                print(f"[{i}/{total}] ERR  {etiqueta[:60]} · {err}")
                continue
            # La BD solo se toca si el tag se escribió: si se hiciera al revés,
            # un fallo de disco dejaría la base diciendo algo que el fichero no
            # dice, y el siguiente escaneo lo revertiría en silencio.
            with Session(engine) as session:
                fresh = session.get(Track, track.id)
                if fresh is not None:
                    fresh.genre = genre
                    session.add(fresh)
                    session.commit()

        resueltas.append(
            {"id": track.id, "artista": artist.name, "titulo": track.title, "genero": genre}
        )
        antes = f"{track.genre} -> " if track.genre else ""
        print(f"[{i}/{total}] {antes}{genre:<12} {etiqueta[:56]}")

    print()
    print(f"resueltas   : {len(resueltas)}/{total} ({100 * len(resueltas) // total}%)")
    if heredadas:
        print(f"  (de ellas, {heredadas} heredadas del género mayoritario de su álbum)")
    print(f"sin género  : {len(sin_genero)}")
    if errores:
        print(f"errores     : {len(errores)}")

    reparto: dict[str, int] = {}
    for r in resueltas:
        reparto[r["genero"]] = reparto.get(r["genero"], 0) + 1
    if reparto:
        print("\nreparto:")
        for g, n in sorted(reparto.items(), key=lambda kv: -kv[1]):
            print(f"  {g:<14} {n}")

    if not args.apply:
        print("\nsimulacro: no se ha tocado ni un fichero ni una fila")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {"resueltas": resueltas, "sin_genero": sin_genero, "errores": errores},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\ninforme en {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
