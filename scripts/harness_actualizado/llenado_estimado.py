# -*- coding: utf-8 -*-
"""D1 depende de PRECIO_UNITARIO_ESTIMADO. Cuanto esta poblado realmente?"""
import csv, sys, glob, os
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10**9)
B = r"C:\DeepSeek Harness\salida"

tot = 0
con_valor = 0
cero = 0
vacio = 0
por_anio = Counter()
val_por_anio = Counter()

for p in sorted(glob.glob(os.path.join(B, "lineas_cartel_*.csv"))):
    anio = os.path.basename(p).split("_")[-1][:4]
    with open(p, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            tot += 1
            por_anio[anio] += 1
            v = (row.get("PRECIO_UNITARIO_ESTIMADO") or "").strip()
            if not v:
                vacio += 1
                continue
            try:
                x = float(v)
            except Exception:
                vacio += 1
                continue
            if x > 0:
                con_valor += 1
                val_por_anio[anio] += 1
            else:
                cero += 1

print("=" * 70)
print("PRECIO_UNITARIO_ESTIMADO — el denominador de D1")
print("=" * 70)
print(f"filas totales de lineas_cartel : {tot:,}")
print(f"  con valor > 0                : {con_valor:,} ({100.0*con_valor/max(tot,1):.2f}%)")
print(f"  en cero                      : {cero:,} ({100.0*cero/max(tot,1):.2f}%)")
print(f"  vacio o no numerico          : {vacio:,} ({100.0*vacio/max(tot,1):.2f}%)")

print("\npor anio:")
for a in sorted(por_anio):
    n, v = por_anio[a], val_por_anio[a]
    print(f"  {a}: {v:>8,} de {n:>8,} con valor  ({100.0*v/max(n,1):>5.2f}%)")

# MONTO_RESERVADO como alternativa
print("\n" + "=" * 70)
print("MONTO_RESERVADO — el candidato alternativo")
print("=" * 70)
tot2 = con2 = 0
for p in sorted(glob.glob(os.path.join(B, "lineas_cartel_*.csv"))):
    with open(p, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            tot2 += 1
            v = (row.get("MONTO_RESERVADO") or "").strip()
            try:
                if v and float(v) > 0:
                    con2 += 1
            except Exception:
                pass
print(f"con valor > 0: {con2:,} de {tot2:,} ({100.0*con2/max(tot2,1):.2f}%)")
