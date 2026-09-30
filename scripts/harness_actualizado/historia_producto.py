# -*- coding: utf-8 -*-
"""
historia_producto.py — evolucion de precio de un mismo articulo: quien lo vendio,
a quien, cuando, a que precio en CRC y en USD implicito.

Cada linea adjudicada trae su propio TIPO_CAMBIO_CRC (el del acto), asi que el
precio en USD se reconstruye fila por fila. Sirve para separar "subio el precio"
de "se movio el tipo de cambio".

AVISO METODOLOGICO: un mismo CODIGO_PRODUCTO_CL agrupa productos muy distintos.
Verificado en 4618160590006864: convive CATERPILLAR NITROGEN a USD 131 con
PAT PARATROOPERS a USD 31. Comparar precios por codigo SIN mirar marca/modelo
mezcla peras con manzanas. Por eso este script SIEMPRE trae la marca.

Uso:
  python historia_producto.py --codigo-cl 4618160590006864
  python historia_producto.py --marca MARLUVAS --codigo 461816
  python historia_producto.py --codigo-cl 4618160590006864 --csv historia.csv
"""
import csv, io, os, re, argparse, statistics as st
from collections import defaultdict, Counter

BASE = os.environ.get("SICOP_SALIDA", r"C:\DeepSeek Harness\salida")
ANIOS = range(2020, 2027)
csv.field_size_limit(10 * 1024 * 1024)
RX_MARCA = re.compile(r"\bMarca\s+(.+?)\s+Modelo\s+(.+)$")   # case-sensitive: ver skill §8


