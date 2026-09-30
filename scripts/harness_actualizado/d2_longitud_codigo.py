# -*- coding: utf-8 -*-
"""
D2 — ANATOMIA DEL CODIGO DE PRODUCTO: verificacion de longitudes.

Hipotesis (research swarm 2026-08-24): Hacienda documenta codigos anidados
de 8 / 16 / 24 digitos. Si el campo trae longitudes mixtas, buena parte del
problema de identidad de producto se resuelve con un GROUP BY sobre el prefijo
y NO con entity resolution.

Salida: distribucion de longitudes por archivo y por campo, y prueba de
anidamiento (¿los codigos de 24 empiezan por un codigo de 16 que existe?).
"""
import csv, os, sys, glob
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10**9)

BASE = r"C:\DeepSeek Harness\salida"

CAMPOS = ["CODIGO_PRODUCTO", "CODIGO_PRODUCTO_CL", "codigo_producto",
          "codigo_producto_cl", "COD_PRODUCTO", "cod_producto",
          "CODIGO_IDENTIFICACION", "codigo_identificacion"]

def leer(path, limite=None):
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        r = csv.DictReader(f)
        for i, row in enumerate(r):
            if limite and i >= limite:
                break
            yield row

def main():
    archivos = sorted(glob.glob(os.path.join(BASE, "*.csv")))
    universo_por_len = defaultdict(set)   # longitud -> set de codigos
    por_archivo = {}

    for path in archivos:
        nombre = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
                cab = csv.DictReader(f).fieldnames or []
        except Exception as e:
            print(f"[skip] {nombre}: {e}")
            continue

        presentes = [c for c in cab if c in CAMPOS]
        if not presentes:
            continue

        cnt = defaultdict(Counter)
        n = 0
        try:
            for row in leer(path):
                n += 1
                for c in presentes:
                    v = (row.get(c) or "").strip()
                    if v:
                        cnt[c][len(v)] += 1
                        universo_por_len[len(v)].add(v)
        except Exception as e:
            print(f"[parcial] {nombre} tras {n} filas: {e}")

        por_archivo[nombre] = (n, {c: dict(cnt[c]) for c in presentes})

    print("=" * 78)
    print("DISTRIBUCION DE LONGITUDES POR ARCHIVO Y CAMPO")
    print("=" * 78)
    for nombre in sorted(por_archivo):
        n, campos = por_archivo[nombre]
        print(f"\n{nombre}  ({n:,} filas)")
        for c, d in campos.items():
            if not d:
                continue
            tot = sum(d.values())
            detalle = "  ".join(
                f"len={k}: {v:,} ({100.0*v/tot:.1f}%)"
                for k, v in sorted(d.items(), key=lambda kv: -kv[1])
            )
            print(f"   {c:24s} {detalle}")

    print("\n" + "=" * 78)
    print("UNIVERSO GLOBAL DE CODIGOS DISTINTOS POR LONGITUD")
    print("=" * 78)
    for L in sorted(universo_por_len):
        print(f"   len={L:3d} -> {len(universo_por_len[L]):,} codigos distintos")

    # PRUEBA DE ANIDAMIENTO
    print("\n" + "=" * 78)
    print("PRUEBA DE ANIDAMIENTO")
    print("=" * 78)
    c8  = universo_por_len.get(8,  set())
    c16 = universo_por_len.get(16, set())
    c24 = universo_por_len.get(24, set())
    print(f"   distintos: 8={len(c8):,}  16={len(c16):,}  24={len(c24):,}")

    if c24 and c16:
        hit = sum(1 for x in c24 if x[:16] in c16)
        print(f"   de 24, con prefijo[:16] presente en el universo de 16: "
              f"{hit:,}/{len(c24):,} ({100.0*hit/len(c24):.1f}%)")
    if c24 and c8:
        hit = sum(1 for x in c24 if x[:8] in c8)
        print(f"   de 24, con prefijo[:8] presente en el universo de 8:  "
              f"{hit:,}/{len(c24):,} ({100.0*hit/len(c24):.1f}%)")
    if c16 and c8:
        hit = sum(1 for x in c16 if x[:8] in c8)
        print(f"   de 16, con prefijo[:8] presente en el universo de 8:  "
              f"{hit:,}/{len(c16):,} ({100.0*hit/len(c16):.1f}%)")

    # colapso: cuantos codigos de 24 colapsan a cada prefijo de 16
    if c24:
        col = Counter(x[:16] for x in c24)
        print(f"\n   colapso 24 -> prefijo 16: {len(c24):,} codigos -> {len(col):,} grupos")
        print(f"   grupos con >1 codigo: {sum(1 for v in col.values() if v > 1):,}")
        print("   top 10 prefijos mas poblados:")
        for k, v in col.most_common(10):
            print(f"      {k}  -> {v} codigos de 24")

    print("\nLECTURA: si el % de anidamiento es alto (>90%), el GROUP BY por")
    print("prefijo es valido y sustituye entity resolution para agrupar familia.")
    print("Si es bajo, los tres largos son universos separados y NO anidados.")

if __name__ == "__main__":
    main()
