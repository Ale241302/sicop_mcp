# -*- coding: utf-8 -*-
"""Barrido: donde declara SICOP la confidencialidad de informacion.
Regla del skill: antes de declarar que un dato no existe, barrer TODOS los campos."""
import csv, sys, glob, os
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10**9)
B = r"C:\DeepSeek Harness\salida"

TERMINOS = ["CONFIDENCIAL", "SECRETO", "RESERVA", "PRIVAD", "RESTRINGID",
            "DIVULGA", "PUBLICID", "SENSIBLE"]

# --- 1) nombres de columna en TODOS los archivos
print("=" * 74)
print("1) COLUMNAS cuyo nombre menciona confidencialidad")
print("=" * 74)
hallado_col = defaultdict(list)
esquemas = {}
for p in sorted(glob.glob(os.path.join(B, "*.csv"))):
    n = os.path.basename(p)
    try:
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            cab = csv.DictReader(f).fieldnames or []
    except Exception:
        continue
    base = n.rsplit("_", 1)[0] if n[-8:-4].isdigit() else n[:-4]
    esquemas.setdefault(base, cab)
    for c in cab:
        cu = c.upper()
        for t in TERMINOS:
            if t in cu:
                hallado_col[base].append(c)
if hallado_col:
    for tab, cols in hallado_col.items():
        print(f"   {tab}: {sorted(set(cols))}")
else:
    print("   NINGUNA columna con esos terminos en su nombre.")

# --- 2) valores de texto que mencionen confidencialidad
print("\n" + "=" * 74)
print("2) VALORES que mencionan confidencialidad (muestra por tabla)")
print("=" * 74)
LIM = 250000   # filas por archivo, para no tardar horas
ejemplos = defaultdict(list)
conteo = defaultdict(int)
for p in sorted(glob.glob(os.path.join(B, "*.csv"))):
    n = os.path.basename(p)
    base = n.rsplit("_", 1)[0] if n[-8:-4].isdigit() else n[:-4]
    if base in ("invitaciones",):     # 2 GB, sin texto libre util
        continue
    try:
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            for i, row in enumerate(csv.DictReader(f)):
                if i >= LIM: break
                for k, v in row.items():
                    if not v or len(v) < 6: continue
                    vu = v.upper()
                    for t in TERMINOS:
                        if t in vu:
                            conteo[(base, k)] += 1
                            if len(ejemplos[(base, k)]) < 2:
                                ejemplos[(base, k)].append(v[:220])
                            break
    except Exception as e:
        print(f"   [skip] {n}: {e}")

if conteo:
    for (tab, campo), c in sorted(conteo.items(), key=lambda kv: -kv[1])[:25]:
        print(f"\n   {tab}.{campo}  -> {c:,} filas")
        for e in ejemplos[(tab, campo)]:
            print(f"      \"{e}\"")
else:
    print("   NINGUN valor con esos terminos.")

# --- 3) esquema de evaluacion_ofertas (donde podria vivir el regimen)
print("\n" + "=" * 74)
print("3) ESQUEMA de evaluacion_ofertas — pendiente abierto del skill")
print("=" * 74)
if "evaluacion_ofertas" in esquemas:
    for c in esquemas["evaluacion_ofertas"]:
        print(f"   {c}")
else:
    print("   no encontrado")
