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

from app.config import settings

log = logging.getLogger("bbeat.genres")

DEEZER = "https://api.deezer.com"
ITUNES = "https://itunes.apple.com/search"
WIKIDATA = "https://www.wikidata.org/w/api.php"
LASTFM = "https://ws.audioscrobbler.com/2.0/"
HEADERS = {"User-Agent": "Bbeat/0.1 (https://github.com/Howlpy/bbeat)"}
TIMEOUT = 15.0

# El límite público de Deezer ronda 50 peticiones / 5 s por IP. Con este
# espaciado las pruebas nunca lo tocaron.
REQUEST_SPACING_S = 0.15

# Respaldo por artista: hace falta más de un voto para creerse el resultado.
# Sin el mínimo de votos, Powerwolf entraba como "Clásica" al 100 % — un único
# álbum sinfónico decidiendo por toda la discografía.
ARTIST_ALBUMS_SAMPLE = 6
ARTIST_TOP_SAMPLE = 10
ARTIST_MIN_VOTES = 2
ARTIST_MIN_SHARE = 0.5
# Cuánto del peso de los tags tiene que llevarse un género para que el artista
# pueda corregir a Deezer. Medido: Kidd Keo trap se lleva el 0.87.
ARTISTA_UNANIME = 0.8

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
    # Los géneros de primer nivel, tal cual los devuelve /genre. OJO: la API
    # responde en español ("Películas/Juegos", no "Films/Games").
    "Pop": "pop",
    "Rap/Hip Hop": "rap",
    "Reggaeton": "reggaeton",
    "Rock": "rock",
    "Dance": "electronica",
    "R&B": "rnb",
    "Alternativo": "rock",
    "Electro": "electronica",
    "Folk": "folk",
    "Reggae": "reggae",
    "Jazz": "jazz",
    "Salsa": "latino",
    "Clásica": "clasica",
    "Metal": "metal",
    "Películas/Juegos": "bso",
    "Soul & Funk": "rnb",
    "Blues": "blues",
    "Cumbia": "latino",
    "Latino": "latino",
    "Música Brasileña": "latino",
    "Música africana": "mundo",
    "Música asiática": "mundo",
    "Música india": "mundo",
    "Niños": "infantil",
    # Subgéneros que aparecen a nivel de álbum aunque no estén en /genre.
    "Hip Hop": "rap",
    "Rap": "rap",
    "Trap": "rap",
    "Techno/House": "electronica",
    "Drum & Bass": "electronica",
    "Dubstep": "electronica",
    "Electronic": "electronica",
    "Hard Rock": "rock",
    "Indie Pop/Rock": "rock",
    "Indie Rock": "rock",
    "Punk": "rock",
    "Metal extremo": "metal",
    "Bandas sonoras": "bso",
}


# iTunes nombra los géneros a su manera ("Hip-Hop/Rap", no "Rap/Hip Hop"), así
# que necesita su propia tabla. Cubre cosas que Deezer no indexa: sellos
# pequeños de electrónica sobre todo.
ITUNES_CANONICAL: dict[str, str] = {
    "Hip-Hop/Rap": "rap",
    "Hip Hop/Rap": "rap",
    "Rap": "rap",
    "Electronic": "electronica",
    "Dance": "electronica",
    "Techno": "electronica",
    "House": "electronica",
    "Drum & Bass": "electronica",
    "Drum and Bass": "electronica",
    "Dubstep": "electronica",
    "Breakbeat": "electronica",
    "Trance": "electronica",
    "Rock": "rock",
    "Alternative": "rock",
    "Indie Rock": "rock",
    "Punk": "rock",
    "Hard Rock": "rock",
    "Metal": "metal",
    "Heavy Metal": "metal",
    "Death Metal/Black Metal": "metal",
    "Pop": "pop",
    "Latin": "latino",
    "Latin Urban": "reggaeton",
    "Reggaeton y Hip-Hop": "reggaeton",
    "Reggaeton": "reggaeton",
    "Salsa y Tropical": "latino",
    "Flamenco": "latino",
    "R&B/Soul": "rnb",
    "Soul": "rnb",
    "Funk": "rnb",
    "Reggae": "reggae",
    "Jazz": "jazz",
    "Blues": "blues",
    "Classical": "clasica",
    "Soundtrack": "bso",
    "Folk": "folk",
    "Singer/Songwriter": "folk",
    "World": "mundo",
    "Worldwide": "mundo",
    "Children's Music": "infantil",
}


