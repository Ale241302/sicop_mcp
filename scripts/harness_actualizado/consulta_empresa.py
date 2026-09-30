#!/usr/bin/env python3
"""
consulta_empresa.py — Ficha de participación de una empresa en contratación pública.

Responde: ¿en cuántos procedimientos participó, cuántos ganó, por cuánto, ante
quién y con qué frecuencia? Busca por cédula o por parte del nombre.

    python3 consulta_empresa.py --datos ./salida --empresa "CAPRIS"
    python3 consulta_empresa.py --datos ./salida --cedula 3101005113

Sólo biblioteca estándar. No usa ningún modelo: es un conteo.
"""
import argparse, csv, glob, os, sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10 * 1024 * 1024)


def leer(datos, nombre):
    """CONVENCIONES_SICOP §1: conjuntos con sufijo de año, derivadas sin él."""
    p = os.path.join(datos, f"{nombre}.csv")
    if not os.path.exists(p):
        c = sorted(glob.glob(os.path.join(datos, f"{nombre}_[0-9][0-9][0-9][0-9].csv")))
        if not c:
            return []
        p = c[-1]
    with open(p, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def num(x):
    try:
        return float(str(x or "").strip() or 0)
    except ValueError:
        return 0.0


def crc(v):
    return f"₡{v:,.0f}".replace(",", ".")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", required=True)
    ap.add_argument("--empresa", help="parte del nombre, sin importar mayúsculas")
    ap.add_argument("--cedula")
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    if not (a.empresa or a.cedula):
        print("indicá --empresa o --cedula"); return 2

    prov = leer(a.datos, "proveedores")
    catalogo = {r["CEDULA_PROVEEDOR"]: r for r in prov}

    # ── resolver a quién estamos consultando ────────────────────────────────
    if a.cedula:
        cedulas = [a.cedula]
    else:
        q = a.empresa.upper()
        cedulas = [c for c, r in catalogo.items()
                   if q in (r.get("NOMBRE_PROVEEDOR") or "").upper()]
        if not cedulas:
            print(f"Ninguna empresa del catálogo contiene «{a.empresa}».")
            print("El catálogo tiene", len(catalogo), "proveedores registrados.")
            return 1
        if len(cedulas) > 1:
            print(f"«{a.empresa}» coincide con {len(cedulas)} empresas. "
                  f"No se agregan entre sí — elegí una:\n")
            for c in cedulas[:20]:
                print(f"  {c}  {catalogo[c].get('NOMBRE_PROVEEDOR','')}")
            return 1

    ced = cedulas[0]
    ficha = catalogo.get(ced, {})
    nombre = ficha.get("NOMBRE_PROVEEDOR") or "[nombre no está en el catálogo]"

    ofe = leer(a.datos, "ofertas")
    adj = leer(a.datos, "adjudicaciones")
    car = leer(a.datos, "carteles")
    inst = {r["CEDULA"]: r.get("NOMBRE_INSTITUCION", "") for r in leer(a.datos, "instituciones")}
    meta = {r["NRO_SICOP"]: r for r in car}

    mias_ofe = [r for r in ofe if r.get("CEDULA_PROVEEDOR") == ced]
    proc_ofertados = {r["NRO_SICOP"] for r in mias_ofe}
    mias_adj = [r for r in adj if r.get("CEDULA_PROVEEDOR") == ced]
    proc_ganados = {r["NRO_SICOP"] for r in mias_adj}
    monto = sum(num(r.get("MONTO_ADJU_LINEA_CRC")) for r in mias_adj)

    print("=" * 74)
    print(f" {nombre}")
    print(f" cédula {ced} · {ficha.get('TIPO_PROVEEDOR','')} · "
          f"tamaño {ficha.get('TAMAÑO_PROVEEDOR') or '[sin dato]'}"
          + (f" · constituida {ficha.get('FECHA_CONSTITUCION','')[:10]}"
             if ficha.get("FECHA_CONSTITUCION") else ""))
    print("=" * 74)

    print(f"\nPARTICIPÓ EN     {len(proc_ofertados):>6} procedimientos "
          f"({len(mias_ofe)} ofertas presentadas)")
    print(f"FUE ADJUDICADA   {len(proc_ganados):>6} procedimientos · "
          f"{len(mias_adj)} líneas · {crc(monto)}")
    if proc_ofertados:
        cruzados = proc_ofertados & proc_ganados
        print(f"TASA DE ÉXITO    {len(cruzados) / len(proc_ofertados) * 100:>5.1f} % "
              f"sobre los procedimientos en que sí consta que ofertó")

    # ── advertencia obligatoria: sin esto la tasa engaña ─────────────────────
    solo_adj = proc_ganados - proc_ofertados
    if solo_adj:
        print(f"\n  ⚠ {len(solo_adj)} procedimientos donde fue adjudicada NO tienen su")
        print(f"    oferta registrada en el período descargado. La oferta puede haberse")
        print(f"    presentado en un mes anterior al corte. La tasa de éxito de arriba")
        print(f"    se calcula sólo sobre lo verificable, y por eso es un piso.")

    if not mias_ofe and not mias_adj:
        print("\nSin actividad registrada en el período descargado.")
        return 0

    print("\n── POR MES ─────────────────────────────────────────────────────────")
    mo = Counter(r.get("MES_PUBLICACION", "") for r in mias_ofe)
    ma = Counter(r.get("MES_PUBLICACION", "") for r in mias_adj)
    print(f"  {'mes':<10}{'ofertas':>10}{'líneas adj.':>14}")
    for m in sorted(set(mo) | set(ma)):
        print(f"  {m:<10}{mo.get(m,0):>10}{ma.get(m,0):>14}")

    print("\n── ANTE QUÉ INSTITUCIONES ──────────────────────────────────────────")
    por_inst = defaultdict(lambda: {"ofe": set(), "adj": 0, "monto": 0.0})
    for r in mias_ofe:
        ci = (meta.get(r["NRO_SICOP"], {}) or {}).get("CEDULA_INSTITUCION", "?")
        por_inst[ci]["ofe"].add(r["NRO_SICOP"])
    for r in mias_adj:
        ci = r.get("CEDULA_INSTITUCION") or \
             (meta.get(r["NRO_SICOP"], {}) or {}).get("CEDULA_INSTITUCION", "?")
        por_inst[ci]["adj"] += 1
        por_inst[ci]["monto"] += num(r.get("MONTO_ADJU_LINEA_CRC"))
    orden = sorted(por_inst.items(), key=lambda kv: -kv[1]["monto"])
    for ci, d in orden[:a.top]:
        nom = inst.get(ci) or (adj and next((r.get("INSTITUCION") for r in mias_adj
                               if r.get("CEDULA_INSTITUCION") == ci), "")) or ci
        print(f"  {str(nom)[:44]:<46} ofertó en {len(d['ofe']):>3} · "
              f"{d['adj']:>3} líneas · {crc(d['monto'])}")
    if len(orden) > a.top:
        print(f"  … y {len(orden) - a.top} instituciones más")

    print("\n── POR VÍA DE CONTRATACIÓN ─────────────────────────────────────────")
    vias = Counter((meta.get(p, {}) or {}).get("TIPO_PROCEDIMIENTO", "[sin cartel]")
                   for p in proc_ofertados)
    for v, n in vias.most_common():
        print(f"  {v[:46]:<48} {n:>4}")

    print("\n" + "-" * 74)
    print("Fuente: datos abiertos de SICOP. «Participó» = tiene oferta registrada.")
    print("Esto son datos y preguntas, no conclusiones. La lectura jurídica la")
    print("hace una persona.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
