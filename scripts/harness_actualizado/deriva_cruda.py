# -*- coding: utf-8 -*-
"""El extractor normaliza columnas: si la fuente no trae una, la escribe vacia.
Eso ENMASCARA la deriva. Verificar en el ZIP crudo y medir llenado real."""
import zipfile, csv, io, sys, glob, os
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10**9)
CACHE = r"C:\DeepSeek Harness\salida\_cache"
SALIDA = r"C:\DeepSeek Harness\salida"

OBJETIVO = {
    "LineasOfertadas.csv": ["CODIGO_PRODUCTO_CL", "CODIGO_PRODUCTO"],
    "Sistemas.csv": [],
    "Garantias.csv": ["garantia_NM"],
}

def decodificar(raw):
    for enc in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return None

print("=" * 78)
print("1) PRESENCIA DEL MIEMBRO Y DE LA COLUMNA EN EL ZIP CRUDO, POR ANIO")
print("=" * 78)

por_anio = defaultdict(lambda: defaultdict(lambda: {"zips": 0, "con_miembro": 0,
                                                    "cols": set()}))
for zp in sorted(glob.glob(os.path.join(CACHE, "*.zip"))):
    anio = os.path.basename(zp)[:4]
    try:
        with zipfile.ZipFile(zp) as z:
            nombres = {m.split("/")[-1].lower(): m for m in z.namelist()}
            for miembro, cols_interes in OBJETIVO.items():
                d = por_anio[miembro][anio]
                d["zips"] += 1
                m = nombres.get(miembro.lower())
                if not m:
                    continue
                d["con_miembro"] += 1
                raw = z.read(m)[:200000]
                txt = decodificar(raw)
                if txt:
                    linea = txt.split("\n", 1)[0]
                    delim = ";" if linea.count(";") > linea.count(",") else ","
                    d["cols"] |= set(c.strip().strip('"')
                                     for c in linea.split(delim))
    except Exception as e:
        print(f"[skip] {os.path.basename(zp)}: {e}")

for miembro in OBJETIVO:
    print(f"\n--- {miembro} ---")
    for anio in sorted(por_anio[miembro]):
        d = por_anio[miembro][anio]
        print(f"  {anio}: en {d['con_miembro']}/{d['zips']} zips · "
              f"{len(d['cols'])} columnas")
        for c in OBJETIVO[miembro]:
            estado = "SI" if c in d["cols"] else "** NO **"
            print(f"        {c}: {estado}")

print("\n" + "=" * 78)
print("2) LLENADO REAL EN EL CSV EXTRAIDO (la mascara)")
print("=" * 78)
for campo, patron in [("CODIGO_PRODUCTO_CL", "lineas_ofertadas_*.csv")]:
    print(f"\n{campo} en {patron}:")
    for p in sorted(glob.glob(os.path.join(SALIDA, patron))):
        anio = os.path.basename(p)[-8:-4]
        tot = lleno = 0
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            r = csv.DictReader(f)
            if campo not in (r.fieldnames or []):
                print(f"  {anio}: la columna NO existe en el CSV")
                continue
            for row in r:
                tot += 1
                if (row.get(campo) or "").strip():
                    lleno += 1
        pct = 100.0 * lleno / max(tot, 1)
        marca = "  <-- HUECO ESTRUCTURAL" if pct < 50 else ""
        print(f"  {anio}: {lleno:>8,} de {tot:>8,} ({pct:>5.1f}%){marca}")