# Wikidata no usa un vocabulario cerrado: los géneros son entidades sueltas y
# las etiquetas vienen en español o inglés, con toda variante imaginable
# ("hip hop español", "trap latino", "rumba cubana", "hard rock"). Por eso aquí
# se busca por SUBCADENA y en orden: el primero que encaje gana.
#
# El orden es lo que hace que funcione. "trap latino" contiene "trap" y
# "latino"; es rap. "pop rap" es rap, no pop. Y "pop" va el último a propósito,
# porque es la etiqueta que todo el mundo usa cuando no sabe qué poner.
WIKIDATA_PATRONES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("hip hop", "hip-hop", "rap", "trap", "drill", "grime"), "rap"),
    (("reggaeton", "reguet", "perreo", "dembow"), "reggaeton"),
    (("metal", "thrash", "grindcore"), "metal"),
    (("house", "techno", "electro", "drum and bass", "drum'n'bass", "dubstep",
      "trance", "dance", "edm", "eurodance", "breakbeat", "makina", "hardstyle",
      "jungle", "ambient", "synthwave", "big beat"), "electronica"),
    (("reggae", "ska", "dancehall", "dub"), "reggae"),
    (("punk", "rock", "grunge", "indie", "alternativ", "alterlatino", "shoegaze",
      "hardcore", "metalcore"), "rock"),
    (("flamenco", "rumba", "salsa", "cumbia", "bachata", "merengue", "ranchera",
      "bolero", "copla", "tango", "mariachi", "vallenato", "latin"), "latino"),
    (("r&b", "rhythm and blues", "soul", "funk", "motown"), "rnb"),
    (("jazz", "bebop", "swing"), "jazz"),
    (("blues",), "blues"),
    (("clásic", "clasic", "classical", "ópera", "opera", "sinfón", "sinfon",
      "barroc", "baroque"), "clasica"),
    (("banda sonora", "soundtrack", "videojuego", "video game", "film score"), "bso"),
    (("folk", "cantautor", "country", "bluegrass", "canción de autor"), "folk"),
    (("world", "músicas del mundo", "afrobeat", "k-pop", "j-pop"), "mundo"),
    (("pop",), "pop"),
)

# Solo nos vale la entidad si es una persona o grupo que hace música: buscando
# por nombre se pesca de todo, y un género colgado de la entidad equivocada es
# peor que no tener género.
WIKIDATA_MUSICAL = (
    "grupo", "banda", "dúo", "duo", "trío", "rapero", "rapera", "cantante",
    "músic", "compositor", "productor", "dj", "artista", "band", "rapper",
    "singer", "musician", "composer", "producer", "duet", "girl group",
    "boy band", "orquesta", "orchestra",
)


def canonicalize_wikidata(label: Optional[str]) -> Optional[str]:
    """Etiqueta de género de Wikidata → vocabulario de bbeat."""
    if not label:
        return None
    bajo = _norm(label)
    for agujas, destino in WIKIDATA_PATRONES:
        if any(a in bajo for a in agujas):
            return destino
    return None


