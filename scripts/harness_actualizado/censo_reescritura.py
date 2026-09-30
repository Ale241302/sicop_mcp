# -*- coding: utf-8 -*-
"""Censo de reescritura: HEAD a los 84 meses y comparar Last-Modified contra
la fecha en que el mes deberia haber cerrado. Responde la pregunta que el
sistema no podia contestar: cuantos meses cerrados reescribio la fuente?"""
import sys, importlib.util, json, time
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

spec = importlib.util.spec_from_file_location(
    "sl", r"C:\DeepSeek Harness\scripts\sicop_loop.py")
sl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sl)

man = json.load(open(r"C:\DeepSeek Harness\salida\manifiesto.json",
                     encoding="utf-8"))
meses = man.get("meses", man)

def fin_de_mes(aaaamm):
    a, m = int(aaaamm[:4]), int(aaaamm[4:])
    if m == 12:
        return datetime(a + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(a, m + 1, 1, tzinfo=timezone.utc)

filas = []
print("consultando 84 meses…\n")
for mes in sorted(meses):
    h = sl.head_remoto(sl.BASE_URL.format(AAAAMM=mes))
    if not h or h.get("not_found"):
        continue
    lm = h.get("last_modified")
    if not lm:
        continue
    try:
        dt = datetime.strptime(lm, "%a, %d %b %Y %H:%M:%S %Z").replace(
            tzinfo=timezone.utc)
    except Exception:
        continue
    cierre = fin_de_mes(mes)
    dias = (dt - cierre).days
    filas.append((mes, dt, dias, int(h.get("content_length") or 0),
                  meses[mes].get("tamano_bytes", 0)))
    time.sleep(0.05)

print("=" * 88)
print("CENSO DE REESCRITURA — Last-Modified vs cierre natural del mes")
print("=" * 88)
print(f"{'mes':>7} {'last_modified':>20} {'dias tras cierre':>17} "
      f"{'bytes remoto':>14} {'bytes local':>13}")
print("-" * 88)
tocados = 0
discrepa = 0
for mes, dt, dias, remoto, local in filas:
    marca = ""
    if dias > 60:
        marca = "  <-- REESCRITO"
        tocados += 1
    if local and remoto and remoto != local:
        marca += " *TAMANO DIFIERE*"
        discrepa += 1
    print(f"{mes:>7} {dt.strftime('%Y-%m-%d %H:%M'):>20} {dias:>17,} "
          f"{remoto:>14,} {local:>13,}{marca}")

print("-" * 88)
print(f"meses consultados                    : {len(filas)}")
print(f"modificados >60 dias tras su cierre  : {tocados}")
print(f"con tamano remoto != local           : {discrepa}   <-- reproceso urgente")
print("\nLECTURA: 'dias tras cierre' alto no prueba cambio de contenido — puede ser")
print("una migracion de almacenamiento. El tamano distinto SI es cambio real.")
