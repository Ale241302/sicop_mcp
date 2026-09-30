#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""precios_secuencia.py — la secuencia temporal de precios OFERTADOS de un producto.

Un producto = un CODIGO_PRODUCTO_CL (16 dígitos = UNSPSC + ID_CATALOGO; skill §8:
una talla = un código). Para ese código, une a lo largo de TODOS los años:

  lineas_ofertadas   -> precio unitario ofertado, moneda, TIPO_CAMBIO_CRC, cantidad
  ofertas            -> cédula del oferente (NRO_SICOP + NRO_OFERTA)
  proveedores        -> nombre del oferente
  carteles           -> FECHA_PUBLICACION (el eje del tiempo)
  instituciones      -> nombre de la institución
  adjudicaciones     -> quién ganó la línea (marca ES_ADJUDICATARIO)

Uso:
  python3 precios_secuencia.py --codigo 7210150790004458
  python3 precios_secuencia.py --codigo 7210150790004458 --top 40
  python3 precios_secuencia.py --codigo 7210150790004458 --csv serie.csv

Advertencias honestas:
- El precio unitario baja con el volumen: la serie muestra la cantidad de cada oferta.
- El mismo código puede llevar años con especificaciones equivalentes; el cambio de
  patrón de precios es la señal a mirar, no el valor absoluto.
