"""Tests de la resolución de género (services/genres.py).

Las funciones puras se prueban tal cual. Para resolve() se parchean las seis
fuentes de red (Last.fm pista/artista, Deezer pista/artista, iTunes, Wikidata),
de modo que cada regla de decisión queda fijada con el caso real que la motivó
(Denom, Kidd Keo, Blake, FUFU, Powerwolf... ver los commits #41-#44). Si una
futura "mejora" rompe una de estas reglas, esto es lo que la detecta.

Sin red: ninguna prueba toca ninguna API.
"""
import pytest

from app.services import genres


@pytest.fixture(autouse=True)
def _cachés_limpias():
    """Cada test parte con las cachés del cliente vacías y las deja vacías."""
    genres.reset_cache()
    yield
    genres.reset_cache()


# ─── Normalización y tablas ──────────────────────────────────────


def test_norm_quita_acentos_y_signos():
    assert genres._norm("Rap/Hip Hop") == "rap hip hop"
    assert genres._norm("Clásica") == "clasica"
    assert genres._norm("  R&B  ") == "r b"


def test_norm_tight_iguala_variantes_de_nombre():
    assert genres._norm_tight("Eazy E") == genres._norm_tight("Eazy-E")


def test_canonicalize_deezer():
    assert genres.canonicalize("Rap/Hip Hop") == "rap"
    assert genres.canonicalize("RAP/HIP HOP") == "rap"
    assert genres.canonicalize("Techno/House") == "electronica"
    assert genres.canonicalize("Películas/Juegos") == "bso"
    # Etiqueta desconocida → None a propósito: mejor vacía que mal mapeada.
    assert genres.canonicalize("Zouk") is None
    assert genres.canonicalize(None) is None


def test_canonicalize_itunes_tabla_y_patrones():
    assert genres.canonicalize_itunes("Hip-Hop/Rap") == "rap"
    # No está en la tabla, pero los patrones por subcadena lo cazan.
    assert genres.canonicalize_itunes("Urbano latino") == "latino"
    assert genres.canonicalize_itunes("Reggaeton y Hip-Hop") == "reggaeton"


def test_canonicalize_wikidata_el_orden_decide():
    # "trap latino" contiene "trap" y "latino": gana rap porque va antes.
    assert genres.canonicalize_wikidata("trap latino") == "rap"
    assert genres.canonicalize_wikidata("pop rap") == "rap"
    # "pop" va el último a propósito.
    assert genres.canonicalize_wikidata("música pop") == "pop"
    assert genres.canonicalize_wikidata("novela") is None


def test_search_title_corta_coletillas():
    assert genres.search_title("Moon Talk (Remasterizado 2024)") == "Moon Talk"
    assert genres.search_title("TOO SWEET - Dnb Mix") == "TOO SWEET"
    assert genres.search_title("Dura feat. Bad Bunny") == "Dura"
    # Nunca deja un título ridículamente corto.
    assert genres.search_title("A - B") == "A - B"


def test_es_pop_por_defecto():
    assert genres._es_pop_por_defecto(["Pop"]) is True
    assert genres._es_pop_por_defecto(["Pop", "Rock"]) is False
    assert genres._es_pop_por_defecto(["Rap/Hip Hop"]) is False
    assert genres._es_pop_por_defecto([]) is False


def test_tags_a_genero_vota_con_pesos_e_ignora_ruido():
    # Bad Bunny: Reggaeton:100 frente a trap:72 → reggaeton, y la fuerza es
    # la parte del peso que se lleva el ganador.
    tags = [
        {"name": "Reggaeton", "count": 100},
        {"name": "trap", "count": 72},
        {"name": "spanish", "count": 50},   # ruido: no mapea, no puntúa
        {"name": "2022", "count": 40},
    ]
    genero, fuerza = genres._tags_a_genero(tags)
    assert genero == "reggaeton"
    assert fuerza == pytest.approx(100 / 172)


def test_tags_a_genero_acepta_dict_suelto_y_vacio():
    assert genres._tags_a_genero({"name": "hip hop", "count": 3}) == ("rap", 1.0)
    assert genres._tags_a_genero([]) == (None, 0.0)


