#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sicop_verificar.py — verifica los puntos abiertos del encargo (apartado 4):

  a) Enero sin filas: contrastar ProcedimientoAdjudicacion.csv contra
     AdjudicacionesFirme.csv y Contratos.csv del mismo zip.
  b) Filas sin NOMBRE_PROVEEDOR: resolver por cédula contra el propio
     consolidado (otros meses) y contra InstitucionesRegistradas.csv.
  c) Coherencia de montos: MONTO_ADJU_LINEA vs MONTO_ADJU_LINEA_CRC/_USD
     según MONEDA_ADJUDICADA, y tasas implícitas.

Además: chequeo de duplicados por clave natural en el consolidado.

Uso: python3 scripts/sicop_verificar.py [salida] [año]
Salida: <salida>/VERIFICACIONES.md
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("salida")
YEAR = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
CONS = SALIDA / f"adjudicaciones_{YEAR}.csv"
CACHE = SALIDA / "_cache"
NATURAL_KEY = ("NRO_SICOP", "LINEA", "CEDULA_PROVEEDOR")


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


def fmt(v) -> str:
    if v is None:
        return "—"
    return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def read_consolidated(path: Path):
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def sniff(path: Path):
    """Codificación validando el archivo completo (un prefijo cortado a mitad
    de una secuencia UTF-8 multibyte falsearía la detección); delimitador por
    la primera línea."""
    raw = path.read_bytes()
    enc = "utf-8-sig"
    for cand in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            raw.decode(cand)
            enc = cand
            break
        except UnicodeDecodeError:
            continue
    sample = raw.decode(enc, errors="replace")
    line = sample.splitlines()[0] if sample else ""
    counts = {d: 0 for d in ",;\t|"}
    in_q = False
    for ch in line:
        if ch == '"':
            in_q = not in_q
        elif ch in counts and not in_q:
            counts[ch] += 1
    return enc, max(counts, key=counts.get) if any(counts.values()) else ","


def count_and_dates(zip_path: Path, member: str, tmp: Path):
    """Extrae un miembro y devuelve (n_filas, columnas, años-meses si hay columna fecha)."""
    found = False
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if Path(name).name.lower() == member.lower():
                with z.open(name) as src, open(tmp, "wb") as f:
                    shutil.copyfileobj(src, f, 1024 * 1024)
                found = True
                break
    if not found:
        return None, None, None
    enc, delim = sniff(tmp)
    n = 0
    header = []
    ym = Counter()
    date_col = None
    with open(tmp, "r", encoding=enc, newline="") as f:
        rdr = csv.reader(f, delimiter=delim)
        try:
            header = [h.strip() for h in next(rdr)]
        except StopIteration:
            return 0, [], Counter()
        for dc in header:
            if re.search(r"FECHA|ADJUD", dc, re.I):
                date_col = dc
                break
        di = header.index(date_col) if date_col else None
        for row in rdr:
            n += 1
            if di is not None and di < len(row) and row[di]:
                m2 = re.search(r"(19|20)\d{2}-\d{2}", row[di])
                if m2:
                    ym[m2.group(0)[:7]] += 1
    return n, header, dict(ym.most_common(12))


