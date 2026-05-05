"""
auditar_chunks.py - Detecta articulos mutilados/cortos en ChromaDB.

Diagnostico para el bug de chunking visto en stress test:
  "Articulo 416. , la pena de prision podra aumentar hasta ocho anos."
  "Articulo 413. - Cuando el delito previsto en el"

Estrategia:
  1) Agregar todos los chunks por (ley, articulo) -> texto unificado
  2) Marcar como MUTILADO solo si:
       - texto agregado < umbral chars  (DEFAULT 60), o
       - texto coincide con patron "solo encabezado + fragmento minimo"
  3) Reportar ranking por ley y top ejemplos

Uso:
  python auditar_chunks.py
  python auditar_chunks.py --umbral 60
  python auditar_chunks.py --ley "Codigo Penal"
  python auditar_chunks.py --csv salida.csv
"""
from __future__ import annotations
import argparse
import re
import sys
from collections import defaultdict

import chromadb
import config


# Patrones que sugieren mutilacion grave (encabezado + cuerpo trivial)
RX_HEAD_VACIO = re.compile(r"^\s*Art[ií]culo\s+\d+[A-Z\-]?\s*\.?\s*$", re.IGNORECASE)
RX_HEAD_FRAGMENTO = re.compile(
    r"^\s*Art[ií]culo\s+\d+[A-Z\-]?\s*\.?\s*[,\.\-—:]?\s*\S{0,40}\s*$",
    re.IGNORECASE,
)

CORTES_FINALES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "en", "con", "por", "para", "a", "ante",
    "que", "y", "o", "u", "su", "sus", "este", "esta", "ese",
    "esa", "al", "como", "sobre", "entre", "sin",
}


def _termina_cortado(t: str) -> bool:
    t = t.strip()
    if not t:
        return False
    palabras = t.split()
    if not palabras:
        return False
    final = palabras[-1].lower().strip(".,;:!?\"'»)]")
    return final in CORTES_FINALES and t[-1] not in ".;:!?"