def test_split_artist_from_title():
    assert genres._split_artist_from_title("Gydra & Fatloaf - Sphere (Original Mix)") == (
        "Gydra & Fatloaf",
        "Sphere (Original Mix)",
    )
    assert genres._split_artist_from_title("Sin separador") is None


# ─── resolve(): las reglas de decisión, con sus casos reales ─────


def _fuentes(
    monkeypatch,
    *,
    lf=None,            # Last.fm por pista (canónico)
    dz=None,            # Deezer por pista (etiqueta CRUDA de Deezer)
    it=None,            # iTunes por pista (canónico)
    artista_dz=None,    # respaldo Deezer por artista (canónico)
    artista_lf=(None, 0.0),  # tags del artista en Last.fm (canónico, fuerza)
    wikidata=None,      # género del artista en Wikidata (canónico)
):
    """Deja resolve() corriendo contra fuentes de mentira."""
    monkeypatch.setattr(genres, "_lastfm_track_genre", lambda a, t, al: lf)
    monkeypatch.setattr(genres, "_track_genre", lambda a, t: dz)
    monkeypatch.setattr(genres, "_itunes_genre", lambda a, t: it)
    monkeypatch.setattr(genres, "_artist_genre", lambda a: artista_dz)
    monkeypatch.setattr(genres, "_lastfm_artist_genre", lambda a: artista_lf)
    monkeypatch.setattr(genres, "_wikidata_genre", lambda a: wikidata)


def test_lastfm_manda_si_no_hay_consenso_en_contra(monkeypatch):
    _fuentes(monkeypatch, lf="rap", dz="Dance", it=None, artista_lf=("rap", 0.9))
    assert genres.resolve("Kidd Keo", "Foreign") == "rap"


def test_consenso_de_tres_tumba_a_lastfm(monkeypatch):
    # Denom — "Vidas Que Se Van" (#44): Last.fm casó el álbum equivocado y
    # decía electronica; Deezer, iTunes y los tags del artista decían rap.
    _fuentes(
        monkeypatch,
        lf="electronica",
        dz="Rap/Hip Hop",
        it="rap",
        artista_lf=("rap", 0.9),
    )
    assert genres.resolve("Denom", "Vidas Que Se Van") == "rap"


def test_dos_rivales_no_bastan_para_tumbar_a_lastfm(monkeypatch):
    _fuentes(
        monkeypatch,
        lf="electronica",
        dz="Rap/Hip Hop",
        it=None,
        artista_lf=("rap", 0.9),
    )
    assert genres.resolve("dnb demon", "Can't Get You Out Of My Head") == "electronica"


def test_respuesta_vaga_se_corrige_con_el_artista(monkeypatch):
    # SFDK en Deezer España sale "Pop" (el hueco), iTunes también dice pop;
    # los tags del artista dicen rap: gana el artista.
    _fuentes(monkeypatch, it="pop", artista_lf=("rap", 0.9))
    assert genres.resolve("SFDK", "Mis dulces 16") == "rap"


def test_respuesta_especifica_no_se_corrige(monkeypatch):
    # Un tema de reggaeton de un rapero se queda en reggaeton aunque el
    # artista sea rap: solo se corrige lo vago.
    _fuentes(monkeypatch, lf="reggaeton", artista_lf=("rap", 0.95))
    assert genres.resolve("Cualquiera", "Perreo") == "reggaeton"


def test_artista_unanime_pisa_a_deezer_con_wikidata_de_acuerdo(monkeypatch):
    # Kidd Keo — "Ma Vie" (#43): Deezer la coloca en un disco "Dance", pero
    # trap:100 en Last.fm + rap en Wikidata → rap. Hace falta que Last.fm
    # conozca ESA canción de ESE artista (guarda anti-homónimos, #42).
    _fuentes(
        monkeypatch,
        dz="Dance",
        artista_lf=("rap", 0.87),
        wikidata="rap",
    )
    genres._client.lastfm_track_existe[
        (genres._norm_tight("Kidd Keo"), genres._norm_tight("Ma Vie"))
    ] = True
    assert genres.resolve("Kidd Keo", "Ma Vie") == "rap"


