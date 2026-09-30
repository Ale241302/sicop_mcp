# -*- coding: utf-8 -*-
"""
competencia_producto.py — cruce por linea: que PIDEN vs que OFERTAN vs que ADJUDICAN.

Une, por (NRO_SICOP, NRO_LINEA):
  lineas_cartel      -> lo solicitado (DESC_LINEA, CANTIDAD_SOLICITADA, PRECIO_UNITARIO_ESTIMADO)
  lineas_ofertadas   -> lo ofertado   (precio unitario por oferta)
  ofertas            -> cedula del oferente
  proveedores        -> nombre del oferente
  lineas_adjudicadas -> el ganador y su precio

Todos los precios se normalizan a CRC con TIPO_CAMBIO_CRC de la propia fila.

Uso:
  python competencia_producto.py --codigo 461816
  python competencia_producto.py --codigo 461816 --proveedor SONDEL
  python competencia_producto.py --codigo 461816 --proveedor SONDEL --perdidas-baratas
  python competencia_producto.py --codigo 461816 --csv salida.csv
"""
import csv, os, sys, argparse, io
from collections import defaultdict

BASE = os.environ.get("SICOP_SALIDA", r"C:\DeepSeek Harness\salida")
ANIOS = range(2020, 2027)
csv.field_size_limit(10 * 1024 * 1024)


