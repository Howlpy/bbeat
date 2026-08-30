"""Resolución de género por pista usando la API pública de Deezer (sin key).

Deezer no expone el género de una pista: lo expone del **álbum**. Así que la
pista se busca por artista + título y hereda el género de *su* álbum, que es
distinto —y mejor— que el del artista.

Cascada: pista → artista (respaldo) → None. Medido sobre 30 pistas reales de la
biblioteca: 80 % por pista, 90 % con el respaldo. Ver docs/plan-generos.md.

El género se guarda en la PISTA y acaba en el tag del fichero, que es la fuente
de la verdad: `organizer.write_tags()` lo escribe y `scanner` lo vuelve a leer.
"""
from __future__ import annotations

import logging
import threading
import time
import unicodedata
from collections import Counter
from typing import Optional

import httpx

log = logging.getLogger("bbeat.genres")

DEEZER = "https://api.deezer.com"
HEADERS = {"User-Agent": "Bbeat/0.1 (https://github.com/Howlpy/bbeat)"}
TIMEOUT = 15.0

# El límite público de Deezer ronda 50 peticiones / 5 s por IP. Con este
# espaciado las pruebas nunca lo tocaron.
REQUEST_SPACING_S = 0.15

# Respaldo por artista: hace falta más de un voto para creerse el resultado.
# Sin el mínimo de votos, Powerwolf entraba como "Clásica" al 100 % — un único
# álbum sinfónico decidiendo por toda la discografía.
ARTIST_ALBUMS_SAMPLE = 6
ARTIST_MIN_VOTES = 2
ARTIST_MIN_SHARE = 0.5

# ─── Vocabulario canónico ────────────────────────────────────────
# Deezer usa cuatro etiquetas para dos ideas ("Electro", "Dance",
# "Techno/House", "Drum & Bass"). Mapear a un vocabulario cerrado es lo que
# permite preguntar "top de rap de la semana" con una sola comparación, en vez
# de una lista de cadenas que se rompe cuando Deezer renombra una etiqueta.
# Las claves se escriben TAL CUAL las manda Deezer y se normalizan abajo. No
# escribirlas ya normalizadas a mano: "Rap/Hip Hop" normaliza a "rap hip hop",
# y una tabla escrita con la barra dentro no casa jamás — justo con el género
# más frecuente de esta biblioteca.
CANONICAL: dict[str, str] = {
    "Rap/Hip Hop": "rap",
    "Hip Hop": "rap",
    "Rap": "rap",
    "Reggaeton": "reggaeton",
    "Latino": "latino",
    "Flamenco": "latino",
    "Salsa": "latino",
    "Música latina": "latino",
    "Electro": "electronica",
    "Dance": "electronica",
    "Techno/House": "electronica",
    "Drum & Bass": "electronica",
    "Dubstep": "electronica",
    "Rock": "rock",
    "Hard Rock": "rock",
    "Alternativo": "rock",
    "Indie Pop/Rock": "rock",
    "Indie Rock": "rock",
    "Punk": "rock",
    "Metal": "metal",
    "Metal extremo": "metal",
    "Pop": "pop",
    "Pop indie": "pop",
    "R&B": "rnb",
    "Soul & Funk": "rnb",
    "Jazz": "jazz",
    "Blues": "blues",
    "Clásica": "clasica",
    "Banda sonora": "bso",
    "Films/Games": "bso",
}


def canonicalize(deezer_genre: Optional[str]) -> Optional[str]:
    """Etiqueta de Deezer → vocabulario de bbeat. None si no la conocemos.

    Devolver None (en vez de 'otros') es deliberado: una etiqueta sin mapear es
    una que hay que añadir aquí a mano, y prefiero verla vacía a verla mal.
    """
    if not deezer_genre:
        return None
    return _LOOKUP.get(_norm(deezer_genre))


def _norm(s: str) -> str:
    """Minúsculas sin acentos ni signos, para comparar nombres."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() or c.isspace() else " " for c in s).split())


def _norm_tight(s: str) -> str:
    """Como _norm pero sin espacios: 'Eazy E' == 'Eazy-E'."""
    return _norm(s).replace(" ", "")


# Coletillas que arrastran los títulos venidos de YouTube y Spotify y que
# impiden que Deezer encuentre la pista: "- Remix", "(Vídeo Oficial)",
# "- Remaster 2015", "feat. X". Cortar por aquí es lo que sube la cobertura.
_TITLE_CUTS = (" - ", " (", " [", " feat", " ft.", " ft ", " featuring ")


def search_title(title: str) -> str:
    """Título limpio para buscar. Nunca deja menos de 4 caracteres."""
    out = title.strip()
    for sep in _TITLE_CUTS:
        idx = out.lower().find(sep)
        if idx > 3:
            out = out[:idx]
    return out.strip() or title.strip()


class _Client:
    """Cliente httpx compartido con espaciado y cachés.

    Las cachés importan de verdad en el backfill: muchas pistas comparten
    álbum, así que las consultas de álbum acaban siendo bastantes menos que las
    de pista.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._client: Optional[httpx.Client] = None
        self.album_cache: dict[int, list[str]] = {}
        self.artist_cache: dict[str, Optional[str]] = {}

    def get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        """GET a Deezer. None ante cualquier problema: esto nunca debe tumbar
        una descarga por no saber el género."""
        with self._lock:
            wait = REQUEST_SPACING_S - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            if self._client is None:
                self._client = httpx.Client(timeout=TIMEOUT, headers=HEADERS)
            client = self._client
        try:
            r = client.get(DEEZER + path, params=params)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.debug("deezer %s falló: %s", path, e)
            return None
        # Deezer devuelve 200 con {"error": {...}} cuando no encuentra algo.
        if isinstance(data, dict) and data.get("error"):
            return None
        return data

    def album_genres(self, album_id: int) -> list[str]:
        if album_id not in self.album_cache:
            d = self.get(f"/album/{album_id}") or {}
            self.album_cache[album_id] = [
                g["name"] for g in (d.get("genres") or {}).get("data", []) if g.get("name")
            ]
        return self.album_cache[album_id]

    def reset(self) -> None:
        self.album_cache.clear()
        self.artist_cache.clear()


