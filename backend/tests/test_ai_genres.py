"""Clasificación de géneros con IA: cliente, validación, umbral, bloqueos, cuota.

Sin red: el LLM se simula con httpx.MockTransport o con un cliente falso, y la
búsqueda web con una función. El tag del fichero se sustituye por un registro.
"""
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, delete, select

from app.api import ai_genres as ai_api
from app.config import settings
from app.db import engine, init_db
from app.models import Album, AlbumTrack, Artist, GenreSuggestion, Track, User
from app.services import auth as auth_svc
from app.services import genre_store
from app.services.ai import genre_ai, search as search_svc
from app.services.ai.llm import (
    InvalidResponse, LLMClient, LLMConfig, LLMError, QuotaExceeded, extract_json,
)


# ─── LLM client ──────────────────────────────────────────────────


def _cfg(provider="openai", **kw):
    base = dict(provider=provider, base_url="http://llm.test/v1", api_key="k",
                model="m", rpm=0, timeout=5)
    base.update(kw)
    return LLMConfig(**base)


def _client(handler, provider="openai", sleeps=None, **kw):
    sl = sleeps if sleeps is not None else []
    return LLMClient(_cfg(provider, **kw), transport=httpx.MockTransport(handler), sleep=sl.append)


def _ok(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_extract_json_tolerante():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Claro, aquí va: {"a": {"b": 2}} espero que sirva') == {"a": {"b": 2}}
    with pytest.raises(InvalidResponse):
        extract_json("nada de json")
    with pytest.raises(InvalidResponse):
        extract_json("")


def test_chat_json_reintenta_una_vez_si_es_invalido():
    respuestas = iter(["esto no es json", '{"ok": true}'])
    c = _client(lambda req: _ok(next(respuestas)))
    assert c.chat_json("s", "u") == {"ok": True}
    assert c.requests == 2


def test_chat_json_falla_tras_dos_invalidos():
    c = _client(lambda req: _ok("basura"))
    with pytest.raises(InvalidResponse):
        c.chat_json("s", "u")
    assert c.requests == 2


def test_chat_json_validador_dispara_reintento():
    respuestas = iter(['{"x": 1}', '{"x": 2}'])

    def val(d):
        if d["x"] != 2:
            raise ValueError("x debe ser 2")
        return d["x"]

    assert _client(lambda req: _ok(next(respuestas))).chat_json("s", "u", val) == 2


def test_429_reintenta_con_retry_after():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        if n["i"] == 1:
            return httpx.Response(429, headers={"retry-after": "7"}, text="slow down")
        return _ok("{}")

    sleeps = []
    assert _client(h, sleeps=sleeps).chat_json("s", "u") == {}
    assert sleeps == [7.0]


def test_5xx_backoff_exponencial():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        return httpx.Response(503) if n["i"] < 3 else _ok("{}")

    sleeps = []
    _client(h, sleeps=sleeps).chat_json("s", "u")
    assert sleeps == [2.0, 4.0]


def test_cuota_diaria_lanza_quota_exceeded_sin_esperar():
    body = '{"error": {"message": "Quota exceeded for metric per day"}}'
    sleeps = []
    c = _client(lambda req: httpx.Response(429, text=body), sleeps=sleeps)
    with pytest.raises(QuotaExceeded):
        c.chat_json("s", "u")
    assert sleeps == [] and c.requests == 1


def test_retry_after_largo_es_cuota():
    c = _client(lambda req: httpx.Response(429, headers={"retry-after": "3600"}))
    with pytest.raises(QuotaExceeded) as e:
        c.chat_json("s", "u")
    assert e.value.retry_after == 3600


def test_429_sostenido_acaba_en_quota_exceeded():
    c = _client(lambda req: httpx.Response(429), sleeps=[])
    with pytest.raises(QuotaExceeded):
        c.chat_json("s", "u")


def test_clave_rechazada_es_error_claro():
    with pytest.raises(LLMError, match="clave"):
        _client(lambda req: httpx.Response(401)).chat_json("s", "u")


def test_sin_response_format_si_el_servidor_lo_rechaza():
    vistos = []

    def h(req):
        body = json.loads(req.content)
        vistos.append("response_format" in body)
        return httpx.Response(400) if "response_format" in body else _ok("{}")

    _client(h).chat_json("s", "u")
    assert vistos == [True, False]


def test_anthropic_usa_messages_api():
    def h(req):
        assert req.url.path == "/v1/messages"
        assert req.headers["x-api-key"] == "k"
        body = json.loads(req.content)
        assert body["system"] == "s"
        return httpx.Response(200, json={"content": [{"type": "text", "text": '{"a": 1}'}]})

    c = _client(h, provider="anthropic", base_url="http://llm.test")
    assert c.chat_json("s", "u") == {"a": 1}


def test_rpm_espacia_las_peticiones():
    t = {"now": 0.0}
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        t["now"] += s

    c = LLMClient(_cfg(rpm=6), transport=httpx.MockTransport(lambda r: _ok("{}")),
                  sleep=sleep, clock=lambda: t["now"])
    c.chat_json("s", "u")
    c.chat_json("s", "u")
    assert sleeps == [10.0]


def test_config_por_defecto_y_habilitado(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "ai_api_key", "")
    monkeypatch.setattr(settings, "ai_base_url", "")
    monkeypatch.setattr(settings, "ai_model", "")
    c = LLMConfig.from_settings()
    assert "generativelanguage" in c.base_url and c.model and not c.enabled
    monkeypatch.setattr(settings, "ai_api_key", "x")
    assert LLMConfig.from_settings().enabled
    monkeypatch.setattr(settings, "ai_provider", "ollama")
    monkeypatch.setattr(settings, "ai_api_key", "")
    assert LLMConfig.from_settings().enabled  # local: sin clave
    monkeypatch.setattr(settings, "ai_provider", "none")
    assert not LLMConfig.from_settings().enabled


# ─── Búsqueda ────────────────────────────────────────────────────


def test_busqueda_desactivada_o_rota_nunca_lanza(monkeypatch):
    monkeypatch.setattr(settings, "search_provider", "none")
    assert search_svc.search("x") == []
    monkeypatch.setattr(settings, "search_provider", "searxng")
    monkeypatch.setattr(settings, "searxng_url", "http://searx.test")

    def boom(*a, **k):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(httpx, "get", boom)
    assert search_svc.search("x") == []


def test_searxng_parsea_resultados(monkeypatch):
    monkeypatch.setattr(settings, "search_provider", "searxng")
    monkeypatch.setattr(settings, "searxng_url", "http://searx.test/")

    def fake_get(url, params=None, headers=None, timeout=None):
        assert url == "http://searx.test/search" and params["format"] == "json"
        return httpx.Response(200, json={"results": [
            {"title": "T", "content": "C" * 500, "url": "http://u"}, {"title": "T2"}
        ]}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    r = search_svc.search("q", 1)
    assert len(r) == 1 and r[0].title == "T" and len(r[0].content) == 300


# ─── Validación de la respuesta ──────────────────────────────────


def _ctx(aid=1, tracks=((10, "a"), (11, "b"))):
    return genre_ai.ArtistCtx(aid, "X", [genre_ai.TrackInfo(i, t, None, "rap") for i, t in tracks])


def test_parse_valida_slugs_y_recorta_confianza():
    ctx = _ctx()
    out = genre_ai.parse_response({"results": [{
        "artist_id": 1, "artist_genre": "Rock", "confidence": 7, "reason": "r",
        "exceptions": [
            {"track_id": 10, "genre": "pop", "reason": "x"},
            {"track_id": 99, "genre": "pop"},       # pista ajena
            {"track_id": 11, "genre": "inventado"}, # slug inválido
            {"track_id": 11, "genre": "rock"},      # igual al del artista
        ],
    }]}, [ctx])
    v = out[1]
    assert v.genre == "rock" and v.confidence == 1.0
    assert [(e.track_id, e.genre) for e in v.exceptions] == [(10, "pop")]


def test_parse_acepta_etiqueta_unknown_y_objeto_suelto():
    ctx = _ctx()
    v = genre_ai.parse_response({"artist_genre": "Rap / Hip-Hop", "confidence": 0.9}, [ctx])[1]
    assert v.genre == "rap"
    v = genre_ai.parse_response({"artist_genre": "unknown", "confidence": 0.2,
                                 "exceptions": [{"track_id": 10, "genre": "pop"}]}, [ctx])[1]
    assert v.genre is None and v.exceptions == []


def test_parse_rechaza_genero_fuera_de_la_lista_y_respuesta_vacia():
    ctx = _ctx()
    with pytest.raises(ValueError):
        genre_ai.parse_response({"results": [{"artist_id": 1, "artist_genre": "vaporwave"}]}, [ctx])
    with pytest.raises(ValueError):
        genre_ai.parse_response({"results": []}, [ctx])
    with pytest.raises(ValueError):
        genre_ai.parse_response({"hola": 1}, [ctx])


def test_todo_genero_canonico_tiene_descripcion():
    from app.services.genres import GENRE_LABELS
    assert set(GENRE_LABELS) == set(genre_ai.GENRE_DESCRIPTIONS)


# ─── Persistencia: umbral, bloqueos, excepciones, cuota ──────────


class FakeLLM:
    """Responde con un veredicto por artista según `plan`: nombre -> dict o excepción."""

    def __init__(self, plan):
        self.cfg = _cfg()
        self.plan = plan
        self.requests = 0
        self.calls = []

    def chat_json(self, system, user, validate=None):
        self.requests += 1
        self.calls.append(user)
        results = []
        for name, spec in self.plan.items():
            if f'nombre="{name}"' in user:
                if isinstance(spec, Exception):
                    raise spec
                results.append((name, spec))
        # artist_id real: se resuelve en el test con ids de la BD
        data = {"results": [dict(spec, artist_id=ids[name]) for name, spec in results]}
        return validate(data) if validate else data

    def close(self):
        pass


ids: dict[str, int] = {}


def _limpiar():
    """Vacía lo que tocan estos tests (la BD es compartida con el resto)."""
    with Session(engine) as s:
        for m in (GenreSuggestion, AlbumTrack, Track, Album, Artist, User):
            s.exec(delete(m))
        s.commit()


@pytest.fixture()
def db(monkeypatch):
    init_db()
    SQLModel.metadata.create_all(engine)
    _limpiar()
    monkeypatch.setattr(settings, "ai_min_confidence", 0.75)
    monkeypatch.setattr(settings, "ai_batch_artists", 5)
    ids.clear()
    tags = []
    monkeypatch.setattr(genre_store, "write_genre_tag", lambda p, g: tags.append((p, g)) or None)
    yield tags
    _limpiar()


def _artist(name, genres, locked=()):
    """Crea un artista con una pista por cada género dado."""
    with Session(engine) as s:
        a = Artist(name=name, name_normalized=name.lower())
        s.add(a)
        s.commit()
        s.refresh(a)
        ids[name] = a.id
        out = []
        for i, g in enumerate(genres):
            t = Track(title=f"{name}-{i}", artist_id=a.id, genre=g,
                      file_path=f"{name}/{i}.opus", genre_locked=(i in locked))
            s.add(t)
            s.commit()
            s.refresh(t)
            out.append(t.id)
        return a.id, out


def _genres(artist_id):
    with Session(engine) as s:
        return {t.id: (t.genre, t.genre_source, t.genre_locked)
                for t in s.exec(select(Track).where(Track.artist_id == artist_id)).all()}


def _run(plan, **kw):
    kw.setdefault("search", lambda q, n: [])
    return genre_ai.run(llm=FakeLLM(plan), **kw)


def test_simulacro_no_escribe_nada(db):
    aid, _ = _artist("Mana", ["electronica"] * 3)
    r = _run({"Mana": {"artist_genre": "rock", "confidence": 0.95, "reason": "r"}}, apply=False)
    assert r.outcomes[0].status == "applied" and len(r.outcomes[0].changes) == 3
    assert {g for g, _, _ in _genres(aid).values()} == {"electronica"}
    assert db == []
    with Session(engine) as s:
        assert s.exec(select(GenreSuggestion)).all() == []


def test_confianza_alta_aplica_y_escribe_tag(db):
    aid, tids = _artist("Mana", ["electronica"] * 3)
    r = _run({"Mana": {"artist_genre": "rock", "confidence": 0.9, "reason": "r"}}, apply=True)
    assert r.count("applied") == 1
    assert all(v == ("rock", "ai", False) for v in _genres(aid).values())
    assert len(db) == 3
    with Session(engine) as s:
        rows = s.exec(select(GenreSuggestion)).all()
        assert [(x.status, x.track_id) for x in rows] == [("applied", None)]
        assert rows[0].previous_genre == "electronica"


def test_confianza_baja_va_a_revision_sin_tocar_pistas(db):
    aid, _ = _artist("Beatles", ["folk"] * 3)
    r = _run({"Beatles": {"artist_genre": "rock", "confidence": 0.5, "reason": "dudoso"}}, apply=True)
    assert r.count("pending") == 1
    assert {g for g, _, _ in _genres(aid).values()} == {"folk"}
    assert db == []
    with Session(engine) as s:
        assert s.exec(select(GenreSuggestion)).one().status == "pending"


def test_unknown_se_registra_y_no_se_repite(db):
    _artist("Raro", [None, None])
    llm = FakeLLM({"Raro": {"artist_genre": "unknown", "confidence": 0.1}})
    genre_ai.run(apply=True, llm=llm, search=lambda q, n: [])
    assert llm.requests == 1
    r = genre_ai.run(apply=True, llm=llm, search=lambda q, n: [])
    assert r.outcomes == [] and llm.requests == 1  # ya clasificado: idempotente
    r = genre_ai.run(apply=True, llm=llm, search=lambda q, n: [], force=True)
    assert llm.requests == 2 and len(r.outcomes) == 1


def test_pistas_bloqueadas_no_se_tocan(db):
    aid, tids = _artist("Mana", ["electronica"] * 3, locked=(1,))
    _run({"Mana": {"artist_genre": "rock", "confidence": 0.95}}, apply=True)
    g = _genres(aid)
    assert g[tids[1]] == ("electronica", None, True)
    assert g[tids[0]][0] == "rock" and g[tids[2]][0] == "rock"


def test_set_track_genre_automatico_respeta_bloqueo(db):
    _, tids = _artist("A", ["rap"], locked=(0,))
    with Session(engine) as s:
        t = s.get(Track, tids[0])
        assert genre_store.set_track_genre(s, t, "pop", "ai") is False
        assert genre_store.set_track_genre(s, t, "pop", "manual", lock=True) is True
        assert t.genre == "pop"


def test_excepciones_por_pista(db):
    aid, tids = _artist("Pop Star", ["pop"] * 3)
    plan = {"Pop Star": {"artist_genre": "pop", "confidence": 0.9, "reason": "r",
                         "exceptions": [{"track_id": 0, "genre": "rap", "reason": "colab"}]}}
    llm = FakeLLM(plan)
    plan["Pop Star"]["exceptions"][0]["track_id"] = tids[1]
    r = genre_ai.run(apply=True, llm=llm, search=lambda q, n: [])
    g = _genres(aid)
    assert g[tids[1]][0] == "rap" and g[tids[0]][0] == "pop"
    assert r.outcomes[0].changes == {tids[1]: "rap"}
    with Session(engine) as s:
        assert len(s.exec(select(GenreSuggestion)).all()) == 2  # artista + excepción


def test_cuota_agotada_para_y_se_reanuda(db):
    for n in ("A", "B", "C"):
        _artist(n, ["electronica"] * 12)  # grandes: una petición cada uno
    plan = {
        "A": {"artist_genre": "rock", "confidence": 0.9},
        "B": QuotaExceeded("sin cuota", 3600),
        "C": {"artist_genre": "pop", "confidence": 0.9},
    }
    llm = FakeLLM(plan)
    r = genre_ai.run(apply=True, llm=llm, search=lambda q, n: [])
    assert r.quota_exceeded and r.retry_after == 3600
    assert [o.ctx.name for o in r.outcomes] == ["A"] and r.remaining == 2
    # al día siguiente: A ya está hecho, continúa con B y C
    plan["B"] = {"artist_genre": "jazz", "confidence": 0.9}
    r2 = genre_ai.run(apply=True, llm=llm, search=lambda q, n: [])
    assert not r2.quota_exceeded
    assert sorted(o.ctx.name for o in r2.outcomes) == ["B", "C"]


def test_artistas_pequenos_comparten_peticion(db):
    for n in ("A", "B", "C"):
        _artist(n, ["pop"] * 2)
    plan = {n: {"artist_genre": "rock", "confidence": 0.9} for n in ("A", "B", "C")}
    llm = FakeLLM(plan)
    genre_ai.run(apply=True, llm=llm, search=lambda q, n: [])
    assert llm.requests == 1


def test_evidencia_web_va_al_prompt(db):
    _artist("A", ["pop"] * 2)
    llm = FakeLLM({"A": {"artist_genre": "pop", "confidence": 0.9}})
    snip = search_svc.Snippet("Wiki", "cantante de pop", "http://w")
    genre_ai.run(apply=False, llm=llm, search=lambda q, n: [snip])
    assert "cantante de pop" in llm.calls[0] and "pop: 2" in llm.calls[0]


def test_candidatos_filtros(db):
    _artist("Completo", ["rap"] * 3)
    _artist("SinGenero", ["rap", None])
    _artist("Mixto", ["rap", "rap", "rock"])
    _artist("Unknown Artist", [None])
    with Session(engine) as s:
        names = lambda l: sorted(s.get(Artist, i).name for i in l)  # noqa: E731
        assert names(genre_ai.candidate_artist_ids(s)) == ["Completo", "Mixto", "SinGenero"]
        assert names(genre_ai.candidate_artist_ids(s, only_missing=True)) == ["SinGenero"]
        assert names(genre_ai.candidate_artist_ids(s, suspicious=True)) == ["Mixto", "SinGenero"]
        assert names(genre_ai.candidate_artist_ids(s, names=["completo"])) == ["Completo"]


# ─── Revisión y edición manual ───────────────────────────────────


def test_aceptar_cambiar_y_rechazar_sugerencias(db):
    aid, tids = _artist("Beatles", ["folk"] * 2)
    _run({"Beatles": {"artist_genre": "rock", "confidence": 0.4}}, apply=True)
    with Session(engine) as s:
        sid = s.exec(select(GenreSuggestion)).one().id
        assert genre_ai.accept_suggestion(s, sid) == 2
    assert all(v == ("rock", "ai", False) for v in _genres(aid).values())
    with Session(engine) as s:
        with pytest.raises(ValueError):
            genre_ai.accept_suggestion(s, sid)  # ya resuelta

    aid2, _ = _artist("Otro", ["folk"] * 2)
    _run({"Otro": {"artist_genre": "rock", "confidence": 0.4}}, apply=True)
    with Session(engine) as s:
        sid2 = s.exec(select(GenreSuggestion).where(GenreSuggestion.artist_id == aid2)).one().id
        genre_ai.accept_suggestion(s, sid2, "Jazz")  # otro género: decisión humana
    assert all(v == ("jazz", "manual", True) for v in _genres(aid2).values())

    aid3, _ = _artist("Tercero", ["folk"])
    _run({"Tercero": {"artist_genre": "rock", "confidence": 0.4}}, apply=True)
    with Session(engine) as s:
        sid3 = s.exec(select(GenreSuggestion).where(GenreSuggestion.artist_id == aid3)).one().id
        genre_ai.reject_suggestion(s, sid3)
        assert s.get(GenreSuggestion, sid3).status == "rejected"
    assert _genres(aid3)[next(iter(_genres(aid3)))][0] == "folk"


def test_aceptar_no_pisa_pistas_bloqueadas(db):
    aid, tids = _artist("A", ["folk"] * 3, locked=(0,))
    _run({"A": {"artist_genre": "rock", "confidence": 0.4}}, apply=True)
    with Session(engine) as s:
        genre_ai.accept_suggestion(s, s.exec(select(GenreSuggestion)).one().id)
    g = _genres(aid)
    assert g[tids[0]][0] == "folk" and g[tids[1]][0] == "rock"


def test_genero_de_artista_manual_bloquea_todo(db):
    aid, tids = _artist("A", ["folk", "rap", None], locked=(1,))
    with Session(engine) as s:
        res = genre_ai.set_artist_genre(s, aid, "rock")
    assert res["changed"] == 3
    assert all(v == ("rock", "manual", True) for v in _genres(aid).values())
    # y ya no lo cambia la IA
    _run({"A": {"artist_genre": "jazz", "confidence": 0.99}}, apply=True, force=True)
    assert all(v[0] == "rock" for v in _genres(aid).values())


def test_editar_genero_a_mano_bloquea(db, monkeypatch, tmp_path):
    from app.services import library as library_svc, organizer

    monkeypatch.setattr(organizer, "write_tags", lambda *a, **k: None)
    monkeypatch.setattr(settings, "music_dir", tmp_path)
    (tmp_path / "A").mkdir()
    f = tmp_path / "A" / "t.opus"
    f.write_bytes(b"x")
    with Session(engine) as s:
        a = Artist(name="A", name_normalized="a")
        s.add(a)
        s.commit()
        t = Track(title="t", artist_id=a.id, genre="rap", file_path="A/t.opus")
        s.add(t)
        s.commit()
        tid = t.id
    # editar solo el título no bloquea el género
    assert library_svc.edit_track(tid, title="t2")["ok"]
    with Session(engine) as s:
        assert s.get(Track, tid).genre_locked is False
    assert library_svc.edit_track(tid, genre="jazz")["ok"]
    with Session(engine) as s:
        t = s.get(Track, tid)
        assert (t.genre, t.genre_source, t.genre_locked) == ("jazz", "manual", True)


# ─── Coherencia por artista al importar ──────────────────────────


def test_coherencia_mantiene_el_genero_del_artista(db):
    _artist("Rapero", ["rap"] * 4 + ["rock"])  # 80% rap
    with Session(engine) as s:
        assert genre_store.apply_artist_consistency(s, "Rapero", "electronica") == ("rap", True)
        assert genre_store.apply_artist_consistency(s, "Rapero", "rap") == ("rap", False)
        assert genre_store.apply_artist_consistency(s, "Rapero", None) == (None, False)
        assert genre_store.apply_artist_consistency(s, "Nuevo", "pop") == ("pop", False)


def test_coherencia_necesita_minimo_de_pistas_y_acuerdo(db):
    _artist("Poco", ["rap"] * 2)
    _artist("Mixto", ["rap", "rap", "rock"])  # 67% < 80%
    with Session(engine) as s:
        assert genre_store.apply_artist_consistency(s, "Poco", "pop") == ("pop", False)
        assert genre_store.apply_artist_consistency(s, "Mixto", "pop") == ("pop", False)


def test_coherencia_cede_ante_evidencia_fuerte_del_album(db):
    with Session(engine) as s:
        a = Artist(name="Art", name_normalized="art")
        s.add(a)
        s.commit()
        aid = a.id
        al = Album(title="Disco", title_normalized="disco", artist_id=aid)
        s.add(al)
        s.commit()
        alid = al.id
        for i in range(10):
            s.add(Track(title=str(i), artist_id=aid, file_path=f"x{i}",
                        genre="rap" if i < 9 else "jazz", album_id=alid if i >= 8 else None))
        s.commit()
    with Session(engine) as s:
        # el álbum tiene 1 jazz + 1 rap: no basta
        assert genre_store.apply_artist_consistency(s, "Art", "jazz", "Disco") == ("rap", True)
        s.add(Track(title="y", artist_id=aid, file_path="y", genre="jazz", album_id=alid))
        s.commit()
        assert genre_store.apply_artist_consistency(s, "Art", "jazz", "Disco") == ("jazz", True)


def test_coherencia_se_puede_desactivar(db, monkeypatch):
    _artist("Rapero", ["rap"] * 5)
    monkeypatch.setattr(settings, "artist_consistency", False)
    with Session(engine) as s:
        assert genre_store.apply_artist_consistency(s, "Rapero", "pop") == ("pop", False)


def test_resolve_meta_aplica_coherencia_y_encola_si_hay_ia(db, monkeypatch):
    from app.services import genres
    from app.services.spotify import TrackMeta

    _artist("Rapero", ["rap"] * 5)
    monkeypatch.setattr(genres, "resolve", lambda *a, **k: "electronica")
    enq = []
    monkeypatch.setattr(genre_ai, "enqueue_artist", enq.append)
    meta = TrackMeta(spotify_id="1", title="t", artists=["Rapero"], album="", album_artist="Rapero",
                     track_number=1, disc_number=1, total_tracks=1, duration_ms=1, isrc=None,
                     year=None, cover_url=None, source_url="", source_kind="track", genre=None)
    assert genres.resolve_meta(meta) == "rap"
    assert enq == ["Rapero"]  # discrepancia -> a la cola de IA


def test_enqueue_no_hace_nada_sin_ia(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "none")
    genre_ai._queue.clear()
    genre_ai.enqueue_artist("X")
    assert genre_ai._queue == set()


# ─── API ─────────────────────────────────────────────────────────


@pytest.fixture()
def api(db):
    with Session(engine) as s:
        admin = User(username="adm", email="a@x.com", password_hash="x", is_admin=True, is_approved=True)
        s.add(admin)
        s.commit()
        s.refresh(admin)
    app = FastAPI()
    app.include_router(ai_api.router, prefix="/api")
    app.dependency_overrides[auth_svc.require_admin] = lambda: admin
    return TestClient(app)


def test_api_estado_sin_secretos(api, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "ai_api_key", "SECRETO")
    _artist("A", [None, "rap"])
    r = api.get("/api/admin/ai-genres/status")
    assert r.status_code == 200
    assert "SECRETO" not in r.text
    j = r.json()
    assert j["config"]["provider"] == "gemini" and j["config"]["api_key_set"] is True
    assert j["tracks_without_genre"] == 1 and j["unclassified_artists"] == 1


def test_api_run_exige_ia_configurada(api, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "none")
    assert api.post("/api/admin/ai-genres/run", json={}).status_code == 400


def test_api_revisar_y_artista(api):
    aid, tids = _artist("Beatles", ["folk"] * 2)
    _run({"Beatles": {"artist_genre": "rock", "confidence": 0.3, "reason": "dudoso"}}, apply=True)
    items = api.get("/api/admin/ai-genres/suggestions").json()["items"]
    assert len(items) == 1 and items[0]["artist_name"] == "Beatles" and items[0]["genre"] == "rock"
    sid = items[0]["id"]
    assert api.post(f"/api/admin/ai-genres/suggestions/{sid}/accept", json={}).json()["changed"] == 2
    assert api.get("/api/admin/ai-genres/suggestions").json()["items"] == []
    assert api.post(f"/api/admin/ai-genres/suggestions/{sid}/accept", json={}).status_code == 400
    assert api.post("/api/admin/ai-genres/suggestions/999/reject").status_code == 404

    r = api.put(f"/api/admin/artists/{aid}/genre", json={"genre": "jazz"})
    assert r.json()["changed"] == 2
    assert all(v == ("jazz", "manual", True) for v in _genres(aid).values())
    assert api.put(f"/api/admin/artists/{aid}/genre", json={"genre": " "}).status_code == 400
    assert api.put("/api/admin/artists/9999/genre", json={"genre": "rap"}).status_code == 404