def test_artista_unanime_sin_wikidata_no_pisa(monkeypatch):
    # FUFU (#43): unanimidad de OTRO artista mezclado en la misma página de
    # Last.fm. Sin la confirmación de Wikidata, manda el álbum de Deezer.
    _fuentes(
        monkeypatch,
        dz="Rap/Hip Hop",
        artista_lf=("electronica", 1.0),
        wikidata=None,
    )
    genres._client.lastfm_track_existe[
        (genres._norm_tight("FUFU"), genres._norm_tight("TIBURON"))
    ] = True
    assert genres.resolve("FUFU", "TIBURON") == "rap"


def test_artista_homonimo_sin_la_pista_en_lastfm_no_pisa(monkeypatch):
    # Blake (#42): el Blake de Last.fm es un grupo finlandés de stoner rock.
    # Si Last.fm no conoce esta canción de este artista, su unanimidad no vale.
    _fuentes(
        monkeypatch,
        dz="Rap/Hip Hop",
        artista_lf=("rock", 1.0),
        wikidata="rock",
    )
    # Nótese: lastfm_track_existe queda vacío → la pista no existe allí.
    assert genres.resolve("Blake", "Mena") == "rap"


def test_bso_se_reescribe_con_el_genero_del_artista(monkeypatch):
    # "bso" dice dónde salió la canción, no cómo suena.
    _fuentes(monkeypatch, dz="Películas/Juegos", artista_lf=("rap", 0.6))
    assert genres.resolve("Snoop Dogg", "Riders on the Storm") == "rap"


def test_bso_sin_mas_informacion_se_queda_en_bso(monkeypatch):
    _fuentes(monkeypatch, dz="Bandas sonoras")
    assert genres.resolve("Hans Zimmer", "Time") == "bso"


def test_artista_vacio_saca_el_artista_del_titulo(monkeypatch):
    # Subidas a mano: "Unknown Artist / Gydra - Scourge". El artista real se
    # extrae del título ANTES de preguntar, y corre la cascada entera.
    def lf_pista(artist, title, album):
        if artist == "Gydra" and title == "Scourge":
            return "electronica"
        return None

    _fuentes(monkeypatch)
    monkeypatch.setattr(genres, "_lastfm_track_genre", lf_pista)
    assert genres.resolve("Unknown Artist", "Gydra - Scourge") == "electronica"


def test_artista_vacio_sin_titulo_partible_no_inventa(monkeypatch):
    # "Various Artists — SLEEPY": buscar "Various Artists" en Deezer casa con
    # cualquier recopilatorio y devolvía un género al azar. Mejor ninguno.
    _fuentes(monkeypatch, dz="Niños", it="pop", artista_dz="pop")
    assert genres.resolve("Various Artists", "SLEEPY") is None


def test_artista_vacio_aplica_las_correcciones_al_artista_real(monkeypatch):
    # Al extraer el artista del título, la pista gana también las reglas de
    # corrección (vago → tags del artista real), no solo las cuatro fuentes.
    def artista_lf(artist):
        return ("rap", 0.9) if artist == "SFDK" else (None, 0.0)

    _fuentes(monkeypatch, it="pop")
    monkeypatch.setattr(genres, "_lastfm_artist_genre", artista_lf)
    assert genres.resolve("Various Artists", "SFDK - Mis dulces 16") == "rap"


def test_sin_fuentes_devuelve_none(monkeypatch):
    _fuentes(monkeypatch)
    assert genres.resolve("Nadie", "Nada") is None


def test_resolve_nunca_lanza(monkeypatch):
    def explota(*a, **k):
        raise RuntimeError("la red se cayó")

    _fuentes(monkeypatch)
    monkeypatch.setattr(genres, "_lastfm_track_genre", explota)
    assert genres.resolve("Da Igual", "Quien Sea") is None