_client = _Client()


def _track_genre(artist: str, title: str) -> Optional[str]:
    """Género del álbum al que pertenece esta pista concreta en Deezer."""
    if not artist or not title:
        return None
    query = f'artist:"{artist}" track:"{search_title(title)}"'
    data = _client.get("/search", params={"q": query, "limit": 5})
    want = _norm_tight(artist)
    for item in (data or {}).get("data", []):
        # El artista debe coincidir: Deezer devuelve resultados laxos y sin esta
        # comprobación se cuela otro artista con canción del mismo título.
        if _norm_tight((item.get("artist") or {}).get("name", "")) != want:
            continue
        album_id = (item.get("album") or {}).get("id")
        if not album_id:
            continue
        genres = _client.album_genres(int(album_id))
        if genres:
            return genres[0]
    return None


def _artist_genre(name: str) -> Optional[str]:
    """Respaldo: género mayoritario del artista, por votación de sus álbumes.

    Solo se usa cuando la pista no se pudo resolver, y con guardas: el nombre
    tiene que coincidir exactamente (Deezer devolvía 'Alok (IN)' para 'Alok', y
    'Till I Collapse' para un artista basura llamado 'til i collapse').
    """
    if not name:
        return None
    key = _norm_tight(name)
    if key in _client.artist_cache:
        return _client.artist_cache[key]

    result: Optional[str] = None
    data = _client.get("/search/artist", params={"q": name, "limit": 1})
    hits = (data or {}).get("data") or []
    if hits and _norm_tight(hits[0].get("name", "")) == key:
        albums = _client.get(
            f"/artist/{hits[0]['id']}/albums", params={"limit": ARTIST_ALBUMS_SAMPLE}
        )
        votes: Counter[str] = Counter()
        for album in (albums or {}).get("data", []):
            for g in _client.album_genres(int(album["id"])):
                votes[g] += 1
        if votes:
            top, n = votes.most_common(1)[0]
            if n >= ARTIST_MIN_VOTES and n / sum(votes.values()) >= ARTIST_MIN_SHARE:
                result = top

    _client.artist_cache[key] = result
    return result


# Pistas cuyo artista no dice nada. Suelen venir de subidas sueltas y llevan el
# artista real dentro del título, al estilo "Gydra - Scourge".
_ARTISTAS_VACIOS = {"unknownartist", "variousartists", "va", ""}


def _split_artist_from_title(title: str) -> Optional[tuple[str, str]]:
    """'Gydra & Fatloaf - Sphere (Original Mix)' -> ('Gydra & Fatloaf', 'Sphere')."""
    idx = title.find(" - ")
    if idx < 2:
        return None
    left, right = title[:idx].strip(), title[idx + 3 :].strip()
    if not left or not right:
        return None
    return left, right


def resolve(artist: str, title: str, *, allow_artist_fallback: bool = True) -> Optional[str]:
    """Género canónico de una pista, o None si no se puede decidir.

    Nunca lanza: si Deezer no responde, la canción se queda sin género y ya se
    rellenará en otra pasada.
    """
    try:
        raw = _track_genre(artist, title)
        if raw is None and allow_artist_fallback:
            raw = _artist_genre(artist)

        # Último recurso para las pistas sin artista de verdad: sacarlo del
        # título. Sin esto, todo lo subido a mano se queda sin género para
        # siempre, porque "Unknown Artist" no existe en ningún catálogo.
        if raw is None and _norm_tight(artist) in _ARTISTAS_VACIOS:
            partido = _split_artist_from_title(title)
            if partido:
                real_artist, real_title = partido
                raw = _track_genre(real_artist, real_title)
                if raw is None and allow_artist_fallback:
                    raw = _artist_genre(real_artist)

        return canonicalize(raw)
    except Exception:
        log.exception("resolviendo género de %s — %s", artist, title)
        return None


def resolve_meta(meta) -> Optional[str]:
    """Como resolve(), pero tomando artista y título de un TrackMeta."""
    return resolve(meta.primary_artist, meta.title)


def reset_cache() -> None:
    """Para los scripts de larga duración, si hiciera falta soltar memoria."""
    _client.reset()


# Se construye al final porque _norm() se define más abajo que la tabla.
_LOOKUP: dict[str, str] = {_norm(k): v for k, v in CANONICAL.items()}
