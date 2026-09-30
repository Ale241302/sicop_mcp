# -*- coding: utf-8 -*-
"""Verificacion del trabajo del obrero sobre ordenes_pedido."""
import csv, sys, glob, os
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10**9)
B = r"C:\DeepSeek Harness\salida"

tot_filas = 0
ordenes = set()
par_lin = set()
sec_vals = Counter()
lin_por_orden = defaultdict(set)
# suma con y sin dedupe, año 2026 por FECHA_ELABORACION_ORDEN
suma_cruda = 0.0
suma_dedup = 0.0
vistos = set()
outliers = []
prov26 = defaultdict(float)
prov26_ord = defaultdict(set)

for path in sorted(glob.glob(os.path.join(B, "ordenes_pedido_*.csv"))):
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            tot_filas += 1
            o = (row.get("NRO_ORDEN") or "").strip()
            l = (row.get("LINEA_ORD_PEDIDO") or "").strip()
            s = (row.get("SECUENCIA") or "").strip()
            sec_vals[s] += 1
            if o:
                ordenes.add(o)
                par_lin.add((o, l))
                lin_por_orden[o].add(l)
            fe = (row.get("FECHA_ELABORACION_ORDEN") or "")[:4]
            try:
                t = float(row.get("TOTAL_ORDEN") or 0)
            except Exception:
                t = 0.0
            mon = (row.get("MONEDA_ORDEN") or "").strip().upper()
            if fe == "2026" and mon == "CRC":
                suma_cruda += t
                if o not in vistos:
                    vistos.add(o)
                    suma_dedup += t
                    prov26[row.get("NOMBRE_PROVEEDOR", "")] += t
                    prov26_ord[row.get("NOMBRE_PROVEEDOR", "")].add(o)
            if t > 1e12:
                outliers.append((o, t, row.get("NOMBRE_PROVEEDOR", ""), fe, mon))

print(f"filas totales ordenes_pedido_*.csv : {tot_filas:,}")
print(f"NRO_ORDEN distintos                : {len(ordenes):,}")
print(f"(NRO_ORDEN, LINEA_ORD_PEDIDO) dist : {len(par_lin):,}")
print(f"factor inflacion filas/orden       : {tot_filas/max(len(ordenes),1):.2f}x")
print(f"\nSECUENCIA valores distintos: {len(sec_vals)} -> {dict(sec_vals.most_common(10))}")
mult = sum(1 for o, s in lin_por_orden.items() if len(s) > 1)
print(f"ordenes con >1 LINEA_ORD_PEDIDO: {mult:,} ({100.0*mult/max(len(lin_por_orden),1):.1f}%)")
print(f"max lineas en una orden: {max((len(s) for s in lin_por_orden.values()), default=0)}")

print("\n--- 2026 por FECHA_ELABORACION_ORDEN, moneda CRC ---")
print(f"suma TOTAL_ORDEN cruda   : {suma_cruda/1e6:,.0f} M CRC")
print(f"suma dedupe por NRO_ORDEN: {suma_dedup/1e6:,.0f} M CRC")
print(f"inflacion si no se dedupe: {suma_cruda/max(suma_dedup,1):.2f}x")

print(f"\noutliers TOTAL_ORDEN > 1e12: {len(outliers)}")
for o, t, p, fe, m in sorted(outliers, key=lambda x: -x[1])[:8]:
    print(f"   {o}  {t:,.0f} {m}  {fe}  {p[:50]}")

lim = sum(t for _, t, _, fe, m in outliers if fe == "2026" and m == "CRC")
print(f"\naporte de outliers al total 2026 CRC: {lim/1e6:,.0f} M "
      f"({100.0*lim/max(suma_dedup,1):.1f}% del dedupe)")
print(f"2026 CRC SIN outliers: {(suma_dedup-lim)/1e6:,.0f} M CRC")

print("\n--- top 10 proveedores 2026 por ejecucion (dedupe, CRC, sin filtrar outliers) ---")
for p, v in sorted(prov26.items(), key=lambda kv: -kv[1])[:10]:
    print(f"   {v/1e6:>12,.0f} M  {len(prov26_ord[p]):>5} ord  {p[:55]}")

son = [p for p in prov26 if "SONDEL" in p.upper()]
for p in son:
    print(f"\nSONDEL 2026: {prov26[p]/1e6:,.1f} M CRC en {len(prov26_ord[p])} ordenes  [{p}]")
