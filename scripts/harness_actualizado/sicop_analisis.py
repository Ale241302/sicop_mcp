#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sicop_analisis.py — los siete análisis del encargo (apartado 5) sobre el
consolidado de SICOP. Sólo biblioteca estándar.

Uso: python3 scripts/sicop_analisis.py [salida] [año]
Salida: <salida>/ANALISIS_2026.md
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("salida")
YEAR = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
CONS = SALIDA / f"adjudicaciones_{YEAR}.csv"

L = []


def fmt(v) -> str:
    if v is None:
        return "—"
    return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(a, b) -> str:
    if b in (None, 0):
        return "—"
    return f"{a / b * 100:.1f}%"


def parse_number(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    for ch in ("₡", "$", "€", " ", "\u00a0", "\t"):
        s = s.replace(ch, "")
    if "e" in s.lower():
        s2 = s
        if "," in s2 and "." not in s2:
            s2 = s2.replace(",", ".")
        try:
            return float(s2)
        except ValueError:
            return None
    if not re.fullmatch(r"[+-]?[\d.,]+", s):
        return None
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        left, _, right = s.partition(",")
        if len(right) == 3 and "," not in left and "." not in left:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def load():
    rows = []
    with open(CONS, "r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            r["_crc"] = parse_number(r.get("MONTO_ADJU_LINEA_CRC")) or 0.0
            r["_usd"] = parse_number(r.get("MONTO_ADJU_LINEA_USD")) or 0.0
            rows.append(r)
    return rows


def nombre(r, campo, cedula_campo):
    n = (r.get(campo) or "").strip()
    c = (r.get(cedula_campo) or "").strip()
    return n or f"(sin nombre) {c}"


def main() -> int:
    rows = load()
    total_crc = sum(r["_crc"] for r in rows)
    total_usd = sum(r["_usd"] for r in rows)
    provs = {r.get("CEDULA_PROVEEDOR") for r in rows if r.get("CEDULA_PROVEEDOR")}
    insts = {r.get("CEDULA") for r in rows if r.get("CEDULA")}
    procs = {r.get("NRO_SICOP") for r in rows if r.get("NRO_SICOP")}
    objetos = {r.get("OBJETO_GASTO") for r in rows if r.get("OBJETO_GASTO")}
    meses_datos = {r.get("MES_PUBLICACION") for r in rows if r.get("MES_PUBLICACION")}

    L.append(f"# ANÁLISIS — Adjudicaciones SICOP {YEAR}")
    L.append("")
    L.append(f"Consolidado: `{CONS.name}` · {len(rows):,} líneas adjudicadas · "
             f"monto total ₡{fmt(total_crc)} · ${fmt(total_usd)}")
    L.append("")
    L.append(f"- Proveedores distintos: {len(provs):,}")
    L.append(f"- Instituciones distintas: {len(insts):,}")
    L.append(f"- Procedimientos distintos (NRO_SICOP): {len(procs):,}")
    L.append(f"- Objetos de gasto distintos: {len(objetos):,}")
    L.append(f"- Meses de publicación con datos: {', '.join(sorted(meses_datos))}")
    L.append("")
    L.append("> Regla general: cada análisis indica su método en una línea. Son **datos y "
             "preguntas, no conclusiones**: una concentración alta puede tener "
             "explicaciones legítimas (mercados con un solo oferente, especialización "
             "técnica, convenios marco). La lectura jurídica la hace una persona.")

    # ------------------------------------------------------------- 1 adjudicatario
    by_prov = defaultdict(lambda: {"monto": 0.0, "lineas": 0, "insts": set(),
                                   "objetos": defaultdict(float), "nombre": ""})
    for r in rows:
        c = (r.get("CEDULA_PROVEEDOR") or "").strip()
        if not c:
            continue
        d = by_prov[c]
        d["monto"] += r["_crc"]
        d["lineas"] += 1
        d["insts"].add(r.get("CEDULA") or "")
        if not d["nombre"]:
            d["nombre"] = (r.get("NOMBRE_PROVEEDOR") or "").strip()
        o = (r.get("OBJETO_GASTO") or "").strip() or "(sin objeto)"
        d["objetos"][o] += r["_crc"]

    L.append("")
    L.append("## 1. Concentración por adjudicatario")
    L.append("")
    L.append("**Método:** agrupación por `CEDULA_PROVEEDOR` (nombre tomado de la primera "
             "fila no vacía); monto = suma de `MONTO_ADJU_LINEA_CRC` por línea.")
    L.append("")

    top_monto = sorted(by_prov.items(), key=lambda kv: -kv[1]["monto"])[:30]
    L.append("### Top 30 por monto adjudicado (CRC)")
    L.append("")
    L.append("| # | Cédula | Nombre | Monto CRC | % total | Líneas | Instituciones | Principal objeto de gasto |")
    L.append("|---|---|---|---|---|---|---|---|")
    for i, (c, d) in enumerate(top_monto, 1):
        top_obj = max(d["objetos"], key=d["objetos"].get)
        L.append(f"| {i} | {c} | {d['nombre']} | ₡{fmt(d['monto'])} | {pct(d['monto'], total_crc)} "
                 f"| {d['lineas']:,} | {len(d['insts'])} | {top_obj} |")
    L.append("")

    top_lineas = sorted(by_prov.items(), key=lambda kv: -kv[1]["lineas"])[:30]
    L.append("### Top 30 por cantidad de líneas")
    L.append("")
    L.append("| # | Cédula | Nombre | Líneas | Monto CRC | % total | Instituciones |")
    L.append("|---|---|---|---|---|---|---|")
    for i, (c, d) in enumerate(top_lineas, 1):
        L.append(f"| {i} | {c} | {d['nombre']} | {d['lineas']:,} | ₡{fmt(d['monto'])} | "
                 f"{pct(d['monto'], total_crc)} | {len(d['insts'])} |")
    L.append("")
    L.append(f"**Salvedad:** hay {len(by_prov):,} adjudicatarios distintos; el top 30 por "
             f"monto concentra ₡{fmt(sum(d['monto'] for _, d in top_monto))} "
             f"({pct(sum(d['monto'] for _, d in top_monto), total_crc)} del total). "
             "Los nombres ausentes se identifican por cédula (ver VERIFICACIONES.md).")

    # ------------------------------------------------------------- 2 institución
    by_inst = defaultdict(lambda: {"monto": 0.0, "lineas": 0, "provs": defaultdict(float),
                                   "nombre": ""})
    for r in rows:
        c = (r.get("CEDULA") or "").strip()
        if not c:
            continue
        d = by_inst[c]
        d["monto"] += r["_crc"]
        d["lineas"] += 1
        if not d["nombre"]:
            d["nombre"] = (r.get("INSTITUCION") or "").strip()
        pc = (r.get("CEDULA_PROVEEDOR") or "").strip()
        if pc:
            d["provs"][pc] += r["_crc"]

    L.append("")
    L.append("## 2. Concentración por institución")
    L.append("")
    L.append("**Método:** agrupación por `CEDULA` de la institución; proveedores distintos "
             "por cédula de proveedor; % al principal = monto del adjudicatario que más "
             "recibió / monto total de la institución.")
    L.append("")
    L.append(f"Hay {len(by_inst):,} instituciones con adjudicaciones. Top 30 por monto:")
    L.append("")
    L.append("| # | Cédula | Institución | Monto CRC | % total | Líneas | Proveedores | Principal adjudicatario (% de la inst.) |")
    L.append("|---|---|---|---|---|---|---|---|")
    top_inst = sorted(by_inst.items(), key=lambda kv: -kv[1]["monto"])[:30]
    for i, (c, d) in enumerate(top_inst, 1):
        top_p = max(d["provs"], key=d["provs"].get) if d["provs"] else ""
        top_share = pct(d["provs"].get(top_p, 0), d["monto"]) if d["provs"] else "—"
        top_nombre = ""
        if top_p:
            top_nombre = by_prov.get(top_p, {}).get("nombre", "")
        L.append(f"| {i} | {c} | {d['nombre']} | ₡{fmt(d['monto'])} | {pct(d['monto'], total_crc)} "
                 f"| {d['lineas']:,} | {len(d['provs'])} | {top_p} {top_nombre} ({top_share}) |")
    L.append("")

    # --------------------------------------------------- 3 pares recurrentes
    pares = defaultdict(lambda: {"monto": 0.0, "lineas": 0, "meses": set(),
                                 "inst": "", "prov": ""})
    for r in rows:
        ic = (r.get("CEDULA") or "").strip()
        pc = (r.get("CEDULA_PROVEEDOR") or "").strip()
        if not ic or not pc:
            continue
        k = (ic, pc)
        d = pares[k]
        d["monto"] += r["_crc"]
        d["lineas"] += 1
        d["meses"].add(r.get("MES_PUBLICACION"))
        d["inst"] = (r.get("INSTITUCION") or "").strip()
        d["prov"] = (r.get("NOMBRE_PROVEEDOR") or "").strip()

    L.append("")
    L.append("## 3. Pares institución–proveedor recurrentes (varios meses)")
    L.append("")
    L.append("**Método:** par (`CEDULA` de institución, `CEDULA_PROVEEDOR`) con presencia en "
             "2 o más meses de publicación distintos, ordenado por monto acumulado.")
    L.append("")
    recurrentes = sorted(
        ((k, d) for k, d in pares.items() if len(d["meses"]) >= 2),
        key=lambda kv: -kv[1]["monto"])
    if not recurrentes:
        L.append("_No hay pares con 2 o más meses._")
    else:
        L.append(f"{len(recurrentes):,} pares recurrentes. Top 40 por monto acumulado:")
        L.append("")
        L.append("| # | Institución | Proveedor | Cédula prov. | Monto CRC | Líneas | Meses |")
        L.append("|---|---|---|---|---|---|---|")
        for i, ((ic, pc), d) in enumerate(recurrentes[:40], 1):
            L.append(f"| {i} | {d['inst']} ({ic}) | {d['prov']} | {pc} | ₡{fmt(d['monto'])} | "
                     f"{d['lineas']:,} | {', '.join(sorted(d['meses']))} |")
        if len(recurrentes) > 40:
            L.append(f"| … | (y {len(recurrentes) - 40} pares más) |")
    L.append("")

    # --------------------------------------------------- 4 representantes cruzados
    reps = defaultdict(lambda: {"nombre": "", "provs": defaultdict(float), "lineas": 0,
                                "meses": set()})
    for r in rows:
        rc = (r.get("CEDULA_REPRESENTANTE") or "").strip()
        pc = (r.get("CEDULA_PROVEEDOR") or "").strip()
        if not rc or not pc:
            continue
        d = reps[rc]
        if not d["nombre"]:
            d["nombre"] = (r.get("REPRESENTANTE") or "").strip()
        d["provs"][pc] += r["_crc"]
        d["lineas"] += 1
        d["meses"].add(r.get("MES_PUBLICACION"))

    L.append("")
    L.append("## 4. Representantes legales cruzados")
    L.append("")
    L.append("**Método:** una misma `CEDULA_REPRESENTANTE` no vacía que aparece con 2 o más "
             "cédulas de proveedor distintas; monto = suma de la línea donde aparece el par.")
    L.append("")
    cruzados = {rc: d for rc, d in reps.items() if len(d["provs"]) >= 2}
    if not cruzados:
        L.append("_No se encontraron representantes compartidos entre proveedores distintos._")
    else:
        L.append(f"{len(cruzados):,} representantes con más de un proveedor. "
                 f"Top 50 por monto:")
        L.append("")
        L.append("| # | Cédula rep. | Nombre | Proveedores (cédula → monto CRC) | Líneas | Meses |")
        L.append("|---|---|---|---|---|---|")
        for i, (rc, d) in enumerate(
                sorted(cruzados.items(), key=lambda kv: -sum(kv[1]["provs"].values()))[:50], 1):
            provs_txt = "; ".join(
                f"{pc} → ₡{fmt(m)}" for pc, m in
                sorted(d["provs"].items(), key=lambda kv: -kv[1])[:4])
            if len(d["provs"]) > 4:
                provs_txt += f" (+{len(d['provs']) - 4})"
            L.append(f"| {i} | {rc} | {d['nombre']} | {provs_txt} | {d['lineas']:,} | "
                     f"{', '.join(sorted(d['meses']))} |")
        L.append("")
        L.append("> Salvedad: un representante puede ser legal en varias empresas por "
                 "razones legítimas; esto lista los casos, no los interpreta. Cuando la "
                 "cédula del representante coincide con una de las cédulas de proveedor "
                 "listadas, se trata de una persona física que se representa a sí misma, "
                 "no de un cruce entre empresas.")
    L.append("")

    # --------------------------------------------------- 5 tipo y modalidad
    def tabla_por(campo, titulo):
        agg = defaultdict(lambda: {"monto": 0.0, "lineas": 0, "procs": set()})
        for r in rows:
            k = (r.get(campo) or "").strip() or "(vacío)"
            d = agg[k]
            d["monto"] += r["_crc"]
            d["lineas"] += 1
            d["procs"].add(r.get("NRO_SICOP"))
        L.append(f"### Distribución por {titulo}")
        L.append("")
        L.append("| Categoría | Monto CRC | % monto | Líneas | % líneas | Procedimientos |")
        L.append("|---|---|---|---|---|---|")
        for k, d in sorted(agg.items(), key=lambda kv: -kv[1]["monto"]):
            L.append(f"| {k} | ₡{fmt(d['monto'])} | {pct(d['monto'], total_crc)} | "
                     f"{d['lineas']:,} | {pct(d['lineas'], len(rows))} | {len(d['procs']):,} |")
        L.append("")

    L.append("")
    L.append("## 5. Distribución por tipo y modalidad de procedimiento")
    L.append("")
    L.append("**Método:** agrupación por `TIPO_PROCEDIMIENTO` y `MODALIDAD_PROCEDIMIENTO`; "
             "monto = suma de línea (CRC); % sobre el total de la corrida.")
    L.append("")
    tabla_por("TIPO_PROCEDIMIENTO", "tipo de procedimiento")
    tabla_por("MODALIDAD_PROCEDIMIENTO", "modalidad de procedimiento")

    # ------------------------------------------------------------- 6 estacionalidad
    L.append("")
    L.append("## 6. Estacionalidad mensual")
    L.append("")
    L.append("**Método:** agrupación por `MES_PUBLICACION`; variación = cambio porcentual "
             "contra el mes anterior con datos. Un salto no es un error: contrastar contra "
             "el ritmo real de adjudicación.")
    L.append("")
    por_mes = defaultdict(lambda: {"monto": 0.0, "lineas": 0})
    for r in rows:
        d = por_mes[r.get("MES_PUBLICACION")]
        d["monto"] += r["_crc"]
        d["lineas"] += 1
    L.append("| Mes | Líneas | Monto CRC | Δ líneas vs mes prev. | Δ monto vs mes prev. |")
    L.append("|---|---|---|---|---|")
    prev = None
    for mo in sorted(por_mes):
        d = por_mes[mo]
        dl = f"{((d['lineas'] - prev['lineas']) / prev['lineas'] * 100):+.1f}%" if prev and prev['lineas'] else "—"
        dm = f"{((d['monto'] - prev['monto']) / prev['monto'] * 100):+.1f}%" if prev and prev['monto'] else "—"
        L.append(f"| {mo} | {d['lineas']:,} | ₡{fmt(d['monto'])} | {dl} | {dm} |")
        prev = d
    L.append("")
    L.append(f"Nota: enero {YEAR} no figura porque `ProcedimientoAdjudicacion.csv` de enero "
             "no trae filas (ver VERIFICACIONES.md, punto a).")

    # ------------------------------------------------------------- 7 objetos de gasto
    obj = defaultdict(lambda: {"monto": 0.0, "lineas": 0, "provs": defaultdict(float)})
    for r in rows:
        o = (r.get("OBJETO_GASTO") or "").strip() or "(sin objeto)"
        d = obj[o]
        d["monto"] += r["_crc"]
        d["lineas"] += 1
        pc = (r.get("CEDULA_PROVEEDOR") or "").strip()
        if pc:
            d["provs"][pc] += r["_crc"]

    L.append("")
    L.append("## 7. Objetos de gasto dominantes")
    L.append("")
    L.append("**Método:** agrupación por `OBJETO_GASTO`; principales adjudicatarios = top 3 "
             "por monto dentro de cada objeto.")
    L.append("")
    L.append("| # | Objeto de gasto | Monto CRC | % total | Líneas | Principales adjudicatarios |")
    L.append("|---|---|---|---|---|---|")
    for i, (o, d) in enumerate(sorted(obj.items(), key=lambda kv: -kv[1]["monto"])[:20], 1):
        provs_txt = "; ".join(
            f"{by_prov.get(pc, {}).get('nombre', pc)} (₡{fmt(m)})" for pc, m in
            sorted(d["provs"].items(), key=lambda kv: -kv[1])[:3])
        L.append(f"| {i} | {o} | ₡{fmt(d['monto'])} | {pct(d['monto'], total_crc)} | "
                 f"{d['lineas']:,} | {provs_txt} |")
    L.append("")

    # ------------------------------------------------------------- cierre
    L.append("---")
    L.append("")
    L.append("**Método general:** análisis sobre `adjudicaciones_2026.csv` (una fila por "
             "línea adjudicada, deduplicada por `NRO_SICOP`+`LINEA`+`CEDULA_PROVEEDOR`); "
             "monto en CRC = `MONTO_ADJU_LINEA_CRC`. Salvedades: los nombres de proveedor "
             "ausentes se identifican por cédula; no se contrastó contra tipo de cambio "
             "oficial; la lectura jurídica de cualquier concentración la hace una persona. "
             "Período cubierto: enero–diciembre 2026 · fecha de extracción: ver "
             "`REPORTE.md` · archivo de origen: `ProcedimientoAdjudicacion.csv` por mes.")

    (SALIDA / "ANALISIS_2026.md").write_text("\n".join(L), encoding="utf-8")
    print(f"ANALISIS_2026.md escrito en {SALIDA.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