"""
import argparse
import csv
import glob
import io
import os
import sys
from collections import defaultdict
from statistics import median

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10 * 1024 * 1024)


def num(v):
    try:
        return float(str(v).strip())
    except Exception:
        return 0.0


def a_crc(pu, moneda, tc):
    m = (moneda or "CRC").strip().upper()
    if m == "CRC" or not tc:
        return pu
    return pu * tc


def leer_todas(datos, nombre):
    for p in sorted(glob.glob(os.path.join(datos, f"{nombre}_20*.csv"))):
        with io.open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                yield r


def main():
    ap = argparse.ArgumentParser(description="Secuencia de precios ofertados")
    ap.add_argument("--codigo", required=True, help="CODIGO_PRODUCTO_CL (16 dígitos)")
    ap.add_argument("--datos", default="salida")
    ap.add_argument("--top", type=int, default=30, help="filas a imprimir")
    ap.add_argument("--csv", help="ruta de salida CSV con la serie completa")
    a = ap.parse_args()

    prov = {r["CEDULA_PROVEEDOR"]: (r["NOMBRE_PROVEEDOR"] or r["CEDULA_PROVEEDOR"])
            for r in leer_todas(a.datos, "proveedores") if r.get("CEDULA_PROVEEDOR")}
    cartel = {r["NRO_SICOP"]: r for r in leer_todas(a.datos, "carteles")
              if r.get("NRO_SICOP")}
    inst = {r["CEDULA"]: r["NOMBRE_INSTITUCION"] for r in leer_todas(a.datos, "instituciones")
            if r.get("CEDULA")}

    # ganador por (SICOP, LINEA) — de adjudicaciones
    ganador = {}
    for r in leer_todas(a.datos, "adjudicaciones"):
        if r.get("NRO_SICOP") and r.get("LINEA"):
            ganador[(r["NRO_SICOP"].strip(), str(int(float(r["LINEA"]))).strip()
                     if _isnum(r["LINEA"]) else r["LINEA"].strip())] = r.get("CEDULA_PROVEEDOR", "")

    # cédula por (SICOP, OFERTA)
    ced_oferta = {}
    for r in leer_todas(a.datos, "ofertas"):
        if r.get("NRO_SICOP") and r.get("NRO_OFERTA"):
            ced_oferta[(r["NRO_SICOP"].strip(), r["NRO_OFERTA"].strip())] = \
                r.get("CEDULA_PROVEEDOR", "")

    filas = []
    for r in leer_todas(a.datos, "lineas_ofertadas"):
        if (r.get("CODIGO_PRODUCTO_CL") or "").strip() != a.codigo:
            continue
        ns = (r.get("NRO_SICOP") or "").strip()
        nof = (r.get("NRO_OFERTA") or "").strip()
        ced = ced_oferta.get((ns, nof), "")
        precio = a_crc(num(r.get("PRECIO_UNITARIO_OFERTADO")),
                       r.get("TIPO_MONEDA"), num(r.get("TIPO_CAMBIO_CRC")))
        car = cartel.get(ns, {})
        fecha = (car.get("FECHA_PUBLICACION") or "")[:10]
        ci = (car.get("CEDULA_INSTITUCION") or "").strip()
        linea = (r.get("NRO_LINEA") or "").strip()
        llave = linea
        try:
            llave = str(int(float(linea)))
        except Exception:
            pass
        filas.append({
            "fecha": fecha, "nro_sicop": ns, "institucion": inst.get(ci, ci),
            "oferente": prov.get(ced, ced or "(sin cruce)"), "cedula": ced,
            "precio_crc": precio, "cantidad": num(r.get("CANTIDAD_OFERTADA")),
            "moneda": (r.get("TIPO_MONEDA") or "CRC").strip(),
            "adjudicado": "S" if ced and ganador.get((ns, llave)) == ced else "N",
        })

    filas.sort(key=lambda x: (x["fecha"], x["precio_crc"]))
    print(f"\n== Secuencia de precios ofertados · producto {a.codigo} ==")
    if not filas:
        print("  Sin ofertas para este código (verificar el código: 16 dígitos, "
              "puede filtrar por --codigo 461816 con 8 para familias).")
        return 1

    desc = ""
    p_cat = os.path.join(a.datos, "catalogo_productos.csv")
    if os.path.exists(p_cat):
        with io.open(p_cat, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("CODIGO_PRODUCTO_CL") == a.codigo:
                    desc = r.get("DESCRIPCION", "")
                    break
    if desc:
        print(f"  Descripción: {desc[:120]}")

    precios = [f["precio_crc"] for f in filas if f["precio_crc"] > 0]
    n_adj = sum(1 for f in filas if f["adjudicado"] == "S")
    fechas = [f["fecha"] for f in filas if f["fecha"]]
    print(f"  Ofertas: {len(filas):,} · procedimientos: {len({f['nro_sicop'] for f in filas}):,} "
          f"· oferentes distintos: {len({f['cedula'] for f in filas if f['cedula']}):,} "
          f"· instituciones: {len({f['institucion'] for f in filas if f['institucion']}):,}")
    if fechas:
        print(f"  Período: {min(fechas)} → {max(fechas)}")
    if precios:
        p = sorted(precios)
        med = median(p)
        print(f"  Precio ofertado CRC/und: min {p[0]:,.2f} · p25 {p[len(p)//4]:,.2f} · "
              f"mediana {med:,.2f} · p75 {p[3*len(p)//4]:,.2f} · max {p[-1]:,.2f} "
              f"· adjudicadas {n_adj:,}")
        # mediana por año (tendencia)
        por_anio = defaultdict(list)
        for f in filas:
            if f["fecha"] and f["precio_crc"] > 0:
                por_anio[f["fecha"][:4]].append(f["precio_crc"])
        print("  Mediana por año:")
        for y in sorted(por_anio):
            v = sorted(por_anio[y])
            print(f"    {y}: {median(v):>12,.2f}  (n={len(v):>4})")
    print()

    print(f"  Primeras {min(a.top, len(filas))} ofertas (ordenadas por fecha):")
    print(f"    {'fecha':<11}{'institución':<26}{'oferente':<30}{'CRC/und':>13} "
          f"{'cant':>8}  adj")
    for f in filas[:a.top]:
        print(f"    {f['fecha'] or '?' :<11}{(f['institucion'] or '?')[:25]:<26}"
              f"{(f['oferente'] or '?')[:29]:<30}{f['precio_crc']:>13,.2f} "
              f"{f['cantidad']:>8,.0f}  {f['adjudicado']}")

    if a.csv:
        with io.open(a.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(filas)
        print(f"\nCSV -> {a.csv} ({len(filas):,} ofertas)")
    return 0


def _isnum(s):
    try:
        float(s)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(main())
