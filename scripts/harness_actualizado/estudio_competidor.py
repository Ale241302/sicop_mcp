#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""estudio_competidor.py — expediente completo de un proveedor (estudio de competidor).

Une los tres niveles (captación / ejecución / entrega) + señales de integridad para
una empresa del corpus. NIVEL DE MEDICION declarado en cada sección (regla del REPORTE).

Uso:
  python3 estudio_competidor.py --cedula 3101095926
  python3 estudio_competidor.py --empresa "SONDEL" --top 8
  python3 estudio_competidor.py --cedula 3101095926 --csv dossier.csv

Secciones: ficha · captación (qué vende, a quién, por qué vía) · recurrencia (clientes
duraderos) · productos y precios vs mercado (marca+firma) · competencia (co-oferentes,
posición, tasa de victoria) · ejecución (cartera de órdenes) · entrega (cumplimiento) ·
señales de revisión (representante, precios idénticos, excepciones, invitaciones).
"""
import argparse
import csv
import glob
import io
import os
import sys
from collections import Counter, defaultdict
from statistics import median

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10 * 1024 * 1024)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import derivadas_extra as dx  # noqa: E402  (leer, esc, num, cruzar_competencia)

BASE = os.environ.get("SICOP_SALIDA", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "salida"))


def f(fmt, n):
    return f"{n:,.0f}".replace(",", ".")


def resolver_cedula(empresa):
    cat = {}
    for r in dx.leer("proveedores"):
        ced = dx.esc(r, "CEDULA_PROVEEDOR")
        nom = dx.esc(r, "NOMBRE_PROVEEDOR")
        if ced and nom:
            cat.setdefault(ced, nom)
    q = empresa.upper()
    ceds = [c for c, n in cat.items() if q in n.upper()]
    if len(ceds) > 1:
        print(f"«{empresa}» coincide con {len(ceds)} cédulas — elegir una:")
        for c in sorted(ceds):
            print(f"  {c}  {cat[c]}")
        return None
    return ceds[0] if ceds else None


def main():
    ap = argparse.ArgumentParser(description="Expediente de competidor")
    ap.add_argument("--cedula", default=None)
    ap.add_argument("--empresa", default=None)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()
    if not (a.cedula or a.empresa):
        print("Dar --cedula o --empresa.")
        return 2
    ced = a.cedula or resolver_cedula(a.empresa)
    if not ced:
        print(f"No se encontró «{a.empresa}» en el catálogo de proveedores.")
        return 1

    # ── ficha ──────────────────────────────────────────────────────────────
    ficha = {}
    for r in dx.leer("proveedores"):
        if dx.esc(r, "CEDULA_PROVEEDOR") == ced:
            ficha = r
            break
    nombre = dx.esc(ficha, "NOMBRE_PROVEEDOR") or ced
    print("=" * 78)
    print(f" EXPEDIENTE DE COMPETIDOR · {nombre} · {ced}")
    print(f" tipo {dx.esc(ficha,'TIPO_PROVEEDOR')} · tamaño "
          f"{dx.esc(ficha,'TAMAÑO_PROVEEDOR') or '[sin dato]'} · constituida "
          f"{dx.esc(ficha,'FECHA_CONSTITUCION')[:10] or '[sin dato]'}")
    print("=" * 78)

    # ── 1. CAPTACIÓN (adjudicaciones) ───────────────────────────────────────
    adj = [r for r in dx.leer("adjudicaciones")
           if dx.esc(r, "CEDULA_PROVEEDOR") == ced]
    procs = {dx.esc(r, "NRO_SICOP") for r in adj if dx.esc(r, "NRO_SICOP")}
    monto_adj = sum(dx.num(r.get("MONTO_ADJU_LINEA_CRC")) for r in adj)
    print(f"\n[NIVEL CAPTACIÓN — adjudicaciones, 2020-2026]")
    print(f"  {len(procs)} procedimientos · {len(adj)} líneas · ₡{f('', monto_adj)}")
    por_anio = Counter(dx.esc(r, "MES_PUBLICACION")[:4] for r in adj)
    print(f"  por año: {', '.join(f'{y}:{n}' for y, n in sorted(por_anio.items()))}")
    por_via = Counter(dx.esc(r, "TIPO_PROCEDIMIENTO") for r in adj)
    vias = ", ".join((v or "?") + ":" + str(n) for v, n in por_via.most_common(6))
    print(f"  por vía: {vias}")
    por_inst = defaultdict(lambda: [0, 0.0])   # inst -> [lineas, monto]
    for r in adj:
        e = por_inst[dx.esc(r, "INSTITUCION") or "?"]
        e[0] += 1
        e[1] += dx.num(r.get("MONTO_ADJU_LINEA_CRC"))
    print(f"  a quién le vende (top {a.top} por monto):")
    for inst, (nl, m) in sorted(por_inst.items(), key=lambda kv: -kv[1][1])[:a.top]:
        print(f"    {inst[:52]:<54} {nl:>4} líneas · ₡{f('', m)}")
    por_fam = defaultdict(lambda: [0, 0.0])
    for r in adj:
        fam = dx.esc(r, "PROD_ID")[:8] or "?"
        e = por_fam[fam]
        e[0] += 1
        e[1] += dx.num(r.get("MONTO_ADJU_LINEA_CRC"))
    print(f"  qué le vende (top {a.top} familias UNSPSC por monto):")
    for fam, (nl, m) in sorted(por_fam.items(), key=lambda kv: -kv[1][1])[:a.top]:
        print(f"    {fam}  {nl:>4} líneas · ₡{f('', m)}")

    # ── 2. RECURRENCIA (clientes duraderos) ─────────────────────────────────
    rel = defaultdict(set)   # (inst, familia) -> años
    rel_inst = defaultdict(set)
    for r in adj:
        inst = dx.esc(r, "INSTITUCION") or "?"
        fam = dx.esc(r, "PROD_ID")[:8] or "?"
        anio = dx.esc(r, "MES_PUBLICACION")[:4]
        rel_inst[inst].add(anio)
        if anio:
            rel[(inst, fam)].add(anio)
    print(f"\n[NIVEL CAPTACIÓN — recurrencia]")
    dur = sorted(((len(anios), inst) for inst, anios in rel_inst.items()),
                 reverse=True)[:a.top]
    print(f"  clientes con más años de relación:")
    for n, inst in dur:
        print(f"    {inst[:52]:<54} {n} años")
    print(f"  relaciones institución×familia recurrentes (≥3 años, top {a.top}):")
    for (inst, fam), anios in sorted(rel.items(), key=lambda kv: -len(kv[1]))[:a.top]:
        if len(anios) >= 3:
            print(f"    {inst[:38]:<40} {fam}  {len(anios)} años "
                  f"({','.join(sorted(anios))})")

    # ── 3. PRODUCTOS Y PRECIOS vs MERCADO (marca+firma) ─────────────────────
    catalogo = {dx.esc(r, "CODIGO_PRODUCTO_CL"): (dx.esc(r, "MARCA"), dx.esc(r, "MODELO"))
                for r in dx.leer("catalogo_productos") if dx.esc(r, "MARCA_PLAUSIBLE") == "S"}
    mercado = defaultdict(list)     # cl -> precios de TODOS los oferentes
    mios = defaultdict(list)        # cl -> precios del competidor
    co_oferentes = Counter()
    n_lineas_oferta = 0
    n_ganadas = 0
    posiciones = []
    for r in dx.cruzar_competencia():
        if dx.esc(r, "CEDULA_PROVEEDOR") == ced:
            n_lineas_oferta += 1
            pu = dx.num(r.get("PRECIO_UNITARIO_CRC"))
            if pu > 0:
                mios[dx.esc(r, "CODIGO_PRODUCTO_CL")].append(pu)
            if dx.esc(r, "ES_ADJUDICATARIO") == "S":
                n_ganadas += 1
        pu = dx.num(r.get("PRECIO_UNITARIO_CRC"))
        if pu > 0:
            mercado[dx.esc(r, "CODIGO_PRODUCTO_CL")].append(pu)
    print(f"\n[NIVEL CAPTACIÓN — ofertas y precios vs mercado, 2020-2026]")
    print(f"  ofertó en {n_lineas_oferta:,} líneas · ganó {n_ganadas:,} "
          f"({100.0*n_ganadas/max(n_lineas_oferta,1):.1f}%)")
    print(f"  productos donde vende con marca/modelo (top {a.top} por nº de ofertas "
          f"y su precio vs mediana del mercado):")
    vende = [(cl, len(v), median(v)) for cl, v in mios.items() if len(v) >= 3]
    vende.sort(key=lambda x: -x[1])
    for cl, n, mi in vende[:a.top]:
        ma, mo = catalogo.get(cl, ("", ""))
        med = median(mercado.get(cl, [0])) if mercado.get(cl) else 0
        delta = 100.0 * (mi - med) / med if med else 0
        print(f"    {cl} {ma or '-':<16} {mo or '-':<14} n={n:>3} · su mediana "
              f"₡{f('', mi):>12} vs mercado ₡{f('', med):>12} ({delta:+.0f}%)")

    # ── 4. COMPETENCIA ──────────────────────────────────────────────────────
    por_linea = defaultdict(list)
    for r in dx.cruzar_competencia():
        por_linea[(dx.esc(r, "NRO_SICOP"), dx.esc(r, "NRO_LINEA"))].append(r)
    for (ns, nl), rows in por_linea.items():
        en_linea = [r for r in rows if dx.esc(r, "CEDULA_PROVEEDOR") == ced]
        if not en_linea:
            continue
        precios = sorted(dx.num(r.get("PRECIO_UNITARIO_CRC")) for r in rows
                         if dx.num(r.get("PRECIO_UNITARIO_CRC")) > 0)
        if len(precios) < 2:
            continue
        pos = 1 + sum(1 for p in precios if p < dx.num(en_linea[0].get("PRECIO_UNITARIO_CRC")))
        posiciones.append(pos / len(precios))   # posición relativa 0..1
        for r in rows:
            co = dx.esc(r, "CEDULA_PROVEEDOR")
            if co and co != ced:
                co_oferentes[co] += 1
    if posiciones:
        print(f"\n[NIVEL CAPTACIÓN — competencia]")
        print(f"  posición de precio media en líneas competidas: "
              f"{100.0*sum(posiciones)/len(posiciones):.0f}% del rango "
              f"(0% = siempre el más barato)")
    print(f"  rivales más frecuentes (co-oferentes, top {a.top}):")
    nombres = {dx.esc(r, "CEDULA_PROVEEDOR"): dx.esc(r, "NOMBRE_PROVEEDOR")
               for r in dx.leer("proveedores") if dx.esc(r, "CEDULA_PROVEEDOR")}
    for co, n in co_oferentes.most_common(a.top):
        print(f"    {nombres.get(co, co)[:52]:<54} {n} líneas en común")

    # ── 5. EJECUCIÓN (cartera de órdenes) ───────────────────────────────────
    # Lee cartera_proveedor.csv (d16): MONTO_EJECUTADO_CRC = SOLO colones,
    # dedupe por NRO_ORDEN, año por elaboración máxima (v2 2026-08-25).
    print(f"\n[NIVEL EJECUCIÓN — órdenes de pedido, 2020-2026]")
    try:
        with io.open(os.path.join(BASE, "cartera_proveedor.csv"),
                     encoding="utf-8-sig") as fh:
            cartera = [r for r in csv.DictReader(fh)
                       if dx.esc(r, "CEDULA_PROVEEDOR") == ced]
    except OSError:
        cartera = []
    if cartera:
        tot_ejec = sum(dx.num(r.get("MONTO_EJECUTADO_CRC")) for r in cartera)
        tot_ord = sum(int(r.get("N_ORDENES_CRC") or 0) for r in cartera)
        tot_otras = sum(int(r.get("N_ORDENES_OTRAS_MONEDAS") or 0) for r in cartera)
        monto_otras = sum(dx.num(r.get("MONTO_OTRAS_MONEDAS_ORIGEN")) for r in cartera)
        print(f"  facturó ₡{f('', tot_ejec)} en {tot_ord:,} órdenes CRC "
              f"(+ {tot_otras:,} en otras monedas por ₡{f('', monto_otras)} — "
              f"conversión BCCR pendiente; TOTAL_ORDEN deduplicado por NRO_ORDEN, "
              f"sospechosos >₡100.000M excluidos)")
        for r in sorted(cartera, key=lambda x: x["ANIO_EJECUCION"]):
            if dx.num(r.get("MONTO_EJECUTADO_CRC")) > 0 or r["ANIO_EJECUCION"] == "2026":
                print(f"    {r['ANIO_EJECUCION']}: {r['N_ORDENES_CRC']:>4} órdenes CRC · "
                      f"₡{f('', dx.num(r.get('MONTO_EJECUTADO_CRC')))}")
        r26 = next((r for r in cartera if r["ANIO_EJECUCION"] == "2026"), None)
        if r26:
            ratio = dx.num(r26.get("RATIO_EJECUCION_CAPTACION"))
            print(f"  RATIO EJECUCIÓN/CAPTACIÓN 2026: {ratio}× "
                  f"(medir solo por adjudicaciones subestima {ratio:.0f}× el negocio)")
    else:
        print("  (correr `derivadas_extra.py 16` para generar la cartera)")

    # ── 6. ENTREGA (cumplimiento) ───────────────────────────────────────────
    try:
        with io.open(os.path.join(BASE, "desempeno_proveedor.csv"),
                     encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if dx.esc(r, "CEDULA_PROVEEDOR") == ced:
                    print(f"\n[NIVEL ENTREGA — recepciones]")
                    print(f"  {dx.esc(r,'NOMBRE_PROVEEDOR')}: {dx.esc(r,'LINEAS_RECIBIDAS')} "
                          f"líneas · cumple {dx.esc(r,'TASA_CUMPLIMIENTO')}% · "
                          f"mediana días {dx.esc(r,'DIAS_MEDIANO') or '-'} "
                          f"(negativo=adelanto) · con atraso {dx.esc(r,'PCT_CON_ATRASO')}% "
                          f"· muestra suficiente {dx.esc(r,'MUESTRA_SUFICIENTE')}")
                    break
    except OSError:
        print("\n[NIVEL ENTREGA] desempeno_proveedor.csv no está — correr "
              "derivadas_extra.py 10")

    # ── 7. SEÑALES (cola de revisión — no prueban nada por sí solas) ────────
    print(f"\n[SEÑALES — cola de revisión, ver README_integridad.md]")
    for tabla, col_filtro, etiqueta in (
            ("representante_competencia.csv", "EMPRESAS", "líneas donde compite con "
             "empresas de su mismo representante"),
            ("precios_identicos.csv", "OFERENTES", "líneas donde coincide al precio "
             "exacto con otro oferente")):
        try:
            with io.open(os.path.join(BASE, tabla), encoding="utf-8-sig") as fh:
                rows = [r for r in csv.DictReader(fh)
                        if ced in dx.esc(r, col_filtro)]
        except OSError:
            rows = []
        if rows:
            print(f"  {etiqueta}: {len(rows):,} (p. ej. {rows[0].get('NRO_SICOP','')})")
    exc = [r for r in dx.leer("excepciones_por_adjudicatario")
           if dx.esc(r, "CEDULA_PROVEEDOR") == ced]
    if exc:
        e = exc[0]
        print(f"  contratación por excepción: {dx.esc(e,'PROCEDIMIENTOS')} "
              f"procedimientos · {dx.esc(e,'LINEAS_ADJUDICADAS')} líneas · "
              f"causales: {dx.esc(e,'CAUSAL_EXCEPCION')[:80]}")

    print("\n" + "-" * 78)
    print("Fuente: datos abiertos de SICOP 2020-2026. Cada sección declara su nivel")
    print("de medición. Las señales no prueban conducta: el motivo real vive en el")
    print("acta de estudio técnico del expediente, que no está en los CSV.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
