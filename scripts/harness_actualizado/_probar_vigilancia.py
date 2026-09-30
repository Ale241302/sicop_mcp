# -*- coding: utf-8 -*-
"""Prueba en seco de la vigilancia de reescritura (fix 2026-08-25).
No modifica nada: solo verifica que el HEAD remoto devuelva validadores."""
import sys, importlib.util, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

spec = importlib.util.spec_from_file_location(
    "sl", r"C:\DeepSeek Harness\scripts\sicop_loop.py")
sl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sl)

print("=" * 70)
print("1) HEAD remoto — la fuente expone validadores?")
print("=" * 70)
for mes in ("202608", "202401", "202001", "209912"):
    h = sl.head_remoto(sl.BASE_URL.format(AAAAMM=mes))
    print(f"  {mes}: {json.dumps(h, ensure_ascii=False)}")

print("\n" + "=" * 70)
print("2) Manifiesto: cuantos meses tienen sha256 y validadores?")
print("=" * 70)
man = json.load(open(r"C:\DeepSeek Harness\salida\manifiesto.json",
                     encoding="utf-8"))
meses = man.get("meses", man)
con_hash = sum(1 for v in meses.values()
               if isinstance(v, dict) and v.get("sha256"))
con_val = sum(1 for v in meses.values()
              if isinstance(v, dict) and v.get("validadores"))
ok = sum(1 for v in meses.values()
         if isinstance(v, dict) and v.get("estado") == "OK")
print(f"  meses registrados : {len(meses)}")
print(f"  en estado OK      : {ok}")
print(f"  con sha256        : {con_hash}")
print(f"  con validadores   : {con_val}   <- 0 es esperado antes del primer run")

print("\n" + "=" * 70)
print("3) Que meses vigilaria hoy?")
print("=" * 70)
import time
hoy = time.localtime()
actual = f"{hoy.tm_year}{hoy.tm_mon:02d}"
cerrados = sorted(m for m, v in meses.items()
                  if isinstance(v, dict) and v.get("estado") == "OK"
                  and m < actual)
vig = {actual} | set(cerrados[-2:])
resto = cerrados[:-2] or cerrados
base = (hoy.tm_mday - 1) * 2
for i in range(2):
    if resto:
        vig.add(resto[(base + i) % len(resto)])
print(f"  hoy ({actual}, dia {hoy.tm_mday}): {sorted(vig)}")
print(f"  historicos disponibles para rotacion: {len(resto)}")
print(f"  cobertura completa en ~{(len(resto) + 1) // 2} dias")
