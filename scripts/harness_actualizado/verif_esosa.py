# -*- coding: utf-8 -*-
"""Verificacion de la ficha ESOSA: moneda, clave de linea, recursos."""
import csv, sys, glob, os
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10**9)
B = r"C:\DeepSeek Harness\salida"

ESOSA  = "3101086562"
SONDEL = "3101095926"
OBJ = {ESOSA: "ESOSA", SONDEL: "SONDEL"}

def f(x):
    try: return float(x)
    except Exception: return 0.0

# ---- 1) ejecucion por moneda y anio
ej = defaultdict(float)          # (quien, anio, moneda) -> monto
ordn = defaultdict(set)
vistos_orden = set()
vistos_linea = set()
dup_linea = 0

for p in sorted(glob.glob(os.path.join(B, "ordenes_pedido_*.csv"))):
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            ced = (row.get("CEDULAPROVEEDOR") or "").strip()
            if ced not in OBJ: continue
            quien = OBJ[ced]
            o = (row.get("NRO_ORDEN") or "").strip()
            li = (row.get("LINEA_ORD_PEDIDO") or "").strip()
            anio = (row.get("FECHA_ELABORACION_ORDEN") or "")[:4]
            mon = (row.get("MONEDA_ORDEN") or "?").strip().upper()
            t = f(row.get("TOTAL_ORDEN"))
            kl = (o, li)
            if kl in vistos_linea:
                dup_linea += 1
                continue
            vistos_linea.add(kl)
            if o in vistos_orden:      # ya contamos el TOTAL_ORDEN de esta orden
                continue
            vistos_orden.add(o)
            ej[(quien, anio, mon)] += t
            ordn[(quien, anio)].add(o)

print("=" * 74)
print("EJECUCION POR MONEDA — la pregunta que decide la ficha")
print("=" * 74)
for quien in ("ESOSA", "SONDEL"):
    print(f"\n--- {quien} ---")
    anios = sorted({a for (q, a, m) in ej if q == quien and a >= "2020"})
    for a in anios:
        monedas = {m: v for (q, an, m), v in ej.items() if q == quien and an == a}
        if not monedas: continue
        tot = " · ".join(f"{m} {v/1e6:,.1f}M" for m, v in
                         sorted(monedas.items(), key=lambda kv: -kv[1]))
        print(f"  {a}: {tot}   ({len(ordn[(quien, a)])} ordenes)")

print(f"\nlineas duplicadas descartadas por (NRO_ORDEN, LINEA_ORD_PEDIDO): {dup_linea:,}")

# ---- 2) recursos: contar y ver el campo
rec = defaultdict(lambda: defaultdict(int))
cols = None
for p in sorted(glob.glob(os.path.join(B, "recursos_*.csv"))):
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        r = csv.DictReader(fh)
        cols = r.fieldnames
        for row in r:
            blob = " ".join((row.get(c) or "") for c in (cols or []))
            for ced, quien in OBJ.items():
                if ced in blob:
                    rec[quien]["total"] += 1
                    res = (row.get("RESULTADO") or "").strip() or "(vacio)"
                    rec[quien][res] += 1

print("\n" + "=" * 74)
print("RECURSOS (busqueda por cedula en toda la fila)")
print("=" * 74)
for quien in ("ESOSA", "SONDEL"):
    d = rec.get(quien, {})
    print(f"\n{quien}: total={d.get('total', 0)}")
    for k, v in sorted(d.items(), key=lambda kv: -kv[1]):
        if k != "total":
            print(f"    {k}: {v}")

# ---- 3) sanciones con vigencia
print("\n" + "=" * 74)
print("SANCIONES — con fechas de vigencia")
print("=" * 74)
hay = False
for p in sorted(glob.glob(os.path.join(B, "sanciones_registro_*.csv"))):
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            blob = " ".join((row.get(c) or "") for c in row)
            for ced, quien in OBJ.items():
                if ced in blob:
                    hay = True
                    campos = {k: v for k, v in row.items()
                              if v and ("SANCION" in k.upper() or "FECHA" in k.upper()
                                        or "TIPO" in k.upper() or "ESTADO" in k.upper())}
                    print(f"  {quien}: {campos}")
if not hay:
    print("  (ninguna encontrada por cedula)")
