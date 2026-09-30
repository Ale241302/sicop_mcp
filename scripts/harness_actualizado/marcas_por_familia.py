# -*- coding: utf-8 -*-
"""
marcas_por_familia.py — extrae Marca y Modelo de las tablas de EJECUCION.

La marca NO esta en las tablas del proceso de compra (cartel/adjudicacion).
Vive embebida en la descripcion del producto contratado y recibido, con el
patron `Marca <X> Modelo <Y>` en ~99,6% de las lineas.

Uso:
  python marcas_por_familia.py --codigo 461816
  python marcas_por_familia.py --codigo 461816 --marca MARLUVAS
  python marcas_por_familia.py --codigo 461816 --csv marcas.csv
"""
import csv, io, os, re, argparse
from collections import Counter, defaultdict

BASE = os.environ.get("SICOP_SALIDA", r"C:\DeepSeek Harness\salida")
ANIOS = range(2020, 2027)
csv.field_size_limit(10 * 1024 * 1024)

# Las dos tablas de ejecucion y su columna de descripcion (el nombre difiere en mayusculas).
FUENTES = [("lineas_contratadas", "DESC_PRODUCTO"), ("lineas_recibidas", "desc_producto")]
# CASE-SENSITIVE: la fuente capitaliza siempre `Marca`/`Modelo`. Verificado sobre
# 2.059 lineas reales: identica cobertura que re.I (99,6%), pero sin convertir
# "BOTA SIN MARCA NI MODELO DECLARADO" en Marca=NI / Modelo=DECLARADO.
RX = re.compile(r"\bMarca\s+(.+?)\s+Modelo\s+(.+)$")

# lista de descarte versionada v1 — misma que sicop_loop.py (catalogo_productos)
DESCARTE = {
    "LIBRO", "NACIONAL", "SEGÚN OFERTA", "SEGUN OFERTA", "INTECO",
    "SIN REGISTRO", "NINGUNA", "VARIOS", "GENERICO", "TOTAL", "NO APLICA",
    "NA", "SN", "N/A", "-", "—", ".", "*", "SEGUN MUESTRA", "SEGÚN MUESTRA",
    "A DEFINIR", "POR DEFINIR", "NO INDICA", "NO DECLARADO",
}


def plausible(t):
    t = (t or "").strip()
    if not t or len(t) < 3 or t.isdigit():
        return False
    return t.upper() not in DESCARTE


def leer(nombre, year):
    for cand in (f"{nombre}_{year}.csv", f"{nombre}.csv"):
        p = os.path.join(BASE, cand)
        if os.path.exists(p):
            with io.open(p, "r", encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    yield r
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codigo", required=True, help="prefijo UNSPSC, ej 461816")
    ap.add_argument("--marca", help="filtrar por marca (substring, case-insensitive)")
    ap.add_argument("--csv", help="ruta de salida con el detalle por linea")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()

    nombres = {}
    for y in ANIOS:
        for r in leer("proveedores", y):
            c = (r.get("CEDULA_PROVEEDOR") or "").strip()
            if c:
                nombres.setdefault(c, (r.get("NOMBRE_PROVEEDOR") or c).strip())

    marca = Counter(); modelos = defaultdict(Counter)
    prov = defaultdict(Counter); filas = []
    tot = sin_parse = sin_plausible = 0

    for y in ANIOS:
        for tabla, col in FUENTES:
            for r in leer(tabla, y):
                if not (r.get("CODIGO_PRODUCTO") or "").startswith(a.codigo):
                    continue
                d = (r.get(col) or "").strip()
                if not d:
                    continue
                tot += 1
                m = RX.search(d)
                if not m:
                    sin_parse += 1
                    continue
                mk = m.group(1).strip().upper()[:40]
                md = m.group(2).strip().upper()[:60]
                if not plausible(mk):
                    sin_plausible += 1
                    continue  # el patrón matcheó pero no es marca (LIBRO, NACIONAL…)
                ced = (r.get("CEDULA_PROVEEDOR") or "").strip()
                marca[mk] += 1; modelos[mk][md] += 1
                if ced:
                    prov[mk][ced] += 1
                filas.append((y, tabla, r.get("NRO_SICOP", ""), r.get("CODIGO_PRODUCTO", ""),
                              mk, md, ced, nombres.get(ced, ced), d))

    if not tot:
        print(f"Sin lineas para el codigo {a.codigo}. Verificar que existan "
              f"lineas_contratadas / lineas_recibidas en {BASE}.")
        return

    print(f"\nCODIGO {a.codigo} · {min(ANIOS)}-{max(ANIOS)}")
    print(f"  lineas con descripcion .... {tot}")
    print(f"  parseadas Marca/Modelo .... {tot - sin_parse}  ({100.0*(tot-sin_parse)/tot:.1f}%)")
    print(f"  marca plausible ........... {tot - sin_parse - sin_plausible}  "
          f"({100.0*(tot-sin_parse-sin_plausible)/tot:.1f}%)  [descarte v1: "
          f"{sin_plausible} tokens como LIBRO/NACIONAL/INTECO…]")
    print(f"  marcas distintas .......... {len(marca)}\n")

    if a.marca:
        pat = a.marca.upper()
        objetivo = [m for m in marca if pat in m]
        if not objetivo:
            print(f"  '{a.marca}' no aparece.")
            return
        for mk in objetivo:
            print(f"--- {mk} · {marca[mk]} lineas ---")
            print("  vendedores:")
            for ced, c in prov[mk].most_common():
                print(f"    {c:>4}  {nombres.get(ced, ced)}  ({ced})")
            print("  modelos:")
            for md, c in modelos[mk].most_common(12):
                print(f"    {c:>4}  {md}")
            print()
    else:
        print(f"--- TOP {a.top} MARCAS ---")
        for mk, c in marca.most_common(a.top):
            top = prov[mk].most_common(1)
            v = nombres.get(top[0][0], "")[:38] if top else ""
            print(f"  {c:>4}  {mk:<32} {v}")

    if a.csv:
        with io.open(a.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ANIO", "TABLA", "NRO_SICOP", "CODIGO_PRODUCTO", "MARCA", "MODELO",
                        "CEDULA_PROVEEDOR", "PROVEEDOR", "DESCRIPCION"])
            for row in filas:
                if a.marca and a.marca.upper() not in row[4]:
                    continue
                w.writerow(row)
        print(f"\nCSV -> {a.csv}")


if __name__ == "__main__":
    main()