def leer(nombre, year):
    """Acepta nombre_YYYY.csv y nombre.csv. utf-8-sig por el BOM del origen."""
    for cand in (f"{nombre}_{year}.csv", f"{nombre}.csv"):
        p = os.path.join(BASE, cand)
        if os.path.exists(p):
            with io.open(p, "r", encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    yield r
            return
    return


def num(v):
    """Formato de origen: punto decimal estilo US. '1.000' es UNO, no mil.
    Verificado sobre 39.327 precios reales: 0 con coma, 0 con 2+ puntos."""
    try:
        return float(str(v).strip())
    except Exception:
        return 0.0


def a_crc(pu, moneda, tc):
    m = (moneda or "CRC").strip().upper()
    if m == "CRC" or not tc:
        return pu
    return pu * tc


def linea_key(nro, lin):
    """NUMERO_LINEA (cartel) y NRO_LINEA (ofertadas/adjudicadas) pueden venir
    con ceros a la izquierda o como '1.0'. Normalizamos a entero-string."""
    s = str(lin or "").strip()
    if not s:
        return None
    try:
        s = str(int(float(s)))
    except Exception:
        s = s.lstrip("0") or "0"
    return (str(nro or "").strip(), s)


def cargar(codigo, anios):
    nombres, solicitado, ofertas_x_linea, ganador = {}, {}, defaultdict(list), {}
    lineas_del_codigo = set()
    sin_cruce = 0

    for y in anios:
        for r in leer("proveedores", y):
            ced = (r.get("CEDULA_PROVEEDOR") or "").strip()
            if ced:
                nombres.setdefault(ced, (r.get("NOMBRE_PROVEEDOR") or ced).strip())

        # oferta -> cedula
        ofe = {}
        for r in leer("ofertas", y):
            ofe[(r.get("NRO_SICOP", "").strip(), r.get("NRO_OFERTA", "").strip())] = \
                (r.get("CEDULA_PROVEEDOR") or "").strip()

        # adjudicadas: ganador por linea
        for r in leer("lineas_adjudicadas", y):
            if not (r.get("CODIGO_PRODUCTO") or "").startswith(codigo):
                continue
            k = linea_key(r.get("NRO_SICOP"), r.get("NRO_LINEA"))
            if not k:
                continue
            lineas_del_codigo.add(k)
            ced = (r.get("CEDULA_PROVEEDOR") or "").strip()
            ganador[k] = {
                "ced": ced,
                "pu": a_crc(num(r.get("PRECIO_UNITARIO_ADJUDICADO")),
                            r.get("TIPO_MONEDA"), num(r.get("TIPO_CAMBIO_CRC"))),
                "cant": num(r.get("CANTIDAD_ADJUDICADA")),
                "moneda": (r.get("TIPO_MONEDA") or "CRC").strip(),
                "anio": y,
            }

        # ofertadas: todos los oferentes por linea
        for r in leer("lineas_ofertadas", y):
            cod = (r.get("CODIGO_PRODUCTO_CL") or r.get("CODIGO_PRODUCTO") or "")
            if not cod.startswith(codigo):
                continue
            k = linea_key(r.get("NRO_SICOP"), r.get("NRO_LINEA"))
            if not k:
                continue
            lineas_del_codigo.add(k)
            ced = ofe.get((r.get("NRO_SICOP", "").strip(), r.get("NRO_OFERTA", "").strip()))
            if not ced:
                sin_cruce += 1
                continue
            ofertas_x_linea[k].append({
                "ced": ced,
                "pu": a_crc(num(r.get("PRECIO_UNITARIO_OFERTADO")),
                            r.get("TIPO_MONEDA"), num(r.get("TIPO_CAMBIO_CRC"))),
                "cant": num(r.get("CANTIDAD_OFERTADA")),
                "moneda": (r.get("TIPO_MONEDA") or "CRC").strip(),
                "anio": y,
            })

    # cartel: trae lo solicitado Y el código de producto (CODIGO_IDENTIFICACION,
    # 16 dígitos, 99,7% — verificado 2026-08-25; corrige la afirmación anterior
    # de que lineas_cartel no tenía código). Se filtra por las líneas ya
    # identificadas arriba y por el prefijo [:16] del código (16 vs 24 — nunca
    # igualdad). NUMERO_PARTIDA queda registrado: sin la partida la clave
    # (NRO_SICOP, NUMERO_LINEA) del cartel colapsa filas en silencio.
    for y in anios:
        for r in leer("lineas_cartel", y):
            k = linea_key(r.get("NRO_SICOP"), r.get("NUMERO_LINEA"))
            if k in lineas_del_codigo and k not in solicitado:
                cod16 = (r.get("CODIGO_IDENTIFICACION") or "").strip()
                if cod16 and not cod16.startswith(codigo):
                    continue  # el cartel declara un producto fuera de la familia
                solicitado[k] = {
                    "desc": (r.get("DESC_LINEA") or "").strip(),
                    "cant": num(r.get("CANTIDAD_SOLICITADA")),
                    "pu_est": a_crc(num(r.get("PRECIO_UNITARIO_ESTIMADO")),
                                    r.get("TIPO_MONEDA"), num(r.get("TIPO_CAMBIO_CRC"))),
                    "anio": y,
                    "partida": (r.get("NUMERO_PARTIDA") or "").strip(),
                    "cod16": cod16,
                }

    return nombres, solicitado, ofertas_x_linea, ganador, lineas_del_codigo, sin_cruce


def fmt(n):
    return f"{n:,.0f}".replace(",", ".")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codigo", required=True, help="prefijo UNSPSC, ej 461816")
    ap.add_argument("--proveedor", help="filtro por nombre (substring, case-insensitive)")
    ap.add_argument("--anio", type=int, action="append", help="repetible; default 2020-2026")
    ap.add_argument("--perdidas-baratas", action="store_true",
                    help="solo lineas donde el proveedor ofertó MAS BARATO y aun asi perdio")
    ap.add_argument("--csv", help="ruta de salida CSV con el detalle por linea")
    ap.add_argument("--top", type=int, default=15, help="lineas a imprimir en consola")
    a = ap.parse_args()

    anios = a.anio or list(ANIOS)
    nombres, solicitado, ofertadas, ganador, todas, sin_cruce = cargar(a.codigo, anios)

    con_ofertas = [k for k in todas if ofertadas.get(k)]
    cob_of = 100.0 * len(con_ofertas) / len(todas) if todas else 0
    cob_desc = 100.0 * len([k for k in todas if k in solicitado]) / len(todas) if todas else 0

    print(f"\nCODIGO {a.codigo}  ·  anios {min(anios)}-{max(anios)}")
    print(f"  lineas del codigo ............ {len(todas)}")
    print(f"  con oferentes identificados ... {len(con_ofertas)}  ({cob_of:.1f}%)")
    print(f"  con descripcion de cartel ..... {len([k for k in todas if k in solicitado])}  ({cob_desc:.1f}%)")
    print(f"  con adjudicatario ............. {len([k for k in todas if k in ganador])}")
    print(f"  filas ofertadas sin cruce ..... {sin_cruce}")
    if cob_desc < 100:
        print("  [aviso] las lineas sin DESC_LINEA no aparecen en lineas_cartel del "
              "anio cargado; el cartel pudo publicarse en un anio previo.")

    # armar filas
    filas = []
    for k in sorted(todas):
        ofs = sorted(ofertadas.get(k, []), key=lambda o: o["pu"])
        sol = solicitado.get(k, {})
        g = ganador.get(k)
        if a.proveedor:
            pat = a.proveedor.lower()
            if not any(pat in nombres.get(o["ced"], o["ced"]).lower() for o in ofs):
                continue
            if a.perdidas_baratas:
                mio = next((o for o in ofs if pat in nombres.get(o["ced"], o["ced"]).lower()), None)
                if not (g and mio and g["ced"] != mio["ced"]
                        and mio["pu"] > 0 and g["pu"] > 0 and mio["pu"] < g["pu"]):
                    continue
        filas.append((k, sol, ofs, g))

    print(f"\n  lineas que cumplen el filtro .. {len(filas)}\n")

    for k, sol, ofs, g in filas[:a.top]:
        anio = sol.get("anio") or (g or {}).get("anio") or (ofs[0]["anio"] if ofs else "")
        print("=" * 78)
        print(f"Procedimiento {k[0]} · linea {k[1]} · {anio}")
        if sol:
            print(f"  PIDEN: {sol['desc'][:150]}")
            print(f"         cantidad {fmt(sol['cant'])}  ·  estimado CRC {fmt(sol['pu_est'])}/u")
        else:
            print("  PIDEN: [sin DESC_LINEA en lineas_cartel]")
        if not ofs:
            print("  OFERTAN: [sin oferentes cruzables]")
        for o in ofs:
            marca = "  <-- ADJUDICADO" if g and g["ced"] == o["ced"] else ""
            nom = nombres.get(o["ced"], o["ced"])[:44]
            print(f"  CRC {fmt(o['pu']):>12} /u  x{fmt(o['cant']):>8}  {nom}{marca}")
        if g and not any(g["ced"] == o["ced"] for o in ofs):
            print(f"  CRC {fmt(g['pu']):>12} /u  {nombres.get(g['ced'], g['ced'])[:44]}  <-- ADJUDICADO (no cruzado en ofertadas)")

    if a.csv:
        with io.open(a.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["NRO_SICOP", "LINEA", "ANIO", "DESC_LINEA", "CANT_SOLICITADA",
                        "PU_ESTIMADO_CRC", "CEDULA_OFERENTE", "OFERENTE",
                        "PU_OFERTADO_CRC", "CANT_OFERTADA", "MONEDA_ORIGEN",
                        "ADJUDICADO", "CEDULA_GANADOR", "GANADOR", "PU_ADJUDICADO_CRC",
                        "DELTA_PCT_VS_GANADOR", "N_OFERENTES"])
            for k, sol, ofs, g in filas:
                anio = sol.get("anio") or (g or {}).get("anio") or (ofs[0]["anio"] if ofs else "")
                for o in ofs:
                    d = ""
                    if g and g["pu"] > 0:
                        d = round(100.0 * (o["pu"] - g["pu"]) / g["pu"], 1)
                    w.writerow([k[0], k[1], anio, sol.get("desc", ""), sol.get("cant", ""),
                                round(sol.get("pu_est", 0), 2), o["ced"],
                                nombres.get(o["ced"], o["ced"]), round(o["pu"], 2),
                                o["cant"], o["moneda"],
                                "S" if (g and g["ced"] == o["ced"]) else "N",
                                (g or {}).get("ced", ""),
                                nombres.get((g or {}).get("ced", ""), ""),
                                round((g or {}).get("pu", 0), 2), d, len(ofs)])
        print(f"\nCSV -> {a.csv}")


if __name__ == "__main__":
    main()