def leer(nombre, year):
    for cand in (f"{nombre}_{year}.csv", f"{nombre}.csv"):
        p = os.path.join(BASE, cand)
        if os.path.exists(p):
            with io.open(p, "r", encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    yield r
            return


def num(v):
    try:
        return float(str(v).strip())
    except Exception:
        return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codigo-cl", dest="cl", help="CODIGO_PRODUCTO_CL de 16 digitos")
    ap.add_argument("--marca", help="filtrar por marca (substring)")
    ap.add_argument("--codigo", default="", help="prefijo UNSPSC para acotar, ej 461816")
    ap.add_argument("--csv", help="ruta de salida")
    a = ap.parse_args()
    if not a.cl and not a.marca:
        print("indicar --codigo-cl o --marca"); return 2

    nom, inst, proc_inst = {}, {}, {}
    for y in ANIOS:
        for r in leer("proveedores", y):
            nom.setdefault(r.get("CEDULA_PROVEEDOR", ""), (r.get("NOMBRE_PROVEEDOR") or "").strip())
        for r in leer("instituciones", y):
            inst.setdefault(r.get("CEDULA", ""), (r.get("NOMBRE_INSTITUCION") or "").strip())
        for r in leer("carteles", y):
            proc_inst[r.get("NRO_SICOP", "")] = (r.get("CEDULA_INSTITUCION") or "").strip()

    # marca/modelo por (NRO_SICOP, CODIGO_PRODUCTO) desde las tablas de EJECUCION
    marca = {}
    for y in ANIOS:
        for tabla, col in (("lineas_contratadas", "DESC_PRODUCTO"),
                           ("lineas_recibidas", "desc_producto")):
            for r in leer(tabla, y):
                cod = (r.get("CODIGO_PRODUCTO") or "").strip()
                if not cod:
                    continue
                if a.cl and cod[:16] != a.cl:
                    continue
                if a.codigo and not cod.startswith(a.codigo):
                    continue
                m = RX_MARCA.search((r.get(col) or "").strip())
                if m:
                    marca[(r.get("NRO_SICOP", ""), cod)] = (m.group(1).strip().upper(),
                                                            m.group(2).strip().upper())

    # si se filtra por marca, los codigos objetivo salen del cruce anterior
    cls_objetivo = {a.cl} if a.cl else {c[:16] for (s, c) in marca
                                        if a.marca.upper() in marca[(s, c)][0]}

    filas = []
    for y in ANIOS:
        for r in leer("lineas_adjudicadas", y):
            cod = (r.get("CODIGO_PRODUCTO") or "").strip()
            if cod[:16] not in cls_objetivo:
                continue
            pu, tc = num(r.get("PRECIO_UNITARIO_ADJUDICADO")), num(r.get("TIPO_CAMBIO_CRC"))
            mo = (r.get("TIPO_MONEDA") or "CRC").strip().upper()
            if pu <= 1 or not (300 < tc < 900):
                continue
            crc = pu * tc if mo != "CRC" else pu
            s = r.get("NRO_SICOP", "")
            mk, md = marca.get((s, cod), ("", ""))
            if a.marca and a.marca.upper() not in mk:
                continue
            filas.append({
                "mes": r.get("MES_PUBLICACION", ""), "sicop": s, "codigo": cod,
                "cl": cod[:16],
                "institucion": inst.get(proc_inst.get(s, ""), proc_inst.get(s, "")),
                "cedula_prov": r.get("CEDULA_PROVEEDOR", ""),
                "proveedor": nom.get(r.get("CEDULA_PROVEEDOR", ""), r.get("CEDULA_PROVEEDOR", "")),
                "cantidad": num(r.get("CANTIDAD_ADJUDICADA")),
                "crc": crc, "usd": crc / tc, "tc": tc, "moneda": mo,
                "marca": mk, "modelo": md,
            })

    if not filas:
        print("sin adjudicaciones para ese filtro."); return

    filas.sort(key=lambda f: f["mes"])
    print(f"\n{len(filas)} adjudicaciones · {len(cls_objetivo)} codigo(s) de catalogo\n")
    print(f"{'mes':7} {'institucion':28} {'proveedor':30} {'cant':>6} {'CRC/u':>9} "
          f"{'USD/u':>6} {'TC':>5}  marca / modelo")
    for f in filas:
        print(f"{f['mes']:7} {f['institucion'][:28]:28} {f['proveedor'][:30]:30} "
              f"{f['cantidad']:>6.0f} {f['crc']:>9.0f} {f['usd']:>6.0f} {f['tc']:>5.0f}  "
              f"{(f['marca'] + ' / ' + f['modelo'])[:34]}")

    print("\n--- por proveedor ---")
    pv = defaultdict(list)
    for f in filas:
        pv[f["proveedor"]].append(f["usd"])
    for p, v in sorted(pv.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(v):>3} adj · USD/u mediano {st.median(v):>6.0f} · {p[:52]}")

    print("\n--- por marca (el codigo de catalogo NO garantiza producto equivalente) ---")
    mv = defaultdict(list)
    for f in filas:
        if f["marca"]:
            mv[f["marca"]].append(f["usd"])
    for m, v in sorted(mv.items(), key=lambda kv: -st.median(kv[1])):
        print(f"  USD/u mediano {st.median(v):>6.0f} · n={len(v):>3} · {m[:44]}")
    if mv:
        meds = [st.median(v) for v in mv.values()]
        if len(meds) > 1:
            print(f"\n  [aviso] rango entre marcas: USD {min(meds):.0f} a {max(meds):.0f} "
                  f"({max(meds)/max(1e-9,min(meds)):.1f}x). Comparar precio por codigo sin "
                  f"separar por marca mezcla productos distintos.")

    print("\n--- por anio ---")
    ay = defaultdict(list)
    for f in filas:
        ay[f["mes"][:4]].append(f)
    for y in sorted(ay):
        g = ay[y]
        print(f"  {y}  n={len(g):>3}  CRC/u mediano {st.median([x['crc'] for x in g]):>8.0f} · "
              f"USD/u mediano {st.median([x['usd'] for x in g]):>5.0f} · "
              f"TC mediano {st.median([x['tc'] for x in g]):>5.0f}")

    if a.csv:
        with io.open(a.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
            w.writeheader()
            w.writerows(filas)
        print(f"\nCSV -> {a.csv}")


if __name__ == "__main__":
    main()