def _clasificar(texto_agregado: str, umbral: int) -> tuple[bool, str]:
    """Devuelve (es_mutilado, razon). Diseñado para ALTA precision."""
    t = (texto_agregado or "").strip()
    n = len(t)

    if n == 0:
        return True, "VACIO"

    if RX_HEAD_VACIO.match(t):
        return True, f"HEAD_VACIO({n})"

    if n < 30:
        return True, f"MUY_CORTO({n})"

    # "Articulo X." + 0-40 caracteres no triviales
    if RX_HEAD_FRAGMENTO.match(t) and n < umbral:
        return True, f"HEAD_FRAG({n})"

    # < umbral Y termina en preposicion/conjuncion -> probable corte
    if n < umbral and _termina_cortado(t):
        return True, f"CORTE_PREP({n})"

    # < umbral Y empieza con "Articulo X." -> head + body insuficiente
    if n < umbral and re.match(r"^\s*Art[ií]culo\s+\d+", t, re.IGNORECASE):
        return True, f"HEAD_CORTO({n})"

    return False, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--umbral", type=int, default=60,
                    help="Caracteres minimos para no marcar como corto (default 60)")
    ap.add_argument("--ley", type=str, default=None)
    ap.add_argument("--csv", type=str, default=None)
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    print(f"[*] ChromaDB: {config.DB_PATH}")
    client = chromadb.PersistentClient(path=str(config.DB_PATH))
    col = client.get_collection("leyes_venezolanas")
    n_total = col.count()
    print(f"[*] Total chunks: {n_total}")
    print(f"[*] Umbral de corto: {args.umbral} chars\n")

    # PASO 1: traer TODO y agregar por (ley, articulo)
    BATCH = 5000
    agregado: dict[tuple, list[str]] = defaultdict(list)
    offset = 0
    while offset < n_total:
        r = col.get(limit=BATCH, offset=offset, include=["documents", "metadatas"])
        for doc, meta in zip(r["documents"], r["metadatas"]):
            ley = (meta or {}).get("ley", "?")
            art = (meta or {}).get("articulo", "?")
            if args.ley and ley != args.ley:
                continue
            agregado[(ley, art)].append(doc or "")
        offset += BATCH
        sys.stdout.write(f"\r[*] Escaneados {min(offset, n_total)}/{n_total}...")
        sys.stdout.flush()
    print()
    print(f"[*] Articulos unicos (ley, art): {len(agregado)}\n")

    # PASO 2: clasificar cada articulo unico
    sospechosos: list[dict] = []
    por_ley: dict[str, dict] = defaultdict(
        lambda: {"total": 0, "mutilados": 0, "min_len": 99999}
    )
    for (ley, art), chunks in agregado.items():
        # Concatenar todos los chunks del articulo
        texto = "\n".join(c for c in chunks if c)
        # Para casos donde el articulo se chunkea: si UN chunk individual es mutilado
        # PERO el agregado es saludable, NO marcar.
        mut_agregado, razon = _clasificar(texto, args.umbral)
        por_ley[ley]["total"] += 1
        por_ley[ley]["min_len"] = min(por_ley[ley]["min_len"], len(texto))
        if mut_agregado:
            por_ley[ley]["mutilados"] += 1
            sospechosos.append({
                "ley": ley, "art": art, "razon": razon,
                "len": len(texto), "n_chunks": len(chunks),
                "texto": texto[:300],
            })

    # ─── REPORTE ─────────────────────────────────────────────────────────────
    print("=" * 80)
    print(f"REPORTE - {len(sospechosos)} articulos sospechosos de {len(agregado)} totales")
    print("=" * 80)

    ranking = sorted(por_ley.items(), key=lambda kv: (-kv[1]["mutilados"], kv[0]))
    print(f"\n{'LEY':<60} {'TOTAL':>6} {'MUT':>5} {'%':>6} {'MIN':>6}")
    print("-" * 90)
    for ley, info in ranking[:args.top]:
        if info["mutilados"] == 0:
            continue
        pct = (info["mutilados"] / info["total"]) * 100 if info["total"] else 0
        print(f"{ley[:58]:<60} {info['total']:>6} {info['mutilados']:>5} {pct:>5.1f}% {info['min_len']:>6}")

    print("\n" + "=" * 80)
    print(f"TOP {min(40, len(sospechosos))} ARTICULOS MAS CORTOS / SOSPECHOSOS")
    print("=" * 80)
    sospechosos_ord = sorted(sospechosos, key=lambda x: x["len"])[:40]
    for s in sospechosos_ord:
        # ASCII-only: evitar caracteres unicode que rompen cp1252
        try:
            t = s["texto"].encode("ascii", "replace").decode("ascii")
        except Exception:
            t = s["texto"]
        print(f"\n[{s['razon']}] {s['ley']}, Art. {s['art']} ({s['n_chunks']} chunks)")
        print(f"   -> {t!r}")

    if args.csv:
        import csv
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ley", "articulo", "razon", "longitud", "n_chunks", "texto"])
            for s in sorted(sospechosos, key=lambda x: (x["ley"], x["len"])):
                w.writerow([s["ley"], s["art"], s["razon"], s["len"], s["n_chunks"], s["texto"]])
        print(f"\n[OK] Exportado a {args.csv}")

    total_mut = sum(p["mutilados"] for p in por_ley.values())
    total_arts = sum(p["total"] for p in por_ley.values())
    pct = (total_mut / total_arts * 100) if total_arts else 0
    leyes_afectadas = sum(1 for p in por_ley.values() if p["mutilados"] > 0)
    print("\n" + "=" * 80)
    print(f"RESUMEN GLOBAL: {total_mut}/{total_arts} articulos mutilados ({pct:.2f}%)")
    print(f"Leyes afectadas: {leyes_afectadas}/{len(por_ley)}")
    print("=" * 80)


if __name__ == "__main__":
    main()