def canonicalize_itunes(name: Optional[str]) -> Optional[str]:
    """Género de iTunes → vocabulario de bbeat.

    Primero la tabla exacta, y si no encaja, los mismos patrones por subcadena
    que Wikidata. Hace falta porque iTunes responde con los nombres de la tienda
    del país: "Hip-Hop", "Urbano latino", "Rock y Alternativo", "Pop Latino".
    Con solo la tabla en inglés, esas respuestas —que son correctas— se tiraban
    a la basura y la pista se quedaba sin género.
    """
    if not name:
        return None
    return _LOOKUP_ITUNES.get(_norm(name)) or canonicalize_wikidata(name)


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
        self.wikidata_cache: dict[str, Optional[str]] = {}
        self.lastfm_album_cache: dict[tuple, Optional[str]] = {}
        self.lastfm_track_cache: dict[tuple, Optional[str]] = {}
        # Cuán unánime fue la última votación de tags (0..1).
        self.ultima_fuerza: float = 0.0
        self.lastfm_artist_cache: dict[str, Optional[str]] = {}

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

    def get_json(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        """Como get() pero contra una URL completa (para APIs que no son Deezer)."""
        with self._lock:
            wait = REQUEST_SPACING_S - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            if self._client is None:
                self._client = httpx.Client(timeout=TIMEOUT, headers=HEADERS)
            client = self._client
        try:
            r = client.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.debug("%s falló: %s", url, e)
            return None

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
        self.wikidata_cache.clear()
        self.lastfm_album_cache.clear()
        self.lastfm_track_cache.clear()
        self.lastfm_artist_cache.clear()


_client = _Client()


# Respuestas que estas APIs sueltan cuando no han clasificado nada en serio.
# Son ciertas a medias —Sabaton "es" rock, Bad Bunny "es" latino— pero pierden
# justo la información que se busca. Si Wikidata tiene algo más concreto para
# ese artista, manda Wikidata.
GENEROS_VAGOS = frozenset({"pop", "rock", "latino"})


def _lastfm(metodo: str, params: dict) -> Optional[dict]:
    """Llamada a Last.fm. None si no hay clave configurada o si falla."""
    key = settings.lastfm_api_key
    if not key:
        return None
    return _client.get_json(
        LASTFM, {"method": metodo, "format": "json", "api_key": key,
                 "autocorrect": 1, **params}
    )


def _tags_a_genero(tags) -> Optional[str]:
    """Vota el género canónico entre unos tags de Last.fm, usando sus pesos.

    Los tags son libres y vienen mezclados con ruido —"spanish", "2022",
    "9 of 10 stars"—, pero traen un `count` de 0 a 100 que dice cuánta gente
    los puso. Votar con ese peso es lo que hace que Bad Bunny salga reggaeton
    (Reggaeton:100 frente a trap:72) y Kidd Keo rap (trap:100 frente a
    latin:7). El ruido no puntúa porque no se traduce a nada.
    """
    if isinstance(tags, dict):
        tags = [tags]
    votos: Counter[str] = Counter()
    for t in (tags or [])[:12]:
        canon = canonicalize_wikidata(t.get("name"))
        if canon:
            try:
                peso = int(t.get("count") or 1)
            except (TypeError, ValueError):
                peso = 1
            votos[canon] += max(peso, 1)
    if not votos:
        return None
    ganador, peso = votos.most_common(1)[0]
    total = sum(votos.values())
    # "Unánime" = el ganador se lleva casi todo el peso. En Last.fm el tag más
    # votado siempre vale 100, así que lo que distingue a un artista de un solo
    # género de uno que cruza es cuánto se lleva el resto.
    _client.ultima_fuerza = peso / total if total else 0.0
    return ganador


def _lastfm_album_tags(artist: str, album: str) -> Optional[str]:
    """Género según los tags de un álbum concreto en Last.fm."""
    clave = (_norm_tight(artist), _norm_tight(album))
    if clave in _client.lastfm_album_cache:
        return _client.lastfm_album_cache[clave]
    d = _lastfm("album.getinfo", {"artist": artist, "album": album})
    resultado = _tags_a_genero(((d or {}).get("album", {}).get("tags") or {}).get("tag", []))
    _client.lastfm_album_cache[clave] = resultado
    return resultado


def _lastfm_track_genre(artist: str, title: str, album_local: Optional[str]) -> Optional[str]:
    """Género de ESTA pista según Last.fm, por la vía más fina que haya.

    1. Los tags de la propia canción, si los tiene. Es lo ideal, pero en la
       práctica solo están puestos en clásicos muy tageados: funcionan para
       "Smells Like Teen Spirit" y ya no para "Get Lucky".
    2. Los tags del álbum REAL en el que salió, que Last.fm sabe a partir de
       artista + título. Esto es lo que de verdad funciona.
    3. Como último recurso, el nombre de álbum que tengamos guardado.

    El paso 2 importa más de lo que parece: los "álbumes" de esta biblioteca
    son en su mayoría playlists ("KIDD KEO TEMAZOS", "javi's greatest hits
    '25"), que no existen en ningún catálogo. Preguntando por la pista se
    esquiva ese problema entero y se recupera el disco auténtico — y con él
    unos tags que sí dicen algo: "Moon Talk" sale spain, trap, latin, rap.
    """
    if not artist or not title:
        return None
    clave = (_norm_tight(artist), _norm_tight(title))
    if clave in _client.lastfm_track_cache:
        return _client.lastfm_track_cache[clave]

    resultado = None
    d = _lastfm("track.getinfo", {"artist": artist, "track": title})
    pista = (d or {}).get("track", {})
    if pista:
        resultado = _tags_a_genero((pista.get("toptags") or {}).get("tag", []))
        if resultado is None:
            album_real = (pista.get("album") or {}).get("title")
            if album_real:
                resultado = _lastfm_album_tags(artist, album_real)
    if resultado is None and album_local:
        resultado = _lastfm_album_tags(artist, album_local)

    _client.lastfm_track_cache[clave] = resultado
    return resultado


def _lastfm_artist_fuerte(artist: str) -> Optional[str]:
    """Género del artista solo si la comunidad está prácticamente de acuerdo.

    Sirve para desempatar contra el género de álbum de Deezer, que es la fuente
    menos fiable de todas: si Deezer dice "electronica" para una canción de
    Kidd Keo pero sus tags son trap:100 frente a latin:7, gana el artista.

    El umbral se limita solo: un artista que de verdad cruza géneros tiene los
    tags repartidos, no llega al umbral, y su pista conserva lo que diga el
    álbum. Que es justo lo que se quiere.
    """
    g = _lastfm_artist_genre(artist)
    return g if g and _client.ultima_fuerza >= ARTISTA_UNANIME else None


def _lastfm_artist_genre(artist: str) -> Optional[str]:
    """Género según los tags del ARTISTA en Last.fm, ponderados."""
    if not artist:
        return None
    clave = _norm_tight(artist)
    if clave in _client.lastfm_artist_cache:
        return _client.lastfm_artist_cache[clave]
    d = _lastfm("artist.gettoptags", {"artist": artist})
    tags = ((d or {}).get("toptags") or {}).get("tag", [])
    resultado = _tags_a_genero(tags)
    _client.lastfm_artist_cache[clave] = resultado
    return resultado


def _wikidata_genre(artist: str) -> Optional[str]:
    """Género declarado en Wikidata para el artista, o None.

    Es información curada a mano, y acierta justo donde Deezer e iTunes fallan
    con el catálogo español: SFDK sale hip-hop y no pop, Extremoduro hard rock,
    Sabaton power metal. A cambio es del ARTISTA, no de la pista, así que aquí
    solo se usa para corregir respuestas vagas — no para decidir por su cuenta.
    """
    if not artist:
        return None
    key = _norm_tight(artist)
    if key in _client.wikidata_cache:
        return _client.wikidata_cache[key]

    resultado: Optional[str] = None
    try:
        busq = _client.get_json(WIKIDATA, {
            "action": "wbsearchentities", "format": "json", "language": "es",
            "uselang": "es", "type": "item", "limit": 5, "search": artist,
        })
        for hit in (busq or {}).get("search", []):
            # Buscar por nombre pesca de todo: una calle, una película, una
            # empresa. Si la descripción no dice que es alguien que hace
            # música, su "género" no es el que buscamos.
            desc = _norm(hit.get("description", ""))
            if not any(p in desc for p in WIKIDATA_MUSICAL):
                continue
            claims = _client.get_json(WIKIDATA, {
                "action": "wbgetclaims", "format": "json",
                "property": "P136", "entity": hit["id"],
            })
            qids = [
                c["mainsnak"]["datavalue"]["value"]["id"]
                for c in (claims or {}).get("claims", {}).get("P136", [])
                if c.get("mainsnak", {}).get("datavalue")
            ]
            if not qids:
                continue
            etiquetas = _client.get_json(WIKIDATA, {
                "action": "wbgetentities", "format": "json", "props": "labels",
                "languages": "es|en", "ids": "|".join(qids[:8]),
            })
            # Se vota el canónico, en el orden en que Wikidata lista los
            # géneros: Kidd Keo trae "hip hop español, trap latino, drill,
            # música house" y ahí rap gana 3 a 1, que es la respuesta.
            votos: Counter[str] = Counter()
            for qid in qids[:8]:
                ent = (etiquetas or {}).get("entities", {}).get(qid, {})
                labels = ent.get("labels", {})
                nombre = (labels.get("es") or labels.get("en") or {}).get("value")
                canon = canonicalize_wikidata(nombre)
                if canon:
                    votos[canon] += 1
            if votos:
                resultado = votos.most_common(1)[0][0]
                break
    except Exception:
        log.debug("wikidata falló para %s", artist)

    _client.wikidata_cache[key] = resultado
    return resultado


def _itunes_genre(artist: str, title: str) -> Optional[str]:
    """Género de iTunes para esta pista. Segunda opinión cuando Deezer no sabe.

    Devuelve ya canónico. iTunes da género por PISTA (no por álbum) y cubre
    sellos pequeños de electrónica que Deezer no indexa —Ned Bennett, Deas—,
    pero no tiene rap ruso ni mucho underground, así que no sustituye a Deezer:
    lo complementa.
    """
    if not artist or not title:
        return None
    data = _client.get_json(
        ITUNES, {"entity": "song", "limit": 5, "term": f"{artist} {search_title(title)}"}
    )
    want = _norm_tight(artist)
    for item in (data or {}).get("results", []):
        # Mismo criterio que con Deezer: si el artista no coincide, no es
        # nuestra canción por mucho que el título encaje.
        cand = _norm_tight(item.get("artistName", ""))
        if want not in cand and cand not in want:
            continue
        canon = canonicalize_itunes(item.get("primaryGenreName"))
        if canon:
            return canon
    return None


def _es_pop_por_defecto(etiquetas: list[str]) -> bool:
    """True si el álbum trae SOLO "Pop", que en Deezer no significa nada.

    Medido sobre casos con la respuesta conocida: de seis álbumes con la
    etiqueta única ["Pop"], **cinco no eran pop** — SFDK (rap), Extremoduro
    (rock), Fito y Fitipaldis (rock), Maná (rock), Los Delinqüentes (rumba).
    Es lo que pone Deezer en el catálogo español cuando no lo ha clasificado.

    Los álbumes clasificados de verdad traen la etiqueta que toca
    (["Rap/Hip Hop"], ["Rock"]) o varias (["Pop", "Pop internacional", "Rock"]).
    Así que un "Pop" a solas se trata como falta de respuesta y se sigue
    preguntando a las otras fuentes; si de verdad es pop, lo confirmarán.
    """
    return len(etiquetas) == 1 and _norm(etiquetas[0]) == "pop"


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
        etiquetas = _client.album_genres(int(album_id))
        if _es_pop_por_defecto(etiquetas):
            # No es una respuesta: es el hueco. Sigue la cascada.
            return None
        for raw in etiquetas:
            # No basta con coger la primera: un álbum puede venir como
            # ["Películas/Juegos", "Bandas sonoras"] y la útil ser la segunda.
            if canonicalize(raw):
                return raw
    return None


def _artist_album_ids(artist_id: int) -> list[int]:
    """Álbumes representativos del artista, para votar su género.

    Se usan los de sus canciones MÁS ESCUCHADAS, no sus últimos lanzamientos.
    `/artist/albums` devuelve lo más reciente, que en un artista con carrera
    larga es ruido: los seis últimos de Snoop Dogg son un disco de reggae, uno
    de rock, un Baby Shark y un remix EDM, y la votación salía sin ganador. Por
    canciones top sale rap con el 67 %, que es la respuesta.

    Si las top no dan nada (artistas sin apenas reproducciones), se cae a los
    últimos álbumes, que para ellos sí son representativos.
    """
    top = _client.get(f"/artist/{artist_id}/top", params={"limit": ARTIST_TOP_SAMPLE})
    ids = [
        int((t.get("album") or {}).get("id"))
        for t in (top or {}).get("data", [])
        if (t.get("album") or {}).get("id")
    ]
    if ids:
        # Un artista repite álbum entre sus top: cada disco cuenta una vez.
        return list(dict.fromkeys(ids))

    albums = _client.get(f"/artist/{artist_id}/albums", params={"limit": ARTIST_ALBUMS_SAMPLE})
    return [int(a["id"]) for a in (albums or {}).get("data", []) if a.get("id")]


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
        albums = _artist_album_ids(hits[0]["id"])
        # Se vota el género CANÓNICO, no la etiqueta cruda. Deezer reparte una
        # misma idea entre varias etiquetas —Daft Punk salía Electro 3,
        # Techno/House 2, Dance 4— y contando etiquetas ninguna llegaba al 50 %
        # aunque las tres digan "electronica" y sumen 9 de 12. Contando por
        # canónico gana con el 75 % que le corresponde.
        votes: Counter[str] = Counter()
        for album_id in albums:
            for g in _client.album_genres(album_id):
                canon = canonicalize(g)
                if canon:
                    votes[canon] += 1
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


def resolve(
    artist: str,
    title: str,
    *,
    album: Optional[str] = None,
    allow_artist_fallback: bool = True,
) -> Optional[str]:
    """Género canónico de una pista, o None si no se puede decidir.

    Nunca lanza: si Deezer no responde, la canción se queda sin género y ya se
    rellenará en otra pasada.
    """
    try:
        # _track_genre devuelve etiqueta de Deezer; _artist_genre ya devuelve
        # canónico (vota sobre canónicos). Se traduce solo lo primero.
        # Evidencia de la PISTA primero. Un artista puede hacer rap y
        # reggaeton, y eso solo se ve disco a disco y pista a pista.
        #
        # Last.fm va primero porque es la mejor granularidad con datos
        # fiables: los tags los pone gente que escuchó la música, no un
        # catálogo. Y resuelve el álbum real a partir de la pista, así que no
        # depende de cómo se llamen los álbumes aquí dentro.
        canon = _lastfm_track_genre(artist, title, album)
        de_lastfm = canon is not None
        if canon is None:
            canon = canonicalize(_track_genre(artist, title))
        if canon is None:
            canon = _itunes_genre(artist, title)
        if canon is None and allow_artist_fallback:
            canon = _artist_genre(artist)

        # Si la respuesta NO viene de Last.fm sino del género de álbum de
        # Deezer —el menos fiable— y el artista tiene un género casi unánime
        # que lo contradice, gana el artista. Sin esto, "Ma Vie" de Kidd Keo
        # se quedaba en electronica por el disco donde Deezer la coloca.
        if canon is not None and not de_lastfm and allow_artist_fallback:
            fuerte = _lastfm_artist_fuerte(artist)
            if fuerte and fuerte != canon:
                canon = fuerte

        # Corrección: si lo que ha salido es vago —de lo que estas APIs sueltan
        # cuando no han clasificado— se afina con el artista. Los tags de
        # Last.fm van ponderados y son los mejores; Wikidata cubre lo que
        # Last.fm no tenga.
        #
        # Solo se corrige lo vago: una respuesta específica de la pista
        # (reggaeton en un tema de un rapero) se respeta, que es de lo que se
        # trata.
        if canon is None or canon in GENEROS_VAGOS:
            mejor = _lastfm_artist_genre(artist) or _wikidata_genre(artist)
            if mejor and mejor != canon:
                canon = mejor

        # "bso" dice en qué disco salió la canción, no cómo suena. Un tema de
        # Snoop Dogg que aparece en una banda sonora sigue siendo rap, y para
        # "top de rap de la semana" etiquetarlo de bso es perderlo.
        if canon == "bso":
            canon = _lastfm_artist_genre(artist) or _wikidata_genre(artist) or (
                _artist_genre(artist) if allow_artist_fallback else None
            ) or "bso"

        # Último recurso para las pistas sin artista de verdad: sacarlo del
        # título. Sin esto, todo lo subido a mano se queda sin género para
        # siempre, porque "Unknown Artist" no existe en ningún catálogo.
        if canon is None and _norm_tight(artist) in _ARTISTAS_VACIOS:
            partido = _split_artist_from_title(title)
            if partido:
                real_artist, real_title = partido
                canon = canonicalize(_track_genre(real_artist, real_title))
                if canon is None:
                    canon = _itunes_genre(real_artist, real_title)
                if canon is None and allow_artist_fallback:
                    canon = _artist_genre(real_artist)

        return canon
    except Exception:
        log.exception("resolviendo género de %s — %s", artist, title)
        return None


def resolve_meta(meta) -> Optional[str]:
    """Como resolve(), pero tomando los datos de un TrackMeta."""
    return resolve(meta.primary_artist, meta.title, album=meta.album or None)


def reset_cache() -> None:
    """Para los scripts de larga duración, si hiciera falta soltar memoria."""
    _client.reset()


# Se construye al final porque _norm() se define más abajo que la tabla.
_LOOKUP: dict[str, str] = {_norm(k): v for k, v in CANONICAL.items()}
_LOOKUP_ITUNES: dict[str, str] = {_norm(k): v for k, v in ITUNES_CANONICAL.items()}
