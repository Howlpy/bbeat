"""Devuelve su artista real a las pistas que quedaron como genérico.

El importador antiguo dejaba dos rastros distintos, y cada uno se arregla de una
forma:

- **Various Artists**: vinieron de playlists de Spotify. El artista real sigue
  guardado en la fila de `jobs` que las descargó (`jobs.artist`), así que se
  recupera exacto, sin adivinar ni salir a la red.
- **Unknown Artist**: subidas a mano, con el artista dentro del título
  (`"Fourward, Mefjus - Everytime"`). Se parte por el primer " - ". Esto sí es
  heurística, así que lleva guardas y se puede revisar antes con `--dry-run`.

Se escribe el TAG del fichero además de la base de datos, y en ese orden. El tag
manda: `scanner._index_one()` reconstruye `artist_id` desde él en cada escaneo,
así que un cambio solo-en-BD se borraría en la siguiente pasada.

No se mueve ningún fichero. La ruta en disco conserva la carpeta antigua, que es
cosmética y cambiarla implicaría mover 118 ficheros para nada.

Uso:
    python -m scripts.fix_unknown_artists                 # simulacro
    python -m scripts.fix_unknown_artists --apply
    python -m scripts.fix_unknown_artists --solo-jobs     # solo los exactos
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import Artist, Job, Track
from app.services import genres as genres_svc
from app.services.scanner import _get_or_create_artist

GENERICOS = ("Various Artists", "Unknown Artist")

# Trozos que delatan que lo de la izquierda del guion no es un artista.
BASURA = ("http", "www.", ".com", ".net", "yt1s", "youtube", "descargar", "free download")


def _plausible(nombre: str) -> bool:
    if not (2 <= len(nombre) <= 60):
        return False
    bajo = nombre.lower()
    if any(b in bajo for b in BASURA):
        return False
    return not (nombre.startswith(("[", "(")) or nombre.isdigit())


def artista_del_titulo(title: str, verificar: bool) -> Optional[tuple[str, str]]:
    """'Fourward, Mefjus - Everytime' -> ('Fourward, Mefjus', 'Everytime').

    El guion no dice de qué lado está el artista, y en esta biblioteca aparece
    de los dos: "Crazy Frog - Axel F" pero también
    "Pepas x Danza kuduro - Farruko Ft. Don Omar". Adivinar por la izquierda
    acierta la mayoría y falla en los mashups, donde deja de artista lo que en
    realidad son los nombres de las canciones.

    Con `verificar`, se le pregunta a Deezer por las dos orientaciones y se
    acepta la que confirme. Si no confirma ninguna, se deja la pista como está:
    un artista inventado es peor que "Unknown Artist".
    """
    idx = title.find(" - ")
    if idx < 0:
        return None
    izq, der = title[:idx].strip(), title[idx + 3 :].strip()
    if len(izq) < 2 or len(der) < 2:
        return None

    if not verificar:
        return (izq, der) if _plausible(izq) else None

    for artista, cancion in ((izq, der), (der, izq)):
        if _plausible(artista) and genres_svc._track_genre(artista, cancion):
            return artista, cancion
    return None


def escribir_tags(rel_path: str, artist: str, title: Optional[str]) -> Optional[str]:
    """Escribe artist (y title si cambia) en el fichero. Devuelve el error o None."""
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
        audio["artist"] = artist
        if title:
            audio["title"] = title
        audio.save()
    except Exception as e:
        return str(e)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="escribe de verdad")
    ap.add_argument("--solo-jobs", action="store_true", help="omite la heurística del título")
    ap.add_argument(
        "--sin-verificar",
        action="store_true",
        help="acepta el corte por el guion sin contrastarlo con Deezer (más cobertura, menos fiable)",
    )
    args = ap.parse_args()

    with Session(engine) as session:
        genericos = session.exec(select(Artist).where(Artist.name.in_(GENERICOS))).all()
        ids_genericos = [a.id for a in genericos]
        if not ids_genericos:
            print("no hay artistas genéricos: nada que hacer")
            return 0
        rows = session.exec(
            select(Track, Artist)
            .join(Artist, Artist.id == Track.artist_id)
            .where(Track.artist_id.in_(ids_genericos))
            .order_by(Track.id)
        ).all()

        # El artista original de cada pista, tal como lo trajo Spotify.
        jobs = {
            j.result_track_id: j.artist
            for j in session.exec(
                select(Job).where(Job.result_track_id.is_not(None))
            ).all()
            if j.artist and j.artist.strip() and j.artist not in GENERICOS
        }

    modo = "APLICANDO" if args.apply else "SIMULACRO (usa --apply para escribir)"
    verif = "sin verificar" if args.sin_verificar else "cortes verificados contra Deezer"
    print(f"{len(rows)} pistas con artista genérico · {modo} · {verif}\n")

    plan: list[tuple[int, str, str, str, Optional[str], str]] = []
    for track, artist in rows:
        real = jobs.get(track.id)
        if real:
            plan.append((track.id, artist.name, track.title, real, None, "job"))
            continue
        if args.solo_jobs:
            continue
        partido = artista_del_titulo(track.title, not args.sin_verificar)
        if partido:
            plan.append((track.id, artist.name, track.title, partido[0], partido[1], "título"))

    por_job = sum(1 for p in plan if p[5] == "job")
    por_titulo = len(plan) - por_job
    sin_arreglo = len(rows) - len(plan)

    for tid, viejo, titulo, nuevo, nuevo_titulo, origen in plan:
        marca = "·" if origen == "job" else "~"
        extra = f'  título → "{nuevo_titulo}"' if nuevo_titulo else ""
        print(f'{marca} #{tid:<5} [{viejo[:7]}] "{titulo[:40]}"\n    artista → {nuevo}{extra}')

    if args.apply:
        errores = []
        with Session(engine) as session:
            for tid, _viejo, _titulo, nuevo, nuevo_titulo, _origen in plan:
                track = session.get(Track, tid)
                if track is None:
                    continue
                err = escribir_tags(track.file_path, nuevo, nuevo_titulo)
                if err:
                    errores.append((tid, err))
                    continue
                # La BD solo después del tag: si se hiciera al revés, un fallo de
                # disco dejaría la base diciendo algo que el fichero no dice, y el
                # siguiente escaneo lo revertiría en silencio.
                track.artist_id = _get_or_create_artist(session, nuevo).id
                if nuevo_titulo:
                    track.title = nuevo_titulo
                session.add(track)
            session.commit()
        if errores:
            print(f"\n{len(errores)} errores al escribir:")
            for tid, err in errores:
                print(f"  #{tid}: {err}")

    print()
    print(f"exactos (desde jobs)   : {por_job}")
    print(f"heurística del título  : {por_titulo}")
    print(f"sin arreglo posible    : {sin_arreglo}")
    if not args.apply:
        print("\nsimulacro: no se ha tocado ni un fichero ni una fila")
    return 0


if __name__ == "__main__":
    sys.exit(main())
