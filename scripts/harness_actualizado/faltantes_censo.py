# -*- coding: utf-8 -*-
"""Que meses no contestaron el HEAD en el censo, y en que estado estan."""
import sys, json, importlib.util
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
spec = importlib.util.spec_from_file_location(
    "sl", r"C:\DeepSeek Harness\scripts\sicop_loop.py")
sl = importlib.util.module_from_spec(spec); spec.loader.exec_module(sl)

man = json.load(open(r"C:\DeepSeek Harness\salida\manifiesto.json", encoding="utf-8"))
meses = man.get("meses", man)
print(f"meses en manifiesto: {len(meses)}")
for mes in sorted(meses):
    h = sl.head_remoto(sl.BASE_URL.format(AAAAMM=mes))
    if h and h.get("last_modified"):
        continue
    est = meses[mes].get("estado")
    print(f"{mes}  estado={est!r}  head={h!r}")
