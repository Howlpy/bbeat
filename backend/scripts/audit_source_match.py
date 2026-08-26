"""Detecta pistas cuyo audio no corresponde a la canción que dicen ser.

Compara el título de cada pista con el título REAL del vídeo de YouTube del
que se descargó (endpoint oEmbed, sin API key). Sirve para localizar los
cruces que dejó el matcher antiguo, que aceptaba cualquier vídeo del canal
del artista si la duración cuadraba.

Uso:
    python -m scripts.audit_source_match            # informe por consola
    python -m scripts.audit_source_match --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from sqlmodel import Session, select

from app.db import engine
from app.models import Artist, Track
from app.services.downloader import (
    _cand_tokens,
    _norm_text,
    _title_overlap,
    _title_tokens,
)

OEMBED = "https://www.youtube.com/oembed?format=json&url="
WORKERS = 6


def _fetch_title(url: str) -> tuple[str | None, str | None]:
    """Devuelve (título del vídeo, error). None/None si el vídeo ya no existe."""
    req = urllib.request.Request(
        OEMBED + urllib.parse.quote(url, safe=""),
        headers={"User-Agent": "Mozilla/5.0"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.load(resp)
            return data.get("title"), None
        except Exception as e:
            code = getattr(e, "code", None)
            if code in (401, 403, 404):
                # Retirado, privado o con restriccion de edad: no se puede verificar.
                return None, f"HTTP {code}"
            if attempt == 2:
                return None, str(e)[:80]
            time.sleep(1.5 * (attempt + 1))
    return None, "sin respuesta"


def _rows() -> list[dict]:
    with Session(engine) as s:
        pairs = s.exec(
            select(Track, Artist).join(Artist, Artist.id == Track.artist_id)
        ).all()
    out = []
    for t, a in pairs:
        if not t.source_url or "youtu" not in t.source_url:
            continue
        out.append(
            {
                "id": t.id,
                "title": t.title,
                "artist": a.name,
                "source_url": t.source_url,
                "file_path": t.file_path,
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="volcar el resultado completo a un fichero")
    args = ap.parse_args()

    rows = _rows()
    print(f"verificando {len(rows)} pistas con URL de YouTube…", file=sys.stderr)

    def check(r: dict) -> dict:
        r["yt_title"], r["error"] = _fetch_title(r["source_url"])
        if not r["yt_title"]:
            r["verdict"] = "no_verificable"
            return r
        title_norm = _norm_text(r["title"])
        words = _title_tokens(title_norm)
        cand_norm = _norm_text(r["yt_title"])
        overlap = _title_overlap(words, title_norm, cand_norm)
        shared = words & _cand_tokens(cand_norm)
        strong = overlap >= 0.999 or sum(len(w) for w in shared) >= 6
        r["overlap"] = round(overlap, 2)
        r["verdict"] = "ok" if (overlap >= 0.5 and strong) else "mismatch"
        return r

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        rows = list(ex.map(check, rows))

    bad = [r for r in rows if r["verdict"] == "mismatch"]
    unk = [r for r in rows if r["verdict"] == "no_verificable"]

    print(f"\n{len(bad)} pistas con audio que no corresponde:\n")
    for r in sorted(bad, key=lambda x: x["id"]):
        print(f"  #{r['id']}  {r['artist']} — {r['title']}")
        print(f"       suena: {r['yt_title']}")
        print(f"       {r['source_url']}")
    if unk:
        print(f"\n{len(unk)} no verificables (vídeo retirado o privado): "
              + ", ".join(str(r["id"]) for r in unk))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"\ndetalle completo en {args.json}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
