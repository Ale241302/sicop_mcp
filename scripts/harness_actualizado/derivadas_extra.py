#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""derivadas_extra.py — derivadas 10 a 15 del harness SICOP (orden 2026-08-24).

Independientes de --pesados; leen los CSV ya en disco (2020-2026).
Reglas transversales: R1 (agrupar por marca+modelo, no solo código),
R2 (regex case-sensitive), R3 (toda salida declara cobertura),
R4 (bloques de integridad rotulados como cola de revisión con ADVERTENCIA).

Uso:
  python3 derivadas_extra.py 10            # desempeno_proveedor (prioridad)
  python3 derivadas_extra.py 11            # precio_por_institucion
  python3 derivadas_extra.py 12            # representante compartido (cola de revisión)
  python3 derivadas_extra.py 13            # precios idénticos (cola de revisión)
  python3 derivadas_extra.py 14            # tallas demandadas
  python3 derivadas_extra.py 15            # barato y prorrogado
  python3 derivadas_extra.py todo
"""
import argparse
import csv
import glob
import io
import os
import re
import sys
from collections import Counter, defaultdict
from statistics import median

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10 * 1024 * 1024)

BASE = os.environ.get("SICOP_SALIDA", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "salida"))

# R2 — case-sensitive (verificado: misma cobertura, sin Marca=NI)
RX_MARCA = re.compile(r"\bMarca\s+(.+?)\s+Modelo\s+(.+)$")
DESCARTE = {
    "LIBRO", "NACIONAL", "SEGÚN OFERTA", "SEGUN OFERTA", "INTECO",
    "SIN REGISTRO", "NINGUNA", "VARIOS", "GENERICO", "TOTAL", "NO APLICA",
    "NA", "SN", "N/A", "-", "—", ".", "*", "SEGUN MUESTRA", "SEGÚN MUESTRA",
    "A DEFINIR", "POR DEFINIR", "NO INDICA", "NO DECLARADO",
}

ADVERTENCIA_REP = ("Compartir representante legal no prueba coordinación. Hay "
                   "explicaciones legítimas: grupo económico declarado, gestor "
                   "profesional que representa a muchas empresas sin relación entre "
                   "sí. Requiere verificación caso por caso.")
ADVERTENCIA_PRECIOS = ("Coincidir en precio una vez en un bien de catálogo con precio "
                       "de lista es esperable. La repetición del mismo par de oferentes "
                       "en precios idénticos a través de líneas es lo que hay que "
                       "revisar. No prueba coordinación; el motivo real vive en el acta "
                       "de estudio técnico del expediente, que no está en los CSV.")
README_INTEGRIDAD = ("El motivo real de cualquier hallazgo vive en el acta de estudio "
                     "técnico del expediente, que no está en los CSV. Estas tablas "
                     "reducen el universo a una cola de revisión; no prueban conducta.")


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


def leer(nombre):
    """Todos los años: nombre_20*.csv (y nombre.csv sin sufijo para derivadas)."""
    for p in sorted(glob.glob(os.path.join(BASE, f"{nombre}_20*.csv"))):
        with io.open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                yield r
    p0 = os.path.join(BASE, f"{nombre}.csv")
    if os.path.exists(p0) and not glob.glob(os.path.join(BASE, f"{nombre}_20*.csv")):
        with io.open(p0, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                yield r


def esc(r, k):
    return (r.get(k) or "").strip()


def _linea_norm(s):
    try:
        return str(int(float(s)))
    except Exception:
        return esc({"k": s}, "k")


def cruzar_competencia():
    """Todas las líneas ofertadas (2020-2026) con cédula, precio CRC y adjudicado.
    competencia_por_linea.csv solo cubre el año actual; acá se arma el cruce
    completo: lineas_ofertadas × ofertas (cédula) × adjudicaciones (ganador)."""
    ced_oferta = {}
    for r in leer("ofertas"):
        ced_oferta[(esc(r, "NRO_SICOP"), esc(r, "NRO_OFERTA"))] = esc(r, "CEDULA_PROVEEDOR")
    ganador = set()
    for r in leer("adjudicaciones"):
        ns, ln = esc(r, "NRO_SICOP"), _linea_norm(esc(r, "LINEA"))
        if ns and ln:
            ganador.add((ns, ln, esc(r, "CEDULA_PROVEEDOR")))
    for r in leer("lineas_ofertadas"):
        ns, nof = esc(r, "NRO_SICOP"), esc(r, "NRO_OFERTA")
        ced = ced_oferta.get((ns, nof), "")
        ln = _linea_norm(esc(r, "NRO_LINEA"))
        yield {
            "NRO_SICOP": ns, "NRO_OFERTA": nof, "NRO_LINEA": ln,
            "CEDULA_PROVEEDOR": ced,
            "PRECIO_UNITARIO_CRC": a_crc(num(r.get("PRECIO_UNITARIO_OFERTADO")),
                                         r.get("TIPO_MONEDA"),
                                         num(r.get("TIPO_CAMBIO_CRC"))),
            "ES_ADJUDICATARIO": "S" if (ns, ln, ced) in ganador else "N",
            "MES_PUBLICACION": esc(r, "MES_PUBLICACION"),
            "CODIGO_PRODUCTO_CL": esc(r, "CODIGO_PRODUCTO_CL")
                                  or esc(r, "CODIGO_PRODUCTO")[:16],
        }


def escribe(path, cols, filas):
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(filas)
    return path


# ─────────────────────────────────────────────────────────────── D10
def d10():
    """desempeno_proveedor — cumplimiento de recepción por proveedor (prioridad)."""
    # lineas_contratadas: (NRO_CONTRATO, SECUENCIA) -> cedula, cantidad_contratada
    ctr = {}
    ctr_ced = defaultdict(set)
    for r in leer("lineas_contratadas"):
        nc, sec = esc(r, "NRO_CONTRATO"), esc(r, "SECUENCIA")
        ced = esc(r, "CEDULA_PROVEEDOR")
        if nc:
            ctr_ced[nc].add(ced)
            if sec:
                ctr[(nc, sec)] = (ced, num(r.get("CANTIDAD_CONTRATADA")))
    # contratos: NRO_CONTRATO -> cédulas (+ institución); NRO_SICOP -> cédulas
    contr_ced = defaultdict(set)
    contr_inst = {}
    sicop_ced = defaultdict(set)
    for r in leer("contratos"):
        nc, ns = esc(r, "NRO_CONTRATO"), esc(r, "NRO_SICOP")
        ced = esc(r, "CEDULA_PROVEEDOR")
        if nc:
            contr_ced[nc].add(ced)
            contr_inst.setdefault(nc, esc(r, "CEDULA_INSTITUCION"))
        if ns and ced:
            sicop_ced[ns].add(ced)
    # adjudicaciones: NRO_SICOP -> ganadores
    sicop_adj = defaultdict(set)
    for r in leer("adjudicaciones"):
        ns, ced = esc(r, "NRO_SICOP"), esc(r, "CEDULA_PROVEEDOR")
        if ns and ced:
            sicop_adj[ns].add(ced)

    def unir(nc, sec, ns):
        """Cascada: contrato único -> contratadas -> adjudicaciones del procedimiento.
        Devuelve (cedula, cantidad_contratada, paso) o (None, 0, '')."""
        if nc in contr_ced and len(contr_ced[nc]) == 1:
            return next(iter(contr_ced[nc])), 0.0, "contratos"
        if (nc, sec) in ctr:
            return ctr[(nc, sec)][0], ctr[(nc, sec)][1], "contratadas"
        if nc in ctr_ced and len(ctr_ced[nc]) == 1:
            return next(iter(ctr_ced[nc])), 0.0, "contratadas"
        if ns in sicop_adj and len(sicop_adj[ns]) == 1:
            return next(iter(sicop_adj[ns])), 0.0, "adjudicaciones"
        if ns in sicop_ced and len(sicop_ced[ns]) == 1:
            return next(iter(sicop_ced[ns])), 0.0, "contratos_sicop"
        return None, 0.0, ""

    prov = defaultdict(lambda: {"n": 0, "cumple": 0, "nocumple": 0,
                                "parcial": 0, "dias": [], "atraso": 0,
                                "ratios": [], "insts": set(), "anios": set(),
                                "fams": set()})
    unidas = total = 0
    pasos = Counter()
    for r in leer("lineas_recibidas"):
        est = esc(r, "ESTADO_RECEP_DEFINITIVA")
        if not est:
            continue
        total += 1
        nc, sec, ns = esc(r, "NRO_CONTRATO"), esc(r, "SECUENCIA"), esc(r, "NRO_SICOP")
        ced, cant_ctr, paso = unir(nc, sec, ns)
        if not ced:
            continue  # sin proveedor identificable: cobertura se declara abajo
        unidas += 1
        pasos[paso] += 1
        d = prov[ced]
        d["n"] += 1
        if est == "Cumple":
            d["cumple"] += 1
        elif "No Cumple" in est and "se paga" in est.lower():
            d["parcial"] += 1
        elif "No Cumple" in est:
            d["nocumple"] += 1
        dias = num(r.get("dias_adelanto_atraso"))
        if dias:
            d["dias"].append(dias)
            if dias > 0:
                d["atraso"] += 1
        cant_real = num(r.get("CANTIDAD_REAL_RECIBIDA"))
        if cant_real > 0 and cant_ctr > 0:
            d["ratios"].append(cant_real / cant_ctr)
        d["insts"].add(contr_inst.get(nc, ""))
        d["anios"].add((esc(r, "MES_PUBLICACION"))[:4])
        cod = esc(r, "CODIGO_PRODUCTO")
        if len(cod) >= 6:
            d["fams"].add(cod[:6])

    nombre = {esc(r, "CEDULA_PROVEEDOR"): (esc(r, "NOMBRE_PROVEEDOR"), esc(r, "TAMAÑO_PROVEEDOR"))
              for r in leer("proveedores") if esc(r, "CEDULA_PROVEEDOR")}

    filas = []
    for ced, d in prov.items():
        nom, tam = nombre.get(ced, (ced, ""))
        dias = sorted(d["dias"])
        filas.append({
            "CEDULA_PROVEEDOR": ced, "NOMBRE_PROVEEDOR": nom,
            "TAMANO_PROVEEDOR": tam, "LINEAS_RECIBIDAS": d["n"],
            "N_CUMPLE": d["cumple"], "N_NO_CUMPLE": d["nocumple"],
            "N_NO_CUMPLE_PAGO_PARCIAL": d["parcial"],
            "TASA_CUMPLIMIENTO": round(100.0 * d["cumple"] / d["n"], 1) if d["n"] else "",
            "DIAS_MEDIANO": round(median(dias), 1) if dias else "",
            "DIAS_P90": round(dias[int(len(dias) * 0.9)], 1) if dias else "",
            "PCT_CON_ATRASO": round(100.0 * d["atraso"] / d["n"], 1) if d["n"] else "",
            "RATIO_ENTREGA": round(median(d["ratios"]), 3) if d["ratios"] else "",
            "INSTITUCIONES": len([i for i in d["insts"] if i]),
            "ANIOS_ACTIVO": ",".join(sorted(d["anios"])),
            "FAMILIAS_UNSPSC": ",".join(sorted(d["fams"])),
            "MUESTRA_SUFICIENTE": "S" if d["n"] >= 10 else "N",
        })
    filas.sort(key=lambda x: -num(x["LINEAS_RECIBIDAS"]))
    p1 = escribe(os.path.join(BASE, "desempeno_proveedor.csv"),
                 list(filas[0].keys()) if filas else [], filas)

    # por proveedor × familia (6 dígitos)
    fam_rows = defaultdict(lambda: {"n": 0, "cumple": 0, "dias": []})
    for r in leer("lineas_recibidas"):
        est = esc(r, "ESTADO_RECEP_DEFINITIVA")
        cod = esc(r, "CODIGO_PRODUCTO")
        nc, sec, ns = esc(r, "NRO_CONTRATO"), esc(r, "SECUENCIA"), esc(r, "NRO_SICOP")
        if not est or len(cod) < 6:
            continue
        ced, _, _ = unir(nc, sec, ns)
        if not ced:
            continue
        d = fam_rows[(ced, cod[:6])]
        d["n"] += 1
        if est == "Cumple":
            d["cumple"] += 1
        dias = num(r.get("dias_adelanto_atraso"))
        if dias:
            d["dias"].append(dias)
    ff = []
    for (ced, fam), d in fam_rows.items():
        nom, tam = nombre.get(ced, (ced, ""))
        ff.append({
            "CEDULA_PROVEEDOR": ced, "NOMBRE_PROVEEDOR": nom,
            "FAMILIA_UNSPSC": fam, "LINEAS_RECIBIDAS": d["n"],
            "N_CUMPLE": d["cumple"],
            "TASA_CUMPLIMIENTO": round(100.0 * d["cumple"] / d["n"], 1) if d["n"] else "",
            "DIAS_MEDIANO": round(median(d["dias"]), 1) if d["dias"] else "",
            "MUESTRA_SUFICIENTE": "S" if d["n"] >= 10 else "N",
        })
    ff.sort(key=lambda x: -num(x["LINEAS_RECIBIDAS"]))
    p2 = escribe(os.path.join(BASE, "desempeno_por_familia.csv"),
                 list(ff[0].keys()) if ff else [], ff)

    con_muestra = sum(1 for x in filas if x["MUESTRA_SUFICIENTE"] == "S")
    print(f"D10 desempeno_proveedor · {len(filas):,} proveedores · "
          f"{con_muestra:,} con muestra ≥10 líneas")
    print(f"  cobertura: {unidas}/{total} filas de recepción con proveedor "
          f"identificado ({100.0*unidas/total:.1f}%) · pasos: {dict(pasos)}")
    print(f"  -> {p1}\n  -> {p2}")
    return {"proveedores": len(filas), "muestra_suficiente": con_muestra,
            "lineas_unidas": unidas, "lineas_totales": total}


# ─────────────────────────────────────────────────────────────── D11
def d11():
    """precio_por_institucion — quién paga de más por lo mismo (marca+modelo+año)."""
    catalogo = {esc(r, "CODIGO_PRODUCTO_CL"): (esc(r, "MARCA"), esc(r, "MODELO"))
                for r in leer("catalogo_productos") if esc(r, "MARCA_PLAUSIBLE") == "S"}
    cartel = {}
    for r in leer("carteles"):
        ns = esc(r, "NRO_SICOP")
        if ns:
            cartel.setdefault(ns, (esc(r, "CEDULA_INSTITUCION"),
                                   esc(r, "MODALIDAD_PROCEDIMIENTO")))
    inst_nom = {esc(r, "CEDULA"): esc(r, "NOMBRE_INSTITUCION")
                for r in leer("instituciones") if esc(r, "CEDULA")}
    # tipo de cambio por (SICOP, OFERTA, LINEA)
    tc = {}
    for r in leer("lineas_ofertadas"):
        tc[(esc(r, "NRO_SICOP"), esc(r, "NRO_OFERTA"),
            str(int(float(esc(r, "NRO_LINEA")))) if esc(r, "NRO_LINEA") else "")] = \
            num(r.get("TIPO_CAMBIO_CRC"))

    # firma de SKU (D14): por CL y marca → conjunto de firmas de atributos
    firma_por = defaultdict(lambda: defaultdict(set))
    for r in leer("producto_firma"):
        cl = esc(r, "CODIGO_PRODUCTO_CL")
        firma_por[cl][(esc(r, "MARCA"), esc(r, "MODELO"))].add(esc(r, "ATRIBUTOS_CLAVE"))

    grupos = defaultdict(list)
    sin_firma = ambiguo = 0
    for r in leer("lineas_adjudicadas"):
        cl = esc(r, "CODIGO_PRODUCTO")[:16]
        if cl not in catalogo:
            continue
        ma, mo = catalogo[cl]
        if not ma:
            sin_firma += 1
            continue  # R1: sin marca no se compara
        firmas = firma_por.get(cl, {}).get((ma, mo), set())
        if not firmas:
            sin_firma += 1
            continue
        if len(firmas) > 1:
            ambiguo += 1
            continue  # R5: firma no unívoca — no comparable
        atrs = next(iter(firmas))
        anio = esc(r, "MES_PUBLICACION")[:4]
        nc = esc(r, "NRO_LINEA")
        try:
            nc = str(int(float(nc)))
        except Exception:
            pass
        tc_row = tc.get((esc(r, "NRO_SICOP"), esc(r, "NRO_OFERTA"), nc), 0.0) or 0.0
        pu = a_crc(num(r.get("PRECIO_UNITARIO_ADJUDICADO")),
                   r.get("TIPO_MONEDA"), tc_row)
        inst = cartel.get(esc(r, "NRO_SICOP"), ("", ""))[0]
        modalidad = cartel.get(esc(r, "NRO_SICOP"), ("", ""))[1]
        if pu <= 0:
            continue
        grupos[(ma, mo, atrs, cl, anio)].append({
            "pu": pu, "usd": pu / tc_row if tc_row else None,
            "inst": inst, "modalidad": modalidad})

    filas = []
    por_modalidad = Counter()
    for (ma, mo, atrs, cl, anio), rows in grupos.items():
        if len(rows) < 3:
            continue
        insts = {x["inst"] for x in rows if x["inst"]}
        if len(insts) < 2:
            continue
        norm = [x for x in rows if "según demanda" not in x["modalidad"].lower()]
        base = norm or rows
        pcs = sorted(x["pu"] for x in base)
        usds = sorted(x["usd"] for x in base if x["usd"])
        por_modalidad["según demanda" if not norm else "normal"] += len(rows)
        por_inst = {}
        for x in rows:
            d = por_inst.setdefault(x["inst"], [])
            d.append(x["pu"])
        mas_cara = max(por_inst.items(), key=lambda kv: median(kv[1]))
        mas_b = min(por_inst.items(), key=lambda kv: median(kv[1]))
        filas.append({
            "MARCA": ma, "MODELO": mo, "ATRIBUTOS_CLAVE": atrs,
            "CODIGO_PRODUCTO_CL": cl,
            "FAMILIA_UNSPSC": cl[:8], "ANIO": anio,
            "N_ADJUDICACIONES": len(rows),
            "INSTITUCIONES_DISTINTAS": len(insts),
            "PU_CRC_MEDIANO": round(median(pcs), 2),
            "PU_USD_MEDIANO": round(median(usds), 2) if usds else "",
            "PU_CRC_MIN": round(pcs[0], 2), "PU_CRC_MAX": round(pcs[-1], 2),
            "RATIO_MAX_MIN": round(pcs[-1] / pcs[0], 1) if pcs[0] else "",
            "INSTITUCION_MAS_CARA": inst_nom.get(mas_cara[0], mas_cara[0]),
            "PU_MAS_CARA": round(median(mas_cara[1]), 2),
            "INSTITUCION_MAS_BARATA": inst_nom.get(mas_b[0], mas_b[0]),
            "PU_MAS_BARATA": round(median(mas_b[1]), 2),
        })
    filas.sort(key=lambda x: -num(x["RATIO_MAX_MIN"]))
    cols = ["MARCA", "MODELO", "ATRIBUTOS_CLAVE", "CODIGO_PRODUCTO_CL",
            "FAMILIA_UNSPSC", "ANIO",
            "N_ADJUDICACIONES", "INSTITUCIONES_DISTINTAS", "PU_CRC_MEDIANO",
            "PU_USD_MEDIANO", "PU_CRC_MIN", "PU_CRC_MAX", "RATIO_MAX_MIN",
            "INSTITUCION_MAS_CARA", "PU_MAS_CARA", "INSTITUCION_MAS_BARATA",
            "PU_MAS_BARATA"]
    p = escribe(os.path.join(BASE, "precio_por_institucion.csv"), cols, filas)
    print(f"D11 precio_por_institucion · {len(filas):,} grupos "
          f"marca+modelo+firma+año (≥3 adj., ≥2 inst.) · modalidades: "
          f"{dict(por_modalidad)}")
    print(f"  cobertura: {sin_firma:,} adjudicaciones sin marca (R1, no comparadas) · "
          f"{ambiguo:,} con firma no unívoca (R5, excluidas)")
    print(f"  -> {p}")
    return {"grupos": len(filas), "sin_firma": sin_firma, "ambiguos": ambiguo}


# ─────────────────────────────────────────────────────────────── D14
# atributos_producto + producto_firma (rev. 2 de la orden, R5)
# La talla numérica es el 0,5% del universo; el fenómeno general son los
# atributos variantes (dimensión 41,5%, color 10,1%, peso 9,8%…). Son parte de
# la identidad del producto: dos líneas con el mismo código y marca pueden ser
# productos distintos si difieren en dimensión, voltaje, capacidad o presentación.

_UNIDAD_FACTOR = {
    "dimension": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "pulg": 25.4,
                  "pulgadas": 25.4, "metro": 1000.0, "metros": 1000.0},
    "peso": {"g": 1.0, "kg": 1000.0, "mg": 0.001, "lb": 453.6, "oz": 28.35,
             "ton": 1e6, "tonelada": 1e6, "toneladas": 1e6},
    "volumen": {"ml": 1.0, "cc": 1.0, "l": 1000.0, "lt": 1000.0, "litro": 1000.0,
                "litros": 1000.0, "gal": 3785.4, "galon": 3785.4, "galones": 3785.4},
    "voltaje": {"v": 1.0, "kv": 1000.0, "volt": 1.0, "voltios": 1.0},
    "potencia": {"w": 1.0, "kw": 1000.0, "hp": 745.7, "cv": 735.5, "watts": 1.0},
    "capacidad_ti": {"gb": 1.0, "tb": 1024.0, "mb": 1.0 / 1024.0},
}
_UNIDAD_BASE = {"dimension": "mm", "peso": "g", "volumen": "ml", "voltaje": "V",
                "potencia": "W", "capacidad_ti": "GB"}
_COLORES = {"ROJO", "AZUL", "NEGRO", "BLANCO", "GRIS", "VERDE", "AMARILLO", "CAFE",
            "MARRON", "NARANJA", "ROSADO", "MORADO", "CELESTE", "BEIGE", "CREMA",
            "PLATA", "DORADO", "TURQUESA", "TRANSPARENTE", "ROJO/BLANCO", "AZUL/ROJO"}


def _attr_num(t):
    try:
        return float(t.replace(",", "."))
    except Exception:
        return None


def _atributos(desc):
    """Devuelve (set de (tipo, valor_normalizado)) y (set de (tipo, valor, 'rango'))."""
    d = desc or ""
    up = d.upper()
    salida = set()
    rangos = set()

    def punto(tipo, valor, unidad, es_rango=False):
        if es_rango:
            rangos.add((tipo, valor, unidad))
            return
        if tipo in _UNIDAD_FACTOR:
            f = _UNIDAD_FACTOR[tipo].get(unidad.lower(), 1.0)
            salida.add((tipo, f"{round(_attr_num(valor) * f, 2)}{_UNIDAD_BASE[tipo]}"))
        else:
            salida.add((tipo, f"{valor}{unidad}"))

    # numéricos con unidad + rango (X a Y)
    for tipo, base_alt, rango_ok in (
            ("dimension", r"mm|cm|m|pulgadas|pulg|metro|metros", True),
            ("peso", r"kg|g|mg|lb|oz|ton|tonelada|toneladas", True),
            ("volumen", r"ml|cc|l|lt|litro|litros|gal|galon|galones", True),
            ("voltaje", r"v|kv|volt|voltios", False),
            ("potencia", r"w|kw|hp|cv|watts", False),
            ("capacidad_ti", r"gb|tb|mb", True)):
        pat = re.compile(r"([\d]+(?:[.,]\d+)?)\s*(" + base_alt + r")\b", re.I)
        vals = pat.findall(d)
        for v, u in vals:
            n = _attr_num(v)
            if n is None or n <= 0:
                continue
            if tipo == "voltaje":
                continue  # voltaje se extrae con V/kV solo (sin rango)
            punto(tipo, v, u)
        # rango numérico con la misma unidad
        if rango_ok:
            rp = re.compile(
                r"([\d]+(?:[.,]\d+)?)\s*(?:a|al|hasta|–|-)\s*([\d]+(?:[.,]\d+)?)\s*("
                + base_alt + r")\b", re.I)
            for v1, v2, u in rp.findall(d):
                n = _attr_num(v1)
                if n is not None:
                    punto(tipo, v1, u, es_rango=True)
    # voltaje con rango válido > 0 (V/kV)
    for v, u in re.findall(r"([\d]+(?:[.,]\d+)?)\s*(kv|v|voltios)\b", d, re.I):
        n = _attr_num(v)
        if n is not None and n > 0:
            punto("voltaje", v, u)
    # porcentaje 0-100
    for v in re.findall(r"([\d]+(?:[.,]\d+)?)\s*%", d):
        n = _attr_num(v)
        if n is not None and 0 <= n <= 100:
            salida.add(("porcentaje", f"{v}%"))
    # talla numérica de calzado 33-48 (validación obligatoria)
    for rx in (r"\bTALLAS?\s*:?\s*(\d{2})\b", r"#\s*(\d{2})\b",
               r"\bN[o°º]\.?\s*(\d{2})\b", r"\bNUMERO\s*:?\s*(\d{2})\b", r"-(\d{2})$"):
        for v in re.findall(rx, d):
            n = _attr_num(v)
            if n is not None and 33 <= n <= 48:
                salida.add(("talla_num", f"{int(n)}"))
    # talla letra
    for v in re.findall(r"\b(XS|S|M|L|XL|XXL|XXXL)\b", up):
        salida.add(("talla_letra", v))
    # color (diccionario)
    for c in _COLORES:
        if re.search(rf"\b{c}\b", up):
            salida.add(("color", c))
    # clase / grado / tipo / nivel (sin interpretar, por familia)
    for v in re.findall(r"\b(?:clase|grado|tipo|nivel)\s*[:#]?\s*([A-Za-z0-9]+)", d, re.I):
        salida.add(("clase", v.upper()))
    # presentación (caja/paquete/par/kit… de N)
    for v, n in re.findall(
            r"\b(caja|paquete|par|kit|docena|bolsa|frasco|envase|bote|rollo|lote|unidad)"
            r"\s*(?:de|con|por|x)?\s*(\d+)?\b", d, re.I):
        salida.add(("presentacion", f"{v.upper()}{'=' + n if n else ''}"))
    # norma
    for v in re.findall(
            r"\b(EN\s*\d{4,6}|ISO\s*\d{4,5}|ASTM\s*[A-Z0-9-]{2,12}|ANSI\s*[A-Z0-9-]{2,12}"
            r"|INTE\s*\d{4,6}|NFPA\s*\d{2,4})\b", d, re.I):
        salida.add(("norma", re.sub(r"\s+", " ", v).upper()))
    return salida, rangos


def d14():
    """atributos_producto + producto_firma — atributos variantes de producto (R5)."""
    catalogo = {esc(r, "CODIGO_PRODUCTO_CL"): (esc(r, "MARCA"), esc(r, "MODELO"))
                for r in leer("catalogo_productos") if esc(r, "MARCA_PLAUSIBLE") == "S"}
    # agregación por (CL, tipo, valor) y firma por (CL, marca, modelo, conjunto)
    agg = defaultdict(lambda: {"n": 0, "cant": 0.0, "insts": set(), "anios": set(),
                               "marcas": Counter()})
    firma = defaultdict(lambda: {"n": 0, "atrs": set()})
    cartel_inst = {}
    for r in leer("carteles"):
        ns = esc(r, "NRO_SICOP")
        if ns:
            cartel_inst.setdefault(ns, esc(r, "CEDULA_INSTITUCION"))
    inst_nom = {esc(r, "CEDULA"): esc(r, "NOMBRE_INSTITUCION")
                for r in leer("instituciones") if esc(r, "CEDULA")}

    for nombre, campo, cant, fam_ok, fuente in (
            ("adjudicaciones", "DESCR_BIEN_SERVICIO", "CANTIDAD", "PROD_ID",
             "adjudicacion"),
            ("lineas_contratadas", "DESC_PRODUCTO", "CANTIDAD_CONTRATADA",
             "CODIGO_PRODUCTO", "ejecucion"),
            ("lineas_recibidas", "desc_producto", "CANTIDAD_REAL_RECIBIDA",
             "CODIGO_PRODUCTO", "ejecucion")):
        for r in leer(nombre):
            cod = esc(r, fam_ok)
            if len(cod) < 16:
                continue
            cl = cod[:16]
            desc = esc(r, campo)
            if not desc:
                continue
            ma, mo = catalogo.get(cl, ("", ""))
            atrs, rangos = _atributos(desc)
            ns = esc(r, "NRO_SICOP")
            anio = esc(r, "MES_PUBLICACION")[:4]
            for tipo, valor in atrs:
                k = (cl, tipo, valor)
                e = agg[k]
                e["n"] += 1
                e["cant"] += num(r.get(cant))
                if ns in cartel_inst:
                    e["insts"].add(cartel_inst[ns])
                e["anios"].add(anio)
                if ma:
                    e["marcas"][ma] += 1
            for tipo, valor, unidad in rangos:
                agg[(cl, tipo, f"{valor}{unidad}|RANGO")]["n"] += 1
            # firma de SKU: (CL, marca, modelo, frozenset de atributos sin rango)
            if atrs:
                fk = (cl, ma, mo, frozenset(atrs))
                firma[fk]["n"] += 1
                firma[fk]["atrs"] = atrs

    fa = []
    for (cl, tipo, valor), e in agg.items():
        fa.append({
            "CODIGO_PRODUCTO_CL": cl, "FAMILIA_UNSPSC": cl[:8],
            "TIPO_ATRIBUTO": tipo, "VALOR": valor,
            "UNIDAD": _UNIDAD_BASE.get(tipo, ""),
            "VALOR_NORMALIZADO": valor,
            "ES_RANGO": "S" if valor.endswith("|RANGO") else "N",
            "CANTIDAD_ADJUDICADA": round(e["cant"], 2),
            "N_LINEAS": e["n"],
            "INSTITUCIONES": len(e["insts"]),
            "ANIOS": ",".join(sorted(e["anios"])),
            "MARCA": e["marcas"].most_common(1)[0][0] if e["marcas"] else "",
            "FUENTE": fuente if False else "adjudicacion+ejecucion",
        })
    fa.sort(key=lambda x: -x["N_LINEAS"])
    cols_a = ["CODIGO_PRODUCTO_CL", "FAMILIA_UNSPSC", "TIPO_ATRIBUTO", "VALOR",
              "UNIDAD", "VALOR_NORMALIZADO", "ES_RANGO", "CANTIDAD_ADJUDICADA",
              "N_LINEAS", "INSTITUCIONES", "ANIOS", "MARCA", "FUENTE"]
    p1 = escribe(os.path.join(BASE, "atributos_producto.csv"), cols_a, fa)

    ff = []
    for (cl, ma, mo, atrs), e in firma.items():
        clave = "|".join(sorted(f"{t}={v}" for t, v in atrs))
        ff.append({
            "CODIGO_PRODUCTO_CL": cl, "MARCA": ma, "MODELO": mo,
            "ATRIBUTOS_CLAVE": clave, "N_LINEAS": e["n"],
        })
    ff.sort(key=lambda x: (-x["N_LINEAS"], x["CODIGO_PRODUCTO_CL"]))
    cols_f = ["CODIGO_PRODUCTO_CL", "MARCA", "MODELO", "ATRIBUTOS_CLAVE", "N_LINEAS"]
    p2 = escribe(os.path.join(BASE, "producto_firma.csv"), cols_f, ff)

    por_tipo = Counter()
    for (cl, tipo, valor), e in agg.items():
        if not valor.endswith("|RANGO"):
            por_tipo[tipo] += e["n"]
    print(f"D14 atributos_producto · {len(fa):,} producto×atributo×valor · "
          f"{len(ff):,} firmas de SKU · distribución: {dict(por_tipo.most_common())}")
    print(f"  cobertura por familia en atributos_producto (columna FAMILIA_UNSPSC); "
          f"las líneas con atributo explícito tienden a ser compras específicas — "
          f"referencia de planificación, no censo")
    print(f"  -> {p1}\n  -> {p2}")
    return {"atributos": len(fa), "firmas": len(ff), "por_tipo": dict(por_tipo)}


# ─────────────────────────────────────────────────────────────── D15
def d15():
    """barato_y_prorrogado — ¿el más barato concentra prórrogas y reajustes?"""
    # contratos por procedimiento
    contr = defaultdict(list)
    for r in leer("contratos"):
        contr[esc(r, "NRO_SICOP")].append((esc(r, "TIPO_CONTRATO"),
                                           esc(r, "TIPO_MODIFICACION")))
    reaj = defaultdict(list)
    for r in leer("reajustes"):
        reaj[esc(r, "NRO_SICOP")].append(num(r.get("PORC_INCR_ULT_RJ")))

    # por procedimiento: línea adjudicada con más oferentes -> posición del ganador
    por_linea = defaultdict(list)
    for r in cruzar_competencia():
        por_linea[(esc(r, "NRO_SICOP"), esc(r, "NRO_LINEA"))].append(r)

    proc = {}
    for (ns, nl), rows in por_linea.items():
        precios = sorted((r for r in rows if num(r.get("PRECIO_UNITARIO_CRC")) > 0),
                         key=lambda r: num(r.get("PRECIO_UNITARIO_CRC")))
        if not precios:
            continue
        gan = [r for r in precios if esc(r, "ES_ADJUDICATARIO") == "S"]
        if not gan:
            continue
        r_gan = gan[0]
        pos = next(i + 1 for i, r in enumerate(precios)
                   if num(r.get("PRECIO_UNITARIO_CRC")) == num(r_gan.get("PRECIO_UNITARIO_CRC")))
        med = median(num(r.get("PRECIO_UNITARIO_CRC")) for r in precios)
        d = proc.setdefault(ns, {"n_lin": 0, "ganador": "", "pos": 999, "n_ofe": 0,
                                 "delta": 0.0, "anio": ""})
        d["n_lin"] += 1
        d["ganador"] = esc(r_gan, "NOMBRE_PROVEEDOR")
        d["anio"] = esc(r_gan, "MES_PUBLICACION")[:4]
        # usar la línea adjudicada con MÁS oferentes como representativa
        if len(precios) > d["n_ofe"]:
            d["pos"] = pos
            d["n_ofe"] = len(precios)
            d["delta"] = round(100.0 * (num(r_gan.get("PRECIO_UNITARIO_CRC")) - med) / med, 1) \
                if med else ""

    cartel_inst = {}
    for r in leer("carteles"):
        ns = esc(r, "NRO_SICOP")
        if ns:
            cartel_inst.setdefault(ns, esc(r, "CEDULA_INSTITUCION"))
    inst_nom = {esc(r, "CEDULA"): esc(r, "NOMBRE_INSTITUCION")
                for r in leer("instituciones") if esc(r, "CEDULA")}

    filas = []
    for ns, d in proc.items():
        cs = contr.get(ns, [])
        tipos = [c for c, _ in cs]
        mods = [m for _, m in cs if m]
        rs = [x for x in reaj.get(ns, []) if x]
        filas.append({
            "NRO_SICOP": ns, "ANIO": d["anio"],
            "INSTITUCION": inst_nom.get(cartel_inst.get(ns, ""), cartel_inst.get(ns, "")),
            "ADJUDICATARIO": d["ganador"], "POSICION_PRECIO": d["pos"],
            "N_OFERENTES": d["n_ofe"], "DELTA_VS_MEDIANA_PCT": d["delta"],
            "TIENE_CONTRATO": "S" if cs else "N",
            "TIPO_CONTRATO": Counter(tipos).most_common(1)[0][0] if tipos else "",
            "N_MODIFICACIONES": len(mods),
            "TIPO_MODIFICACION": Counter(mods).most_common(1)[0][0] if mods else "",
            "TIENE_REAJUSTE": "S" if rs else "N",
            "PCT_REAJUSTE": round(median(rs), 1) if rs else "",
        })
    filas.sort(key=lambda x: (x["ANIO"], x["NRO_SICOP"]))
    cols = ["NRO_SICOP", "ANIO", "INSTITUCION", "ADJUDICATARIO", "POSICION_PRECIO",
            "N_OFERENTES", "DELTA_VS_MEDIANA_PCT", "TIENE_CONTRATO", "TIPO_CONTRATO",
            "N_MODIFICACIONES", "TIPO_MODIFICACION", "TIENE_REAJUSTE", "PCT_REAJUSTE"]
    p1 = escribe(os.path.join(BASE, "barato_y_prorrogado.csv"), cols, filas)

    # resumen por posición de precio
    resumen = defaultdict(lambda: {"n": 0, "mod": 0, "reaj": 0})
    for f in filas:
        r = resumen[f["POSICION_PRECIO"]]
        r["n"] += 1
        if f["N_MODIFICACIONES"]:
            r["mod"] += 1
        if f["TIENE_REAJUSTE"] == "S":
            r["reaj"] += 1
    cols_r = ["POSICION_PRECIO", "PROCEDIMIENTOS", "TASA_MODIFICACION_PCT",
              "TASA_REAJUSTE_PCT"]
    fr = [{"POSICION_PRECIO": k, "PROCEDIMIENTOS": v["n"],
           "TASA_MODIFICACION_PCT": round(100.0 * v["mod"] / v["n"], 1),
           "TASA_REAJUSTE_PCT": round(100.0 * v["reaj"] / v["n"], 1)}
          for k, v in sorted(resumen.items())]
    p2 = escribe(os.path.join(BASE, "barato_y_prorrogado_resumen.csv"), cols_r, fr)
    print(f"D15 barato_y_prorrogado · {len(filas):,} procedimientos adjudicados · "
          f"{len(resumen)} posiciones")
    for k, v in sorted(resumen.items()):
        print(f"  pos {k}: n={v['n']:,} · mod {100.0*v['mod']/max(v['n'],1):.1f}% · "
              f"reaj {100.0*v['reaj']/max(v['n'],1):.1f}%")
    print("  nota: la modificación se mide en contratos.TIPO_CONTRATO/TIPO_MODIFICACION, "
          "NO en monto_aumentado (lleno al 2%)")
    print(f"  -> {p1}\n  -> {p2}")
    return {"procedimientos": len(filas)}


# ─────────────────────────────────────────────────────────────── D16 · CARTERA
# Flanco de EJECUCIÓN (orden 2026-08-24, va antes que 10-15): el nivel del medio.
#   Cartel → Oferta → ADJUDICACIÓN → Contrato → ORDEN DE PEDIDO → Recepción → Pago
# MONTO_EJECUTADO sale de ordenes_pedido (TOTAL_ORDEN, ya dedup por NRO_ORDEN en el
# extractor); el año de ejecución es FECHA_ELABORACION_ORDEN, NO el año del zip.
def d16():
    """cartera_proveedor — cuánto factura realmente un proveedor y de qué
    antigüedad viene. NIVEL DE MEDICION: ejecución (órdenes de pedido).

    Monedas (v2 2026-08-25): el archivo trae CINCO monedas (CRC, USD, EUR, JPY,
    GBP) y NO trae TIPO_CAMBIO por fila. Sumarlas juntas destruye a los
    importadores (hay casi tantas órdenes en USD como en colones). MONTO_CRC
    suma SOLO colones (dedupe por NRO_ORDEN, TOTAL_ORDEN una vez por orden);
    las otras monedas se reportan en su moneda original en MONTO_OTRAS_MONEDAS.
    La conversión por FECHA_ELABORACION_ORDEN contra la serie del BCCR queda
    pendiente (ver skill §9.4: falta saber qué serie manda la norma)."""
    adj_monto = defaultdict(float)      # (cedula, anio) -> monto adjudicado CRC
    for r in leer("adjudicaciones"):
        ced = esc(r, "CEDULA_PROVEEDOR")
        anio = esc(r, "MES_PUBLICACION")[:4]
        if ced and anio:
            adj_monto[(ced, anio)] += num(r.get("MONTO_ADJU_LINEA_CRC"))

    prov = defaultdict(lambda: {"ordenes": {}, "procs": set(), "estados": Counter(),
                                "origen": Counter(), "min_proc_anio": 9999,
                                "ced": "", "nom": "", "sosp": set(),
                                "monto_sosp": 0.0,
                                "ordenes_otras": {}, "monedas": Counter()})
    filas_tot = 0
    TOTAL_MAX_PLAUSIBLE = 1e11   # ₡100.000M: una orden mayor que eso es contaminación

    # registro global por proveedor: NRO_ORDEN -> (anio_max, monto, moneda, nro_sicop)
    # Una orden con líneas en varios meses/años se asigna al año de su elaboración
    # MÁXIMA (una sola vez), no a cada bucket — evita el doble conteo del TOTAL_ORDEN.
    global_ord = defaultdict(dict)
    estados_row = defaultdict(Counter)
    for r in leer("ordenes_pedido"):
        ced = esc(r, "CEDULAPROVEEDOR")
        if not ced:
            continue
        filas_tot += 1
        no = esc(r, "NRO_ORDEN")
        anio = esc(r, "FECHA_ELABORACION_ORDEN")[:4] or "(sin fecha)"
        moneda = (esc(r, "MONEDA_ORDEN") or "CRC").strip().upper()
        monto = num(r.get("TOTAL_ORDEN"))
        estados_row[(ced, anio)][esc(r, "ESTADO_ORDEN") or "(vacío)"] += 1
        prev = global_ord[ced].get(no)
        if prev is None or anio > prev[0]:
            global_ord[ced][no] = (anio, monto, moneda, esc(r, "NRO_SICOP"))

    for ced, ordenes in global_ord.items():
        for no, (anio, monto, moneda, ns) in ordenes.items():
            d = prov[(ced, anio)]
            d["ced"] = ced
            d["nom"] = d["nom"] or ""
            d["monedas"][moneda] += 1
            if monto > TOTAL_MAX_PLAUSIBLE:
                if no not in d["sosp"]:
                    d["sosp"].add(no)
                    d["monto_sosp"] += monto
                continue
            if moneda == "CRC":
                d["ordenes"][no] = monto   # TOTAL_ORDEN es de la orden completa
            else:
                d["ordenes_otras"][no] = monto  # moneda original; conversión BCCR pendiente
            if ns:
                d["procs"].add(ns)
                try:
                    pa = int(ns[:4])
                    d["origen"][str(pa)] += 1
                    d["min_proc_anio"] = min(d["min_proc_anio"], pa)
                except ValueError:
                    pass
    # nombres desde el catálogo
    nom_cat = {esc(r, "CEDULA_PROVEEDOR"): esc(r, "NOMBRE_PROVEEDOR")
               for r in leer("proveedores") if esc(r, "CEDULA_PROVEEDOR")}
    for (ced, anio), d in prov.items():
        d["nom"] = nom_cat.get(ced, d["nom"])
        d["estados"] = estados_row.get((ced, anio), Counter())

    filas = []
    for (ced, anio), d in prov.items():
        monto = sum(d["ordenes"].values())
        adj = adj_monto.get((ced, anio), 0.0)
        n_prev = sum(v for k, v in d["origen"].items() if k < anio)
        n_tot = sum(d["origen"].values())
        ant = ""
        if d["min_proc_anio"] < 9999 and anio.isdigit():
            ant = int(anio) - d["min_proc_anio"]
        monedas_txt = "|".join(f"{k}:{v}" for k, v in d["monedas"].most_common(5))
        filas.append({
            "CEDULA_PROVEEDOR": ced, "NOMBRE_PROVEEDOR": d["nom"],
            "ANIO_EJECUCION": anio,
            "N_ORDENES_CRC": len(d["ordenes"]),
            "MONTO_EJECUTADO_CRC": round(monto, 2),
            "N_ORDENES_OTRAS_MONEDAS": len(d["ordenes_otras"]),
            "MONTO_OTRAS_MONEDAS_ORIGEN": round(sum(d["ordenes_otras"].values()), 2),
            "MONEDAS": monedas_txt,
            "N_SOSPECHOSAS": len(d["sosp"]),
            "MONTO_SOSPECHOSO_CRC": round(d["monto_sosp"], 2),
            "N_PROCEDIMIENTOS_ACTIVOS": len(d["procs"]),
            "PCT_DE_ANIOS_ANTERIORES": round(100.0 * n_prev / n_tot, 1) if n_tot else 0,
            "ANTIGUEDAD_MAX_ANIOS": ant,
            "ORIGEN_POR_ANIO": "|".join(f"{k}:{v}" for k, v in sorted(d["origen"].items())),
            "MONTO_ADJUDICADO_CRC": round(adj, 2),
            "RATIO_EJECUCION_CAPTACION": round(monto / adj, 1) if adj else "",
            "ESTADOS_ORDEN": "|".join(f"{k}:{v}" for k, v in d["estados"].most_common(6)),
            "NIVEL_DE_MEDICION": "ejecucion (ordenes de pedido)",
        })
    filas.sort(key=lambda x: -x["MONTO_EJECUTADO_CRC"])
    cols = ["CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR", "ANIO_EJECUCION", "N_ORDENES_CRC",
            "MONTO_EJECUTADO_CRC", "N_ORDENES_OTRAS_MONEDAS",
            "MONTO_OTRAS_MONEDAS_ORIGEN", "MONEDAS",
            "N_SOSPECHOSAS", "MONTO_SOSPECHOSO_CRC",
            "N_PROCEDIMIENTOS_ACTIVOS",
            "PCT_DE_ANIOS_ANTERIORES", "ANTIGUEDAD_MAX_ANIOS", "ORIGEN_POR_ANIO",
            "MONTO_ADJUDICADO_CRC", "RATIO_EJECUCION_CAPTACION", "ESTADOS_ORDEN",
            "NIVEL_DE_MEDICION"]
    p1 = escribe(os.path.join(BASE, "cartera_proveedor.csv"), cols, filas)

    # resumen por año (todo el mercado) — dedupe por NRO_ORDEN; solo CRC en
    # MONTO_EJECUTADO_TOTAL_CRC; otras monedas separadas en moneda original
    resumen = defaultdict(lambda: {"ejec_por_orden": {}, "n_ord": set(),
                                   "n_prov": set(), "ejec_prev": {},
                                   "sosp": set(), "monto_sosp": 0.0,
                                   "otras": {}})
    for r in leer("ordenes_pedido"):
        anio = esc(r, "FECHA_ELABORACION_ORDEN")[:4]
        if not anio:
            continue
        e = resumen[anio]
        moneda = (esc(r, "MONEDA_ORDEN") or "CRC").strip().upper()
        no = esc(r, "NRO_ORDEN")
        monto = num(r.get("TOTAL_ORDEN"))
        if monto > TOTAL_MAX_PLAUSIBLE:
            if no not in e["sosp"]:
                e["sosp"].add(no)
                e["monto_sosp"] += monto
            continue
        if moneda == "CRC":
            if no not in e["ejec_por_orden"]:
                e["ejec_por_orden"][no] = monto
                e["n_ord"].add(no)
        else:
            if no not in e["otras"]:
                e["otras"][no] = monto
        ced = esc(r, "CEDULAPROVEEDOR")
        if ced:
            e["n_prov"].add(ced)
        ns = esc(r, "NRO_SICOP")
        try:
            if moneda == "CRC" and no not in e["ejec_prev"] and int(ns[:4]) < int(anio):
                e["ejec_prev"][no] = monto
        except (ValueError, TypeError):
            pass
    fr = []
    for anio in sorted(resumen):
        e = resumen[anio]
        ejec = sum(e["ejec_por_orden"].values())
        ejec_prev = sum(e.get("ejec_prev", {}).values())
        adj_tot = sum(v for (ced, a), v in adj_monto.items() if a == anio)
        fr.append({
            "ANIO": anio,
            "MONTO_EJECUTADO_TOTAL_CRC": round(ejec, 2),
            "MONTO_ADJUDICADO_TOTAL_CRC": round(adj_tot, 2),
            "RATIO_EJECUCION_CAPTACION": round(ejec / adj_tot, 1) if adj_tot else "",
            "PCT_EJECUCION_ANIOS_PREVIOS": round(100.0 * ejec_prev / ejec, 1)
                                           if ejec else 0,
            "N_ORDENES_CRC": len(e["n_ord"]),
            "N_PROVEEDORES": len(e["n_prov"]),
            "N_ORDENES_OTRAS_MONEDAS": len(e["otras"]),
            "MONTO_OTRAS_MONEDAS_ORIGEN": round(sum(e["otras"].values()), 2),
            "N_ORDENES_SOSPECHOSAS": len(e["sosp"]),
            "MONTO_SOSPECHOSO_CRC": round(e["monto_sosp"], 2),
        })
    cols_r = ["ANIO", "MONTO_EJECUTADO_TOTAL_CRC", "MONTO_ADJUDICADO_TOTAL_CRC",
              "RATIO_EJECUCION_CAPTACION", "PCT_EJECUCION_ANIOS_PREVIOS",
              "N_ORDENES_CRC", "N_PROVEEDORES", "N_ORDENES_OTRAS_MONEDAS",
              "MONTO_OTRAS_MONEDAS_ORIGEN", "N_ORDENES_SOSPECHOSAS",
              "MONTO_SOSPECHOSO_CRC"]
    p2 = escribe(os.path.join(BASE, "cartera_resumen.csv"), cols_r, fr)

    # ranking con ambos niveles (tarea 3.2): top proveedores 2026 por ejecución
    top2026 = [f for f in filas if f["ANIO_EJECUCION"] == "2026"][:50]
    cols_t = ["POSICION", "CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR",
              "MONTO_ADJUDICADO_CRC", "MONTO_EJECUTADO_CRC",
              "RATIO_EJECUCION_CAPTACION", "N_ORDENES_CRC"]
    ft = [{"POSICION": i + 1, **{k: v for k, v in f.items()
                                  if k in cols_t}} for i, f in enumerate(top2026)]
    p3 = escribe(os.path.join(BASE, "ranking_captacion_ejecucion.csv"), cols_t, ft)

    print(f"D16 cartera_proveedor · {len(filas):,} proveedor×año · "
          f"{len(prov):,} pares · filas de orden con cédula: {filas_tot:,} · "
          f"SÓLO CRC en MONTO_EJECUTADO (v2: otras monedas separadas)")
    for a in sorted(resumen):
        e = resumen[a]
        ejec = sum(e["ejec_por_orden"].values())
        adj_tot = sum(v for (c, y), v in adj_monto.items() if y == a)
        ratio = f"{ejec / adj_tot:.1f}" if adj_tot else "-"
        print(f"  {a}: ejecutado ₡{ejec:,.0f} CRC ({len(e['n_ord']):,} ord) · otras "
              f"{sum(e['otras'].values()):,.0f} ({len(e['otras'])} ord) · "
              f"adjudicado ₡{adj_tot:,.0f} · ratio {ratio} · "
              f"{100.0*sum(e.get('ejec_prev',{}).values())/max(ejec,1):.1f}% de años "
              f"previos · {len(e['sosp'])} sospechosas "
              f"(₡{e['monto_sosp']:,.0f} excluidos)")
    print(f"  -> {p1}\n  -> {p2}\n  -> {p3}")
    r26 = resumen.get("2026", {})
    return {"pares": len(filas), "anios": len(resumen),
            "resumen_2026": {"monte_ejecutado_crc": round(
                sum(r26.get("ejec_por_orden", {}).values()), 2),
                "n_ordenes_crc": len(r26.get("n_ord", set())),
                "n_proveedores": len(r26.get("n_prov", set())),
                "pct_anios_previos": round(
                    100.0 * sum(r26.get("ejec_prev", {}).values())
                    / max(sum(r26.get("ejec_por_orden", {}).values()), 1), 1)}}


# ─────────────────────────────────────────────────────────────── D12
def d12():
    """representante_compartido — cola de revisión (R4)."""
    rep_prov = defaultdict(Counter)
    adj_rows = []
    for r in leer("adjudicaciones"):
        ced = esc(r, "CEDULA_PROVEEDOR")
        rep = esc(r, "CEDULA_REPRESENTANTE")
        if ced and rep:
            rep_prov[ced][rep] += 1
        if ced:
            adj_rows.append(r)
    rep_nombre = {}
    for r in leer("adjudicaciones"):
        cr = esc(r, "CEDULA_REPRESENTANTE")
        if cr:
            rep_nombre.setdefault(cr, esc(r, "REPRESENTANTE"))

    prov_rep = {ced: c.most_common(1)[0][0] for ced, c in rep_prov.items()}

    # representante -> empresas
    rep_emp = defaultdict(lambda: {"empresas": set(), "n_adj": 0, "monto": 0.0,
                                   "insts": set(), "fams": set()})
    for r in adj_rows:
        rep = prov_rep.get(esc(r, "CEDULA_PROVEEDOR"))
        if not rep:
            continue
        d = rep_emp[rep]
        d["empresas"].add((esc(r, "CEDULA_PROVEEDOR"), esc(r, "NOMBRE_PROVEEDOR")))
        d["n_adj"] += 1
        d["monto"] += num(r.get("MONTO_ADJU_LINEA_CRC"))
        if esc(r, "INSTITUCION"):
            d["insts"].add(esc(r, "INSTITUCION"))
        if len(esc(r, "PROD_ID")) >= 6:
            d["fams"].add(esc(r, "PROD_ID")[:6])
    fe = []
    for rep, d in rep_emp.items():
        if len(d["empresas"]) < 2:
            continue
        fe.append({
            "CEDULA_REPRESENTANTE": rep, "REPRESENTANTE": rep_nombre.get(rep, ""),
            "N_EMPRESAS": len(d["empresas"]),
            "EMPRESAS": ";".join(f"{c}|{n}" for c, n in sorted(d["empresas"])),
            "N_ADJUDICACIONES": d["n_adj"], "MONTO_TOTAL_CRC": round(d["monto"], 2),
            "INSTITUCIONES": ",".join(sorted(d["insts"])),
            "FAMILIAS": ",".join(sorted(d["fams"])),
        })
    fe.sort(key=lambda x: -x["N_EMPRESAS"])
    cols_e = ["CEDULA_REPRESENTANTE", "REPRESENTANTE", "N_EMPRESAS", "EMPRESAS",
              "N_ADJUDICACIONES", "MONTO_TOTAL_CRC", "INSTITUCIONES", "FAMILIAS"]
    p1 = escribe(os.path.join(BASE, "representante_empresas.csv"), cols_e, fe)

    # líneas de competencia donde 2+ oferentes comparten representante
    cartel_inst = {}
    for r in leer("carteles"):
        ns = esc(r, "NRO_SICOP")
        if ns:
            cartel_inst.setdefault(ns, esc(r, "CEDULA_INSTITUCION"))
    inst_nom = {esc(r, "CEDULA"): esc(r, "NOMBRE_INSTITUCION")
                for r in leer("instituciones") if esc(r, "CEDULA")}
    por_linea = defaultdict(list)
    for r in cruzar_competencia():
        por_linea[(esc(r, "NRO_SICOP"), esc(r, "NRO_LINEA"))].append(r)

    fc = []
    for (ns, nl), rows in por_linea.items():
        if len(rows) < 2:
            continue
        por_rep = defaultdict(list)
        for r in rows:
            rep = prov_rep.get(esc(r, "CEDULA_PROVEEDOR"))
            if rep:
                por_rep[rep].append(r)
        for rep, rr in por_rep.items():
            if len(rr) < 2:
                continue
            empresas = sorted({(esc(x, "CEDULA_PROVEEDOR"), esc(x, "NOMBRE_PROVEEDOR"))
                               for x in rr})
            precios = [num(x.get("PRECIO_UNITARIO_CRC")) for x in rr]
            adj = [x for x in rr if esc(x, "ES_ADJUDICATARIO") == "S"]
            fc.append({
                "NRO_SICOP": ns, "NRO_LINEA": nl,
                "ANIO": esc(rr[0], "MES_PUBLICACION")[:4],
                "INSTITUCION": inst_nom.get(cartel_inst.get(ns, ""), cartel_inst.get(ns, "")),
                "CEDULA_REPRESENTANTE": rep, "REPRESENTANTE": rep_nombre.get(rep, ""),
                "N_EMPRESAS_MISMO_REP": len(rr),
                "EMPRESAS": ";".join(f"{c}|{n}" for c, n in empresas),
                "PRECIOS_OFERTADOS_CRC": ";".join(f"{p:,.0f}" for p in sorted(precios)),
                "ADJUDICATARIO": esc(adj[0], "NOMBRE_PROVEEDOR") if adj else "",
                "ADJUDICATARIO_COMPARTE_REP": "S" if adj else "N",
                "N_OFERENTES_TOTAL": len(rows),
                "ADVERTENCIA": ADVERTENCIA_REP,
            })
    fc.sort(key=lambda x: -x["N_OFERENTES_TOTAL"])
    cols_c = ["NRO_SICOP", "NRO_LINEA", "ANIO", "INSTITUCION",
              "CEDULA_REPRESENTANTE", "REPRESENTANTE", "N_EMPRESAS_MISMO_REP",
              "EMPRESAS", "PRECIOS_OFERTADOS_CRC", "ADJUDICATARIO",
              "ADJUDICATARIO_COMPARTE_REP", "N_OFERENTES_TOTAL", "ADVERTENCIA"]
    p2 = escribe(os.path.join(BASE, "representante_competencia.csv"), cols_c, fc)
    with io.open(os.path.join(BASE, "README_integridad.md"), "w",
                 encoding="utf-8") as f:
        f.write(README_INTEGRIDAD + "\n")
    print(f"D12 representante_compartido · {len(fe):,} representantes con ≥2 empresas · "
          f"{len(fc):,} líneas donde 2+ oferentes comparten representante")
    print(f"  -> {p1}\n  -> {p2}\n  -> README_integridad.md")
    return {"representantes": len(fe), "lineas": len(fc)}


# ─────────────────────────────────────────────────────────────── D13
def d13():
    """precios_identicos — cola de revisión con REPETICION_PAR."""
    catalogo = {esc(r, "CODIGO_PRODUCTO_CL"): (esc(r, "MARCA"), esc(r, "MODELO"))
                for r in leer("catalogo_productos")}
    cartel_inst = {}
    for r in leer("carteles"):
        ns = esc(r, "NRO_SICOP")
        if ns:
            cartel_inst.setdefault(ns, esc(r, "CEDULA_INSTITUCION"))
    inst_nom = {esc(r, "CEDULA"): esc(r, "NOMBRE_INSTITUCION")
                for r in leer("instituciones") if esc(r, "CEDULA")}
    nombres = {esc(r, "CEDULA_PROVEEDOR"): esc(r, "NOMBRE_PROVEEDOR")
               for r in leer("proveedores") if esc(r, "CEDULA_PROVEEDOR")}

    por_linea = defaultdict(list)
    for r in cruzar_competencia():
        por_linea[(esc(r, "NRO_SICOP"), esc(r, "NRO_LINEA"))].append(r)

    # pares (a,b) que coinciden en precio en la misma línea -> veces en todo el corpus
    par_veces = Counter()
    coincidencias = []  # (linea, precio, cédulas)
    for (ns, nl), rows in por_linea.items():
        por_precio = defaultdict(set)
        for r in rows:
            pu = num(r.get("PRECIO_UNITARIO_CRC"))
            if pu > 0:
                por_precio[round(pu, 2)].add(esc(r, "CEDULA_PROVEEDOR"))
        for precio, ceds in por_precio.items():
            ceds = [c for c in ceds if c]
            if len(ceds) < 2:
                continue
            coincidencias.append((ns, nl, precio, ceds))
            for i in range(len(ceds)):
                for j in range(i + 1, len(ceds)):
                    par_veces[tuple(sorted((ceds[i], ceds[j])))] += 1

    filas = []
    for ns, nl, precio, ceds in coincidencias:
        # repetición del par: máximo de los pares de esta línea (otras líneas)
        rep = 0
        par_elegido = ""
        for i in range(len(ceds)):
            for j in range(i + 1, len(ceds)):
                par = tuple(sorted((ceds[i], ceds[j])))
                if par_veces[par] > rep:
                    rep = par_veces[par]
                    par_elegido = f"{nombres.get(par[0], par[0])}|{nombres.get(par[1], par[1])}"
        rows = por_linea.get((ns, nl), [])
        cl = ""
        for r in rows:
            if esc(r, "CODIGO_PRODUCTO_CL"):
                cl = esc(r, "CODIGO_PRODUCTO_CL")
                break
        ma, mo = catalogo.get(cl, ("", ""))
        adj = [r for r in rows if esc(r, "ES_ADJUDICATARIO") == "S"]
        filas.append({
            "NRO_SICOP": ns, "NRO_LINEA": nl,
            "ANIO": (rows[0].get("MES_PUBLICACION") or "")[:4] if rows else "",
            "INSTITUCION": inst_nom.get(cartel_inst.get(ns, ""), cartel_inst.get(ns, "")),
            "PRECIO_CRC": round(precio, 2),
            "N_OFERENTES_MISMO_PRECIO": len(ceds),
            "OFERENTES": ";".join(f"{c}|{nombres.get(c, c)}" for c in sorted(ceds)),
            "N_OFERENTES_TOTAL": len(rows),
            "ES_ADJUDICADO_UNO_DE_ELLOS": "S" if adj else "N",
            "MARCA": ma, "MODELO": mo,
            "REPETICION_PAR": rep,
            "PAR_REPETIDO": par_elegido,
            "ADVERTENCIA": ADVERTENCIA_PRECIOS,
        })
    filas.sort(key=lambda x: (-x["REPETICION_PAR"], -x["N_OFERENTES_MISMO_PRECIO"]))
    cols = ["NRO_SICOP", "NRO_LINEA", "ANIO", "INSTITUCION", "PRECIO_CRC",
            "N_OFERENTES_MISMO_PRECIO", "OFERENTES", "N_OFERENTES_TOTAL",
            "ES_ADJUDICADO_UNO_DE_ELLOS", "MARCA", "MODELO", "REPETICION_PAR",
            "PAR_REPETIDO", "ADVERTENCIA"]
    p = escribe(os.path.join(BASE, "precios_identicos.csv"), cols, filas)
    top = filas[:5] if filas else []
    print(f"D13 precios_identicos · {len(filas):,} líneas con 2+ oferentes al mismo "
          f"precio exacto · {len(par_veces):,} pares")
    for f in top:
        print(f"  rep={f['REPETICION_PAR']:>3}  {f['NRO_SICOP']} L{f['NRO_LINEA']} "
              f"₡{f['PRECIO_CRC']:,.0f} · {f['PAR_REPETIDO'][:60]}")
    print(f"  -> {p}")
    return {"lineas": len(filas), "pares": len(par_veces)}


# ─────────────────────────────────────────────────────── D17 · MERCADO (tarea 3.1)
def d17(familia="461816"):
    """Mercado de una familia con los DOS niveles: captación (adjudicaciones) y
    ejecución (órdenes de pedido). La cifra publicada antes medía solo captación
    (p. ej. calzado de seguridad ~₡5,6M/mes) y subestimaba por una magnitud."""
    procs = set()   # NRO_SICOP de la familia (adjudicaciones + ejecución)
    captacion_pares = 0.0
    captacion_monto = 0.0
    for r in leer("adjudicaciones"):
        if esc(r, "PROD_ID").startswith(familia):
            procs.add(esc(r, "NRO_SICOP"))
            captacion_pares += num(r.get("CANTIDAD"))
            captacion_monto += num(r.get("MONTO_ADJU_LINEA_CRC"))
    for nombre, campocod in (("lineas_contratadas", "CODIGO_PRODUCTO"),
                             ("lineas_recibidas", "CODIGO_PRODUCTO")):
        for r in leer(nombre):
            if esc(r, campocod).startswith(familia):
                procs.add(esc(r, "NRO_SICOP"))
    n_ord = 0
    ejecutado = 0.0
    otras_monto = 0.0
    sosp_ords = set()
    monto_sosp = 0.0
    ords = set()
    ords_otras = set()
    for r in leer("ordenes_pedido"):
        if esc(r, "NRO_SICOP") not in procs:
            continue
        no = esc(r, "NRO_ORDEN")
        m = num(r.get("TOTAL_ORDEN"))
        moneda = (esc(r, "MONEDA_ORDEN") or "CRC").strip().upper()
        if m > 1e11:
            if no not in sosp_ords:
                sosp_ords.add(no)
                monto_sosp += m
            continue
        if moneda == "CRC":
            if no not in ords:
                ords.add(no)
                ejecutado += m
        else:
            if no not in ords_otras:
                ords_otras.add(no)
                otras_monto += m
    n_ord = len(ords)
    n_otras = len(ords_otras)

    # ejecución POR LÍNEA de la familia (precisa al producto): contratadas + recibidas
    ejecucion_lineas = 0.0
    pares_ejecutados = 0.0
    for r in leer("lineas_contratadas"):
        if not esc(r, "CODIGO_PRODUCTO").startswith(familia):
            continue
        ejecucion_lineas += a_crc(num(r.get("PRECIO_UNITARIO")),
                                 r.get("TIPO_MONEDA"),
                                 num(r.get("TIPO_CAMBIO_CRC"))) * num(r.get("CANTIDAD_CONTRATADA"))
        pares_ejecutados += num(r.get("CANTIDAD_CONTRATADA"))
    for r in leer("lineas_recibidas"):
        if not esc(r, "CODIGO_PRODUCTO").startswith(familia):
            continue
        # el campo 'precio' de recibidas no declara moneda: se trata como CRC (declarado)
        ejecucion_lineas += num(r.get("precio")) * num(r.get("CANTIDAD_REAL_RECIBIDA"))
        pares_ejecutados += num(r.get("CANTIDAD_REAL_RECIBIDA"))

    filas = [{
        "FAMILIA_UNSPSC": familia,
        "NIVEL_CAPTACION": "adjudicaciones (ProcedimientoAdjudicacion)",
        "PARES_ADJUDICADOS": round(captacion_pares, 2),
        "MONTO_ADJUDICADO_CRC": round(captacion_monto, 2),
        "NIVEL_EJECUCION_ORDENES": "ordenes de pedido (OrdenPedido, por NRO_SICOP)",
        "N_ORDENES_CRC": n_ord,
        "MONTO_ORDENES_CRC": round(ejecutado, 2),
        "N_ORDENES_OTRAS_MONEDAS": n_otras,
        "MONTO_OTRAS_MONEDAS_ORIGEN": round(otras_monto, 2),
        "NIVEL_EJECUCION_LINEAS": "lineas_contratadas + lineas_recibidas de la familia",
        "PARES_EJECUTADOS_LINEAS": round(pares_ejecutados, 2),
        "MONTO_EJECUTADO_LINEAS_CRC": round(ejecucion_lineas, 2),
        "RATIO_ORDENES_CAPTACION": round(ejecutado / captacion_monto, 1)
                                   if captacion_monto else "",
        "RATIO_LINEAS_CAPTACION": round(ejecucion_lineas / captacion_monto, 1)
                                  if captacion_monto else "",
        "N_PROCEDIMIENTOS_FAMILIA": len(procs),
        "N_ORDENES_SOSPECHOSAS": len(sosp_ords),
        "MONTO_SOSPECHOSO_CRC": round(monto_sosp, 2),
        "COBERTURA": ("las órdenes se unen por NRO_SICOP y su TOTAL_ORDEN cubre la "
                     "orden completa (puede incluir otras familias) — es cota superior; "
                     "la ejecución por líneas es precisa al producto. SÓLO monedas CRC "
                     "en MONTO_ORDENES_CRC (otras separadas en moneda original, "
                     "conversión BCCR pendiente). El precio de lineas_recibidas se "
                     "trata como CRC (la fuente no declara moneda)."),
    }]
    cols = ["FAMILIA_UNSPSC", "NIVEL_CAPTACION", "PARES_ADJUDICADOS",
            "MONTO_ADJUDICADO_CRC", "NIVEL_EJECUCION_ORDENES", "N_ORDENES_CRC",
            "MONTO_ORDENES_CRC", "N_ORDENES_OTRAS_MONEDAS", "MONTO_OTRAS_MONEDAS_ORIGEN",
            "NIVEL_EJECUCION_LINEAS", "PARES_EJECUTADOS_LINEAS",
            "MONTO_EJECUTADO_LINEAS_CRC", "RATIO_ORDENES_CAPTACION",
            "RATIO_LINEAS_CAPTACION", "N_PROCEDIMIENTOS_FAMILIA",
            "N_ORDENES_SOSPECHOSAS", "MONTO_SOSPECHOSO_CRC", "COBERTURA"]
    p = escribe(os.path.join(BASE, f"mercado_{familia}.csv"), cols, filas)
    f = filas[0]
    print(f"D17 mercado {familia} · captación {captacion_pares:,.0f} pares / "
          f"₡{captacion_monto:,.0f} · órdenes CRC {n_ord:,} / ₡{ejecutado:,.0f} "
          f"(+{n_otras:,} otras {otras_monto:,.0f}) "
          f"(ratio {f['RATIO_ORDENES_CAPTACION'] or '-'}) · líneas "
          f"{pares_ejecutados:,.0f} pares / ₡{ejecucion_lineas:,.0f} "
          f"(ratio {f['RATIO_LINEAS_CAPTACION'] or '-'})")
    print(f"  -> {p}")
    return filas[0]


def main():
    ap = argparse.ArgumentParser(description="Derivadas 10-15 + cartera (16) + mercado")
    ap.add_argument("cmd", choices=["10", "11", "12", "13", "14", "15", "16",
                                   "cartera", "17", "mercado", "todo"])
    ap.add_argument("--codigo", default="461816", help="familia UNSPSC (tarea 3.1)")
    a = ap.parse_args()
    if a.cmd == "10":
        return d10()
    if a.cmd == "11":
        return d11()
    if a.cmd == "14":
        return d14()
    if a.cmd == "15":
        return d15()
    if a.cmd == "12":
        return d12()
    if a.cmd == "13":
        return d13()
    if a.cmd in ("16", "cartera"):
        return d16()
    if a.cmd in ("17", "mercado"):
        return d17(a.codigo)
    res = {}
    # orden urgente: cartera (16) PRIMERO, luego 10 → 14 → 11 → 15 → 12 → 13
    for fn in (d16, d10, d14, d11, d15, d12, d13):
        res[fn.__name__] = fn()
    return res


if __name__ == "__main__":
    main()
