# -*- coding: utf-8 -*-
"""DeepSeek G7(a): el esquema de la fuente cambia por anio.
El diseno asume esquema estable ('columna nueva = BLOQUEADO').
Verificar: que columnas aparecen/desaparecen entre 2020 y 2026."""
import csv, sys, glob, os
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10**9)
B = r"C:\DeepSeek Harness\salida"

# conjunto -> anio -> set(columnas)
esq = defaultdict(dict)
for p in sorted(glob.glob(os.path.join(B, "*.csv"))):
    n = os.path.basename(p)
    if not n[-8:-4].isdigit():
        continue
    base = n.rsplit("_", 1)[0]
    anio = n[-8:-4]
    try:
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            cab = csv.DictReader(f).fieldnames or []
        esq[base][anio] = set(c for c in cab
                              if c not in ("ARCHIVO_ORIGEN", "MES_PUBLICACION"))
    except Exception as e:
        print(f"[skip] {n}: {e}")

print("=" * 78)
print("DERIVA DE ESQUEMA POR ANIO — conjuntos con columnas que no estan en todos")
print("=" * 78)

inestables = 0
for base in sorted(esq):
    anios = sorted(esq[base])
    if len(anios) < 2:
        continue
    todas = set().union(*esq[base].values())
    comunes = set.intersection(*esq[base].values())
    volatiles = todas - comunes
    if not volatiles:
        continue
    inestables += 1
    print(f"\n{base}  ({len(anios)} anios: {anios[0]}-{anios[-1]})")
    print(f"   columnas estables: {len(comunes)} · volatiles: {len(volatiles)}")
    for c in sorted(volatiles):
        presente = [a for a in anios if c in esq[base][a]]
        ausente = [a for a in anios if c not in esq[base][a]]
        print(f"   · {c}")
        print(f"       presente: {','.join(presente)}")
        print(f"       AUSENTE : {','.join(ausente)}")

print(f"\n{'=' * 78}")
print(f"conjuntos con esquema inestable: {inestables} de {len(esq)}")
print("=" * 78)
if inestables:
    print("\nCONSECUENCIA: toda serie multianual sobre una columna volatil tiene")
    print("huecos estructurales, no faltantes aleatorios. Hay que declarar el mapeo")
    print("por anio ANTES de prometer series 2020-2026 limpias.")
