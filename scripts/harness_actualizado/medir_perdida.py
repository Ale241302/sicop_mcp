# -*- coding: utf-8 -*-
"""Mide la perdida real del dedupe sin NUMERO_PARTIDA (hallazgo GPT-5 Codex).
Lee los ZIP crudos y cuenta cuantas (NRO_SICOP, NUMERO_LINEA) tienen >1 partida."""
import zipfile, csv, io, sys, glob, os
from collections import defaultdict, Counter
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10**9)

CACHE = r"C:\DeepSeek Harness\salida\_cache"
SALIDA = r"C:\DeepSeek Harness\salida"

def leer_miembro(z, nombre):
    for m in z.namelist():
        if m.lower().endswith(nombre.lower()):
            raw = z.read(m)
            for enc in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
                try:
                    return raw.decode(enc)
                except Exception:
                    continue
    return None

def main():
    zips = sorted(glob.glob(os.path.join(CACHE, "*.zip")))
    print(f"zips en cache: {len(zips)}\n")

    partidas_por_linea = defaultdict(set)
    filas_crudas = 0
    zips_leidos = 0

    for zp in zips:
        try:
            with zipfile.ZipFile(zp) as z:
                txt = leer_miembro(z, "DetalleLineaCartel.csv")
                if not txt:
                    continue
                zips_leidos += 1
                # el delimitador de la fuente es ';' salvo SancionProveedores
                dialecto = ";" if txt.count(";") > txt.count(",") else ","
                r = csv.DictReader(io.StringIO(txt), delimiter=dialecto)
                for row in r:
                    filas_crudas += 1
                    s = (row.get("NRO_SICOP") or "").strip()
                    l = (row.get("NUMERO_LINEA") or "").strip()
                    p = (row.get("NUMERO_PARTIDA") or "").strip()
                    if s and l:
                        partidas_por_linea[(s, l)].add(p)
        except Exception as e:
            print(f"[skip] {os.path.basename(zp)}: {e}")

    print(f"zips con DetalleLineaCartel leidos : {zips_leidos}")
    print(f"filas crudas leidas                : {filas_crudas:,}")
    print(f"(NRO_SICOP, NUMERO_LINEA) distintos: {len(partidas_por_linea):,}")

    dist = Counter(len(v) for v in partidas_por_linea.values())
    multi = sum(c for k, c in dist.items() if k > 1)
    filas_perdidas = sum((k - 1) * c for k, c in dist.items() if k > 1)

    print(f"\ndistribucion de partidas por (sicop, linea):")
    for k in sorted(dist):
        print(f"   {k} partida(s): {dist[k]:,} claves")

    print(f"\nclaves con MAS de una partida : {multi:,} "
          f"({100.0*multi/max(len(partidas_por_linea),1):.2f}%)")
    print(f"FILAS QUE EL DEDUPE DESCARTA  : {filas_perdidas:,} "
          f"({100.0*filas_perdidas/max(filas_crudas,1):.2f}% de las crudas)")

    # contraste contra el CSV extraido
    tot_csv = 0
    for p in sorted(glob.glob(os.path.join(SALIDA, "lineas_cartel_*.csv"))):
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            tot_csv += sum(1 for _ in f) - 1
    print(f"\nfilas en lineas_cartel_*.csv extraidos: {tot_csv:,}")
    print(f"diferencia contra claves distintas    : {tot_csv - len(partidas_por_linea):,}")

    if filas_perdidas:
        print("\nejemplos de claves con multiples partidas:")
        n = 0
        for k, v in partidas_por_linea.items():
            if len(v) > 1:
                print(f"   NRO_SICOP={k[0]} LINEA={k[1]} -> partidas {sorted(v)}")
                n += 1
                if n >= 5:
                    break

if __name__ == "__main__":
    main()
