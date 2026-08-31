"""Repara las pistas cuyo artista es "Various Artists" / "Unknown Artist".

En las subidas a mano el artista real suele venir dentro del título, al estilo
"Gydra - Scourge". Este script lo extrae y lo VERIFICA antes de tocar nada:

1. Contra la propia biblioteca: si "Gydra" ya existe como artista, es él.
2. Contra Deezer por pista (artista + título): confirma artista Y canción.
3. Contra Deezer por artista, como último recurso.

Un título que no trae separador, o cuya parte izquierda no la confirma nadie,
se queda como está y sale en el informe para repasarlo a mano. Renombrar con
una corazonada es peor que no renombrar: "Killing In The Name - Remix" NO es
un artista llamado Killing In The Name.

Aplicar usa library_svc.edit_track — el mismo camino que editar desde la UI:
recoloca el fichero en disco, reescribe los tags y actualiza la BD. Las
playlists no se ven afectadas (la pertenencia vive en album_tracks).

Uso:
    python -m scripts.repair_various_artists              # simulacro
    python -m scripts.repair_various_artists --apply
    python -m scripts.repair_various_artists --limit 20
"""
from __future__ import annotations

import argparse
import re
import sys

from sqlmodel import Session, select

from app.db import engine
from app.models import Artist, Track
from app.services import genres as genres_svc
from app.services import library as library_svc


def _verificar(left: str, right: str, artistas_db: dict[str, str]) -> tuple[str, str] | None:
    """Devuelve (nombre canónico, cómo se verificó), o None si nadie lo confirma."""
    key = genres_svc._norm_tight(left)

    # 1. Ya existe en la biblioteca: usar SU casing evita duplicar artistas
    #    ("gydra" y "Gydra" serían dos filas distintas de cara al usuario).
    if key in artistas_db:
        return artistas_db[key], "biblioteca"

    # 2. Deezer conoce la canción de ese artista: confirma ambos a la vez.
    data = genres_svc._client.get(
        "/search",
        params={"q": f'artist:"{left}" track:"{genres_svc.search_title(right)}"', "limit": 5},
    )
    for item in (data or {}).get("data", []):
        nombre = (item.get("artist") or {}).get("name", "")
        if genres_svc._norm_tight(nombre) == key:
            return nombre, "deezer-pista"

    # 3. Al menos el artista existe en Deezer con ese nombre exacto.
    nombre = _artista_en_deezer(left)
    if nombre:
        return nombre, "deezer-artista"

    return None


def _artista_en_deezer(nombre: str) -> str | None:
    """El nombre exacto (normalizado) como artista de Deezer, o None."""
    key = genres_svc._norm_tight(nombre)
    data = genres_svc._client.get("/search/artist", params={"q": nombre, "limit": 5})
    for hit in (data or {}).get("data", []):
        if genres_svc._norm_tight(hit.get("name", "")) == key:
            return hit["name"]
    return None


# La duración puede desviarse un poco entre el rip y el catálogo (silencios,
# fundidos). Cuatro segundos separan versiones de verdad (remix, directo) sin
# dejar pasar la misma canción.
_TOLERANCIA_DURACION_S = 4


def _por_titulo_y_duracion(title: str, duration_ms: int | None) -> str | None:
    """Artista según Deezer buscando SOLO por título, anclado por la duración.

    Para las pistas cuyo título no trae artista ("Veridis Quo", "SLEEPY").
    La duración es casi una huella: un "Veridis Quo" que dura lo que el
    nuestro es el de Daft Punk. La regla de seguridad es la unanimidad:
    si dos artistas distintos tienen una canción con ese título y esa
    duración ("Angel"...), es ambiguo y no se toca.
    """
    if not duration_ms:
        return None
    q = genres_svc.search_title(title)
    data = genres_svc._client.get("/search", params={"q": f'track:"{q}"', "limit": 25})
    objetivo = duration_ms / 1000
    quiero = genres_svc._norm(q)
    candidatos: dict[str, str] = {}
    for item in (data or {}).get("data", []):
        if abs((item.get("duration") or 0) - objetivo) > _TOLERANCIA_DURACION_S:
            continue
        # El título tiene que casar de verdad, no solo contener la búsqueda.
        titulos = {genres_svc._norm(item.get("title") or ""), genres_svc._norm(item.get("title_short") or "")}
        if quiero not in titulos:
            continue
        nombre = (item.get("artist") or {}).get("name", "")
        if nombre:
            candidatos[genres_svc._norm_tight(nombre)] = nombre
    if len(candidatos) == 1:
        return next(iter(candidatos.values()))
    return None


# "Impak, The Clamps" o "Gydra & Fatloaf" no existen como artista en ningún
# catálogo, pero su artista PRINCIPAL sí. Es la misma convención del resto de
# bbeat: una pista tiene un artista y los invitados van en el título.
_SEPARADORES_COLAB = re.compile(r"\s*(?:,|;|\s[xX]\s|\s&\s|\sft\.?\s|\sfeat\.?\s)\s*")


