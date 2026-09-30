# -*- coding: utf-8 -*-
"""Verificacion independiente del gradiente r vs N (enjambre Kimi, corrida 1)."""
import csv, sys, glob, os, statistics as st
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10**9)
B = r"C:\DeepSeek Harness\salida"

def key(sicop, lin):
    s = str(lin or "").strip()
    if not s: return None
    try: s = str(int(float(s)))
    except Exception: s = s.lstrip("0") or "0"
    return (str(sicop or "").strip(), s)

def f(x):
    try: return float(x)
    except Exception: return None

def a_crc(precio, moneda, tc):
    m = (moneda or "CRC").strip().upper()
    if m == "CRC": return precio
    if tc and tc > 0: return precio * tc
    return None

est = {}
fam = {}
for p in sorted(glob.glob(os.path.join(B, "lineas_cartel_*.csv"))):
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            k = key(row.get("NRO_SICOP"), row.get("NUMERO_LINEA"))
            if not k: continue
            v = f(row.get("PRECIO_UNITARIO_ESTIMADO"))
            if not v or v <= 0: continue
            v = a_crc(v, row.get("TIPO_MONEDA"), f(row.get("TIPO_CAMBIO_CRC")))
            if not v or v <= 0: continue
            est[k] = v
            cod = (row.get("CODIGO_IDENTIFICACION") or "").strip()
            if len(cod) >= 6: fam[k] = cod[:6]

ofertas = defaultdict(list)
for p in sorted(glob.glob(os.path.join(B, "lineas_ofertadas_*.csv"))):
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            k = key(row.get("NRO_SICOP"), row.get("NRO_LINEA"))
            if not k or k not in est: continue
            v = f(row.get("PRECIO_UNITARIO_OFERTADO"))
            if not v or v <= 0: continue
            v = a_crc(v, row.get("TIPO_MONEDA"), f(row.get("TIPO_CAMBIO_CRC")))
            if not v or v <= 0: continue
            ofertas[k].append((row.get("NRO_OFERTA"), v))

print(f"lineas de cartel con estimado valido : {len(est):,}")
print(f"lineas con al menos una oferta       : {len(ofertas):,} "
      f"({100.0*len(ofertas)/max(len(est),1):.1f}% match)")

por_n = defaultdict(list)
por_n_foco = defaultdict(list)
descartadas = 0
for k, lst in ofertas.items():
    e = est[k]
    n = len(set(o for o, _ in lst))
    for _, precio in lst:
        r = precio / e
        if r < 0.05 or r > 20:
            descartadas += 1
            continue
        por_n[n].append(r)
        if fam.get(k) == "461816":
            por_n_foco[n].append(r)

print(f"observaciones descartadas por r fuera de [0,05; 20]: {descartadas:,}")

def tabla(d, titulo, minimo=30):
    print(f"\n{titulo}")
    print(f"{'N':>4} {'n_obs':>10} {'r_mediano':>10} {'r_media':>9} {'p25':>7} {'p75':>7}")
    print("-" * 52)
    for n in sorted(d):
        v = d[n]
        if len(v) < minimo: continue
        v_s = sorted(v)
        q = lambda p: v_s[min(int(p*len(v_s)), len(v_s)-1)]
        print(f"{n:>4} {len(v):>10,} {st.median(v):>10.3f} "
              f"{st.mean(v):>9.3f} {q(0.25):>7.3f} {q(0.75):>7.3f}")

tabla(por_n, "TODAS LAS FAMILIAS - r por numero de oferentes (celdas con n>=30)")
tabla(por_n_foco, "FAMILIA 461816 (calzado seguridad) - celdas con n>=30")

print("\nDETALLE N=1..10 (todas las familias), sin filtro de tamano:")
for n in range(1, 11):
    v = por_n.get(n, [])
    if v:
        print(f"   N={n}: n_obs={len(v):>9,}  mediana={st.median(v):.3f}")
    else:
        print(f"   N={n}: sin datos")
