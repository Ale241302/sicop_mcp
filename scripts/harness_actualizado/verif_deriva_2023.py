# -*- coding: utf-8 -*-
"""Kimi P3/K2 refuta mi hallazgo: el CL vacio en 2023 NO seria hueco,
porque el codigo de 24 esta y su prefijo[:16] ES el CL.
Verificar: de las filas con CL vacio, cuantas traen CODIGO_PRODUCTO de 24?"""
import csv, sys, glob, os
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10**9)
B = r"C:\DeepSeek Harness\salida"

print("=" * 74)
print("El 'hueco' de CODIGO_PRODUCTO_CL: real o derivable?")
print("=" * 74)

total_global = vacio_global = derivable_global = 0

for p in sorted(glob.glob(os.path.join(B, "lineas_ofertadas_*.csv"))):
    anio = os.path.basename(p)[-8:-4]
    tot = cl_vacio = derivable = no_derivable = 0
    largos = Counter()
    with open(p, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            tot += 1
            cl = (row.get("CODIGO_PRODUCTO_CL") or "").strip()
            if cl:
                continue
            cl_vacio += 1
            c24 = (row.get("CODIGO_PRODUCTO") or "").strip()
            largos[len(c24)] += 1
            if len(c24) == 24:
                derivable += 1
            else:
                no_derivable += 1
    total_global += tot
    vacio_global += cl_vacio
    derivable_global += derivable

    if cl_vacio == 0:
        print(f"\n{anio}: {tot:>8,} filas · CL completo, nada que derivar")
        continue
    pct_vacio = 100.0 * cl_vacio / max(tot, 1)
    pct_der = 100.0 * derivable / max(cl_vacio, 1)
    print(f"\n{anio}: {tot:>8,} filas · CL vacio en {cl_vacio:>7,} ({pct_vacio:.1f}%)")
    print(f"      de esos, con CODIGO_PRODUCTO de 24 digitos: "
          f"{derivable:>7,} ({pct_der:.1f}%)  <-- DERIVABLE por [:16]")
    if no_derivable:
        print(f"      NO derivables: {no_derivable:,} · largos: {dict(largos)}")

print("\n" + "=" * 74)
print(f"GLOBAL: {vacio_global:,} filas con CL vacio · "
      f"{derivable_global:,} derivables ({100.0*derivable_global/max(vacio_global,1):.2f}%)")
print("=" * 74)
if vacio_global and derivable_global == vacio_global:
    print("\nVEREDICTO: Kimi tiene razon. NO es un hueco de dato, es un hueco de CAMPO.")
    print("La regla  cl = coalesce(CODIGO_PRODUCTO_CL, CODIGO_PRODUCTO[:16])  lo cierra.")
elif vacio_global:
    falta = vacio_global - derivable_global
    print(f"\nVEREDICTO: derivable en su mayoria, pero quedan {falta:,} filas "
          f"({100.0*falta/vacio_global:.2f}%) sin forma de derivar.")
