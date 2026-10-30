"""Clasifica el género de los ARTISTAS con IA (opcional, ver README).

Por cada artista manda a un LLM sus pistas, los géneros actuales y, si hay
SearXNG, evidencia web; el modelo elige un género de la lista cerrada y puede
marcar excepciones por pista. Solo se aplica con confianza >= BBEAT_AI_MIN_CONFIDENCE;
lo demás queda en la cola de revisión (Admin → Géneros con IA).

Las pistas bloqueadas (editadas a mano) no se tocan nunca. Reanudable: un
artista ya clasificado se salta (salvo --force). Si el proveedor agota la
cuota, para limpiamente y basta relanzar el mismo comando más tarde.

Uso:
    python -m scripts.ai_genres                      # simulacro (no toca nada)
    python -m scripts.ai_genres --limit 20 --report informe.csv
    python -m scripts.ai_genres --apply --limit 100
    python -m scripts.ai_genres --apply --only-missing
    python -m scripts.ai_genres --artist "Maná" --force --apply
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter

from app.db import init_db
from app.services.ai import genre_ai
from app.services.ai.llm import LLMNotConfigured


def _dist(o: genre_ai.Outcome) -> str:
    return ", ".join(f"{g}:{n}" for g, n in o.ctx.dist.most_common(4))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="escribe de verdad (por defecto simulacro)")
    ap.add_argument("--limit", type=int, default=0, help="procesa como mucho N artistas")
    ap.add_argument("--artist", action="append", help="solo este artista (repetible)")
    ap.add_argument("--force", action="store_true", help="reclasifica aunque ya lo estuviera")
    ap.add_argument("--only-missing", action="store_true", help="solo artistas con pistas sin género")
    ap.add_argument("--suspicious", action="store_true",
                    help="solo artistas sin género, con géneros mezclados o con 1-2 pistas")
    ap.add_argument("--report", help="vuelca el resultado a un CSV")
    args = ap.parse_args()

    init_db()
    cfg = genre_ai.config_summary()
    if not cfg["enabled"]:
        print("La IA no está configurada. Define BBEAT_AI_PROVIDER (+ BBEAT_AI_API_KEY) en backend/.env; ver README.")
        return 2
    modo = "APLICANDO" if args.apply else "SIMULACRO (usa --apply para escribir)"
    print(f"IA: {cfg['provider']} / {cfg['model']} · rpm {cfg['rpm']} · "
          f"búsqueda: {cfg['search_provider']} · confianza mínima {cfg['min_confidence']} · {modo}\n")

    rows: list[dict] = []

    def show(o: genre_ai.Outcome) -> None:
        v = o.verdict
        exc = "; ".join(f"{e.track_id}->{e.genre}" for e in v.exceptions)
        marca = {"applied": "OK  ", "pending": "REV ", "skipped": "----"}[o.status]
        print(f"{marca} {o.ctx.name[:30]:<30} [{_dist(o)}] -> {v.genre or 'unknown'} "
              f"({v.confidence:.2f}) {len(o.changes)} cambios"
              + (f" · excepciones: {exc}" if exc else "") + f"\n       {v.reason}")
        rows.append({
            "artista": o.ctx.name, "pistas": len(o.ctx.tracks), "actual": _dist(o),
            "propuesto": v.genre or "unknown", "confianza": f"{v.confidence:.2f}",
            "estado": o.status, "pistas_a_cambiar": len(o.changes),
            "excepciones": exc, "motivo": v.reason,
        })

    try:
        res = genre_ai.run(
            apply=args.apply, limit=args.limit, force=args.force,
            only_missing=args.only_missing, suspicious=args.suspicious,
            names=args.artist, on_outcome=show,
        )
    except LLMNotConfigured as e:
        print(e)
        return 2
    except KeyboardInterrupt:
        print("\ninterrumpido: lo ya procesado queda guardado, relanza para continuar")
        return 130

    c = Counter(o.status for o in res.outcomes)
    print(f"\nartistas procesados: {len(res.outcomes)} · aplicables: {c['applied']} · "
          f"a revisión: {c['pending']} · sin decidir: {c['skipped']} · peticiones: {res.requests}")
    print(f"pistas cambiadas: {sum(len(o.changes) for o in res.outcomes)}")
    for e in res.errors[:5]:
        print(f"  error: {e}")
    if res.quota_exceeded:
        espera = f" (el proveedor pide esperar ~{int(res.retry_after)}s)" if res.retry_after else ""
        print(f"\nCUOTA DEL PROVEEDOR AGOTADA{espera}. Quedan ~{res.remaining} artistas.")
        print("Relanza el mismo comando más tarde: continúa donde lo dejó."
              if args.apply else
              "Esto era un simulacro y no guarda progreso; con --apply sí es reanudable.")
    if not args.apply:
        print("\nsimulacro: no se ha tocado ni un fichero ni una fila")
    elif c["pending"]:
        print("\nrevisa las sugerencias en Admin → Géneros con IA")

    if args.report:
        with open(args.report, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["artista"])
            w.writeheader()
            w.writerows(rows)
        print(f"informe en {args.report}")
    return 1 if res.quota_exceeded else 0


if __name__ == "__main__":
    sys.exit(main())