def _artista_principal(left: str) -> str | None:
    """El primer nombre de una ristra de colaboradores, o None si no hay ristra."""
    primero = _SEPARADORES_COLAB.split(left)[0].strip()
    return primero if primero and primero != left else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="escribe de verdad (por defecto simulacro)")
    ap.add_argument("--limit", type=int, default=0, help="procesa como mucho N pistas")
    args = ap.parse_args()

    with Session(engine) as session:
        filas = session.exec(
            select(Track.id, Track.title, Artist.name, Track.duration_ms)
            .join(Artist, Artist.id == Track.artist_id)
            .order_by(Track.id)
        ).all()
        artistas_db = {
            genres_svc._norm_tight(a.name): a.name
            for a in session.exec(select(Artist)).all()
            # Un vacío no puede "verificar" a otro.
            if genres_svc._norm_tight(a.name) not in genres_svc._ARTISTAS_VACIOS
        }

    rotas = [
        (tid, title, aname, dur)
        for tid, title, aname, dur in filas
        if genres_svc._norm_tight(aname) in genres_svc._ARTISTAS_VACIOS
    ]
    if args.limit:
        rotas = rotas[: args.limit]

    if not rotas:
        print("no hay pistas con artista vacío")
        return 0

    modo = "APLICANDO" if args.apply else "SIMULACRO (usa --apply para escribir)"
    print(f"{len(rotas)} pistas con artista vacío · {modo}\n")

    arregladas: list[tuple[int, str, str]] = []
    sin_separador: list[tuple[int, str]] = []
    sin_verificar: list[tuple[int, str]] = []
    errores: list[tuple[int, str, str]] = []

    for i, (tid, title, aname, dur) in enumerate(rotas, 1):
        partido = genres_svc._split_artist_from_title(title)
        if partido is None:
            # El título es solo el título ("Veridis Quo"): buscarlo en Deezer
            # anclado por la duración, que es casi una huella de la pista.
            nombre = _por_titulo_y_duracion(title, dur)
            if nombre is None:
                sin_separador.append((tid, title))
                print(f"[{i}/{len(rotas)}] ····  {title[:64]}  (sin separador)")
                continue
            if args.apply:
                res = library_svc.edit_track(tid, artist=nombre)
                if not res.get("ok"):
                    errores.append((tid, title, res.get("reason", "error")))
                    print(f"[{i}/{len(rotas)}] ERR   {title[:56]} · {res.get('reason')}")
                    continue
                artistas_db.setdefault(genres_svc._norm_tight(nombre), nombre)
            arregladas.append((tid, title, nombre))
            print(f"[{i}/{len(rotas)}] {'titulo+duracion':<14} {nombre[:24]:<24} — {title[:44]}")
            continue
        left, right = partido

        ver = _verificar(left, right, artistas_db)
        if ver is None:
            # Segundo intento: el artista principal de una colaboración.
            principal = _artista_principal(left)
            if principal:
                ver = _verificar(principal, right, artistas_db)
                if ver:
                    ver = (ver[0], ver[1] + "+principal")
        if ver is None:
            sin_verificar.append((tid, title))
            print(f"[{i}/{len(rotas)}] ????  {title[:64]}  ('{left[:30]}' no confirmado)")
            continue
        nombre, via = ver

        # La vía débil (el artista existe, pero no consta esa canción suya)
        # necesita un contra-chequeo: si el lado derecho TAMBIÉN parece un
        # artista, el título probablemente va al revés ("Pepas x Danza kuduro -
        # Farruko Ft. Don Omar" es canción-artista, no artista-canción) y
        # renombrar sería inventar. Ambiguo → se queda para revisar a mano.
        if "deezer-artista" in via:
            # Primero limpiar coletillas ("(AGA x Viterlo Mashup)") y luego
            # quedarse con el primer nombre de la ristra.
            limpio = genres_svc.search_title(right)
            reves = _artista_principal(limpio) or limpio
            if _artista_en_deezer(reves):
                sin_verificar.append((tid, title))
                print(f"[{i}/{len(rotas)}] ????  {title[:64]}  (ambiguo: '{reves[:24]}' también es artista)")
                continue

        if args.apply:
            res = library_svc.edit_track(tid, title=right, artist=nombre)
            if not res.get("ok"):
                errores.append((tid, title, res.get("reason", "error")))
                print(f"[{i}/{len(rotas)}] ERR   {title[:56]} · {res.get('reason')}")
                continue
            # El artista nuevo pasa a poder verificar a los siguientes.
            artistas_db.setdefault(genres_svc._norm_tight(nombre), nombre)

        arregladas.append((tid, title, nombre))
        print(f"[{i}/{len(rotas)}] {via:<14} {nombre[:24]:<24} — {right[:44]}")

    print()
    print(f"arregladas    : {len(arregladas)}/{len(rotas)}")
    print(f"sin separador : {len(sin_separador)}  (se quedan como están)")
    print(f"sin verificar : {len(sin_verificar)}  (revisar a mano)")
    if errores:
        print(f"errores       : {len(errores)}")
    if not args.apply:
        print("\nsimulacro: no se ha tocado ni un fichero ni una fila")
    elif arregladas:
        print(
            "\nLas pistas arregladas siguen sin género: pásales el backfill\n"
            "  python -m scripts.backfill_genres --apply"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