def main() -> int:
    rows = read_consolidated(CONS)
    # directorio temporal dentro del workspace (el sandbox no permite la Temp del sistema)
    tmpdir = SALIDA / "_tmp_verif"
    tmpdir.mkdir(parents=True, exist_ok=True)
    L = []
    L.append(f"# VERIFICACIONES — {YEAR}")
    L.append("")
    L.append(f"- **Consolidado:** `{CONS.name}` — {len(rows):,} filas")
    L.append(f"- **Manifiesto:** `manifiesto.json`")

    # ------------------------------------------------------------------ dup
    L.append("")
    L.append("## 0. Duplicados por clave natural (criterio de aceptación)")
    keys = [tuple((r.get(k) or "").strip() for k in NATURAL_KEY) for r in rows]
    dups = {k: c for k, c in Counter(keys).items() if c > 1}
    if dups:
        L.append("")
        L.append(f"**{sum(dups.values()) - len(dups)} filas duplicadas** en "
                 f"{len(dups)} claves: " + "; ".join(
                     f"{k} ×{c}" for k, c in list(dups.items())[:10]))
    else:
        L.append("")
        L.append(f"**Sin duplicados** por `NRO_SICOP`+`LINEA`+`CEDULA_PROVEEDOR` "
                 f"({len(keys):,} claves únicas). ✅")

    # ---------------------------------------------------------------- (a) enero
    L.append("")
    L.append("## a) Enero 2026: cero filas en ProcedimientoAdjudicacion.csv")
    L.append("")
    jan = CACHE / "202601.zip"
    if not jan.exists():
        L.append(f"**No se pudo verificar:** `{jan}` no está en la caché.")
    else:
        L.append(f"Zip `202601.zip` presente ({jan.stat().st_size / 1e6:.1f} MB). "
                 "Miembros del zip:")
        with zipfile.ZipFile(jan) as z:
            L.append("")
            L.append("```")
            for n in z.namelist():
                i = z.getinfo(n)
                L.append(f"  {n}  ({i.file_size / 1e6:.1f} MB)")
            L.append("```")
        L.append("")
        tmp = tmpdir
        for member in ("AdjudicacionesFirme.csv", "Contratos.csv"):
            n, header, ym = count_and_dates(jan, member, tmp / member)
            if n is None:
                L.append(f"- `{member}`: **no está en el zip**")
            else:
                L.append(f"- `{member}`: **{n:,} filas** — columnas: "
                         f"{', '.join(header[:12])}{'…' if len(header) > 12 else ''}")
                if ym:
                    L.append(f"  - Distribución de fechas (top 12): "
                             + ", ".join(f"{k}: {v:,}" for k, v in ym.items()))
        # AdjudicacionesFirme con detalle del mes de publicación
        n, header, ym = count_and_dates(jan, "AdjudicacionesFirme.csv",
                                        tmp / "af.csv")
        if n:
            L.append("")
            L.append("> Conclusión del chequeo: si estos archivos traen movimiento, "
                     "el vacío está en `ProcedimientoAdjudicacion.csv` de enero, "
                     "**no** en la actividad real de enero.")

    # ------------------------------------------------------- (b) nombres vacíos
    L.append("")
    L.append("## b) Filas sin NOMBRE_PROVEEDOR")
    sin_nombre = [r for r in rows if not (r.get("NOMBRE_PROVEEDOR") or "").strip()
                  and (r.get("CEDULA_PROVEEDOR") or "").strip()]
    L.append("")
    if not sin_nombre:
        L.append("**Ninguna fila** sin nombre de proveedor en el consolidado.")
    else:
        # resolución 1: el mismo proveedor con nombre en otros meses del consolidado
        nombre_por_cedula = {}
        for r in rows:
            c = (r.get("CEDULA_PROVEEDOR") or "").strip()
            n = (r.get("NOMBRE_PROVEEDOR") or "").strip()
            if c and n and c not in nombre_por_cedula:
                nombre_por_cedula[c] = n
        # resolución 2: registros dentro del zip del mes correspondiente
        # (InstitucionesRegistradas.csv y Proveedores.csv)
        registro_por_cedula = {}

        def leer_registro(mo, member):
            zp = CACHE / f"{mo}.zip"
            if not zp.exists():
                return
            t = tmpdir / f"{member}.csv"
            found = False
            with zipfile.ZipFile(zp) as z:
                for name in z.namelist():
                    if Path(name).name.lower() == member.lower():
                        with z.open(name) as src, open(t, "wb") as f:
                            shutil.copyfileobj(src, f, 1024 * 1024)
                        found = True
                        break
            if not found:
                return
            enc, delim = sniff(t)
            with open(t, "r", encoding=enc, newline="") as f:
                rdr = csv.DictReader(f, delimiter=delim)
                cols = {c.strip().upper(): c for c in (rdr.fieldnames or [])}
                ccol = next((cols[k] for k in ("CEDULA", "CEDULA_PROVEEDOR",
                                               "IDENTIFICACION", "ID") if k in cols), None)
                ncol = next((cols[k] for k in ("NOMBRE", "NOMBRE_PROVEEDOR",
                                               "RAZON_SOCIAL", "DESCRIPCION") if k in cols), None)
                if ccol and ncol:
                    for row in rdr:
                        cv = (row.get(ccol) or "").strip()
                        nv = (row.get(ncol) or "").strip()
                        if cv and nv and cv not in registro_por_cedula:
                            registro_por_cedula[cv] = nv

        for r in sin_nombre:
            mo = r.get("MES_PUBLICACION", "")
            leer_registro(mo, "InstitucionesRegistradas.csv")
            leer_registro(mo, "Proveedores.csv")
        L.append(f"**{len(sin_nombre):,} filas** sin `NOMBRE_PROVEEDOR` (cédula sí viene), "
                 f"distribuidas por mes:")
        por_mes = Counter(r.get("MES_PUBLICACION") for r in sin_nombre)
        L.append("")
        L.append("| Mes | Filas sin nombre |")
        L.append("|---|---|")
        for mo, c in sorted(por_mes.items()):
            L.append(f"| {mo} | {c} |")
        L.append("")
        L.append("Resolución por cédula (no se inventa ningún nombre):")
        L.append("")
        L.append("| Cédula | Mes | Consolidado | Registros del zip | Nombre |")
        L.append("|---|---|---|---|---|")
        for r in sorted(sin_nombre, key=lambda x: (x["MES_PUBLICACION"], x["CEDULA_PROVEEDOR"])):
            c = r["CEDULA_PROVEEDOR"].strip()
            c1 = nombre_por_cedula.get(c, "")
            c2 = registro_por_cedula.get(c, "")
            res = c1 or c2 or "**NO resuelto — queda vacío**"
            L.append(f"| {c} | {r.get('MES_PUBLICACION')} | {'sí' if c1 else 'no'} | "
                     f"{'sí' if c2 else 'no'} | {res} |")
        L.append("")
        L.append("> Regla aplicada: si no se puede resolver, el campo se deja vacío y se anota. "
                 "Registros consultados en el zip del mes: `InstitucionesRegistradas.csv` y "
                 "`Proveedores.csv`.")

    # ------------------------------------------------------------- (c) montos
    L.append("")
    L.append("## c) Coherencia de montos (muestra de verificación)")
    L.append("")
    por_moneda = Counter((r.get("MONEDA_ADJUDICADA") or "").strip() or "CRC" for r in rows)
    L.append("| Moneda | Filas | % |")
    L.append("|---|---|---|")
    tot = len(rows)
    for mo, c in por_moneda.most_common():
        L.append(f"| {mo or '(vacío→CRC)'} | {c:,} | {c / tot * 100:.1f}% |")
    L.append("")
    incoherentes = []          # (fila, detalle, magnitud)
    tasas = {"USD": [], "EUR": []}
    crc_faltante = 0
    ejemplos_crc_faltante = []
    sin_monto_linea = 0
    for r in rows:
        mon = (r.get("MONEDA_ADJUDICADA") or "").strip() or "CRC"
        m = parse_number(r.get("MONTO_ADJU_LINEA"))
        crc = parse_number(r.get("MONTO_ADJU_LINEA_CRC"))
        usd = parse_number(r.get("MONTO_ADJU_LINEA_USD"))
        if m is None:
            sin_monto_linea += 1
            continue
        if mon == "CRC":
            if crc is not None:
                if abs(crc - m) / max(abs(m), 1e-9) > 0.02:
                    incoherentes.append((r, f"CRC: línea={m:.6f} vs CRC={crc:.6f}",
                                         max(abs(m), abs(crc))))
            else:
                crc_faltante += 1
                if len(ejemplos_crc_faltante) < 5:
                    ejemplos_crc_faltante.append((r.get("NRO_SICOP"), r.get("LINEA"),
                                                  r.get("CEDULA_PROVEEDOR")))
        elif mon == "USD":
            if usd is not None:
                if abs(usd - m) / max(abs(m), 1e-9) > 0.02:
                    incoherentes.append((r, f"USD: línea={m:.6f} vs USD={usd:.6f}",
                                         max(abs(m), abs(usd))))
            else:
                crc_faltante += 1
                if len(ejemplos_crc_faltante) < 5:
                    ejemplos_crc_faltante.append((r.get("NRO_SICOP"), r.get("LINEA"),
                                                  r.get("CEDULA_PROVEEDOR")))
            if crc is not None and m:
                tasas["USD"].append(crc / m)
        elif mon == "EUR":
            if crc is not None and m:
                tasas["EUR"].append(crc / m)
            else:
                crc_faltante += 1
    if sin_monto_linea:
        L.append(f"**{sin_monto_linea:,} filas** sin `MONTO_ADJU_LINEA` numérico (se omiten "
                 "del chequeo de coherencia).")
        L.append("")
    materiales = [x for x in incoherentes if x[2] >= 1.0]
    centesimales = [x for x in incoherentes if x[2] < 1.0]
    if materiales:
        L.append(f"**{len(materiales):,} filas con incoherencia material** (diferencia > 2% "
                 "y magnitud ≥ 1 unidad de la moneda):")
        L.append("")
        L.append("| NRO_SICOP | Línea | Cédula prov. | Moneda | Detalle |")
        L.append("|---|---|---|---|---|")
        for r, d, _ in materiales[:20]:
            L.append(f"| {r.get('NRO_SICOP')} | {r.get('LINEA')} | {r.get('CEDULA_PROVEEDOR')} "
                     f"| {r.get('MONEDA_ADJUDICADA')} | {d} |")
        if len(materiales) > 20:
            L.append(f"| … | … | … | … | (y {len(materiales) - 20} más) |")
        L.append("")
    else:
        L.append("**Sin incoherencias materiales** (diferencia > 2% con magnitud ≥ 1 unidad "
                 "de moneda). ✅")
        L.append("")
    if centesimales:
        L.append(f"Hay {len(centesimales):,} diferencias **centesimales** (magnitud < 1 "
                 "unidad, p. ej. redondeo de céntimos), que no se consideran incoherencia. "
                 "Ejemplos:")
        L.append("")
        for r, d, _ in centesimales[:5]:
            L.append(f"- `{r.get('NRO_SICOP')}` línea {r.get('LINEA')}: {d}")
        L.append("")
    if crc_faltante:
        L.append(f"**{crc_faltante:,} filas no-CRC** sin `MONTO_ADJU_LINEA_CRC` numérico "
                 "(no hay conversión a colones para ellas). Ejemplos: "
                 + "; ".join(f"`{a}` L{b} ({c})" for a, b, c in ejemplos_crc_faltante))
        L.append("")
    for moeda, lista in (("USD", tasas["USD"]), ("EUR", tasas["EUR"])):
        if lista:
            lista.sort()
            n = len(lista)
            med = lista[n // 2] if n % 2 else (lista[n // 2 - 1] + lista[n // 2]) / 2
            L.append(f"Tasas implícitas CRC/{moeda}: n={n:,} · min={lista[0]:.2f} · "
                     f"mediana={med:.2f} · max={lista[-1]:.2f}")
    L.append("")
    L.append("> Las tasas implícitas se reportan como contexto; no se contrastan contra un "
             "tipo de cambio oficial (no es posible sin una fuente externa).")

    L.append("")
    L.append("---")
    L.append("")
    L.append("**Método:** verificación sobre `adjudicaciones_2026.csv` (una fila por línea "
             "adjudicada) y sobre los zips mensuales de `_cache/`. Cualquier diferencia con "
             "la fuente se reporta tal cual; no se ajustan datos.")

    shutil.rmtree(tmpdir, ignore_errors=True)
    (SALIDA / "VERIFICACIONES.md").write_text("\n".join(L), encoding="utf-8")
    print(f"VERIFICACIONES.md escrito en {SALIDA.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
