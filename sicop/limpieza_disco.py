"""Limpieza de disco de archivos intermedios (FASE operativa 2026-09-02).

El flujo de datos del extractor es: ZIP (descargado a recuperacion/_cache) ->
CSV extraidos (recuperacion/) -> CSV finales (salidas/) -> PostgreSQL -> gold ->
pgvector -> grafo. Solo los CSV de `salidas` alimentan la base; los de
`recuperacion` son intermedios que quedan duplicados (byte-identicos) una vez
que el loader ya copio el CSV a salidas.

Politica de retencion (conservadora):
  - NUNCA borra CSVs de `salidas` (son la fuente canonica de recarga).
  - NUNCA borra los ZIPs de los ultimos 24 meses en _cache (la fuente reescribe
    meses recientes; el ZIP en cache permite re-detectar y re-procesar).
  - Borra CSVs de `recuperacion/` que sean byte-identicos a su par en `salidas/`
    Y cuyo anio sea <= corte (default: ultimos 12 meses se conservan).
  - Borra ZIPs de `_cache/` con mes <= corte_zips (default 24 meses).
  - Deja log en corrida_paso (via control) y en ctl_corrida.

Siempre dry_run=True por defecto; dry_run=False borra de verdad.
"""
import hashlib
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

RECOVERY = "/data/recuperacion"
SALIDAS = "/data/salidas"
CACHE_ZIPS = os.path.join(RECOVERY, "_cache")

# meses (AAAAMM) recientes que se conservan SIEMPRE aunque haya duplicados:
# permiten re-procesar sin re-descargar si la fuente reescribe el mes.
MESES_KEEP_CSV = 12
MESES_KEEP_ZIP = 24


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _anio_mes(archivo):
    """Extrae el AAAAMM o AAAA del nombre {set}_{AAAAMM}.csv, {set}_{AAAA}.csv
    o {AAAAMM}.zip. Devuelve int (ej 2020, 202501) o None."""
    base = archivo[:-4]
    m = base.split("_")[-1]
    if len(m) == 6 and m.isdigit() and m.startswith("20"):
        return int(m)
    if len(m) == 4 and m.isdigit() and m.startswith("20"):
        return int(m) * 100  # 2020 -> 202000 (anio como base de comparacion)
    return None


def _mes_int(archivo):
    m = _anio_mes(archivo)
    return m if m else None


def _hoy_mes():
    hoy = datetime.now()
    return hoy.year * 100 + hoy.month


def _plan_csv_duplicados():
    """CSV de recuperacion byte-identicos a salidas, con mes <= corte. Devuelve
    lista de (path_a_borrar, set_nombre, mes, bytes)."""
    hoy = _hoy_mes()
    corte = hoy - MESES_KEEP_CSV
    plan = []
    if not os.path.isdir(RECOVERY):
        return plan
    for fn in sorted(os.listdir(RECOVERY)):
        if not fn.endswith(".csv") or fn.startswith("_"):
            continue
        src = os.path.join(RECOVERY, fn)
        dst = os.path.join(SALIDAS, fn)
        if not os.path.exists(dst):
            continue
        mes = _mes_int(fn)
        if mes is None or mes > corte:
            continue  # conservar recientes
        try:
            if os.path.getsize(src) == os.path.getsize(dst) and \
                    _sha256(src) == _sha256(dst):
                plan.append({"path": src, "archivo": fn, "mes": str(mes),
                             "bytes": os.path.getsize(src)})
        except OSError:
            continue
    return plan


def _plan_zips_viejos():
    """ZIPs de _cache con mes <= corte. Devuelve lista de paths."""
    hoy = _hoy_mes()
    corte = hoy - MESES_KEEP_ZIP
    plan = []
    if not os.path.isdir(CACHE_ZIPS):
        return plan
    for fn in sorted(os.listdir(CACHE_ZIPS)):
        if not fn.endswith(".zip"):
            continue
        mes = _mes_int(fn)
        if mes is None or mes > corte:
            continue
        p = os.path.join(CACHE_ZIPS, fn)
        plan.append({"path": p, "archivo": fn, "mes": str(mes),
                     "bytes": os.path.getsize(p)})
    return plan


def _cuarentenas():
    """Vaciar carpetas _cuarentena (archivos descartados por el extractor)."""
    limpiables = []
    for base in (RECOVERY, SALIDAS):
        q = os.path.join(base, "_cuarentena")
        if os.path.isdir(q):
            total = sum(os.path.getsize(os.path.join(q, f)) for f in os.listdir(q))
            limpiables.append({"path": q, "archivo": "_cuarentena",
                               "bytes": total})
    return limpiables


def ejecutar_limpieza(corrida, dry_run=True):
    """Ejecuta (o simula) la limpieza de intermedios duplicados. Devuelve resumen
    con lo que se borraria/borro. Usa corrida_paso + ctl_corrida para el log."""
    from sicop import control

    csvs = _plan_csv_duplicados()
    zips = _plan_zips_viejos()
    cuar = _cuarentenas()

    total_bytes = sum(c["bytes"] for c in csvs) + \
        sum(z["bytes"] for z in zips) + sum(q["bytes"] for q in cuar)
    resumen = {
        "corrida": corrida, "dry_run": dry_run,
        "csv_duplicados": len(csvs), "csv_duplicados_bytes": sum(c["bytes"] for c in csvs),
        "csv_duplicados_meses": sorted({c["mes"] for c in csvs}),
        "zips_viejos": len(zips), "zips_viejos_bytes": sum(z["bytes"] for z in zips),
        "zips_viejos_meses": sorted({z["mes"] for z in zips}),
        "cuarentenas_borradas_bytes": sum(q["bytes"] for q in cuar),
        "total_bytes_liberables": total_bytes,
    }

    if not dry_run:
        borrados = 0
        for c in csvs:
            try:
                os.remove(c["path"]); borrados += 1
            except OSError as e:
                resumen.setdefault("errores", []).append(f"{c['archivo']}: {e}")
        for z in zips:
            try:
                os.remove(z["path"]); borrados += 1
            except OSError as e:
                resumen.setdefault("errores", []).append(f"{z['archivo']}: {e}")
        for q in cuar:
            for f in os.listdir(q["path"]):
                try:
                    os.remove(os.path.join(q["path"], f))
                except OSError:
                    pass
        resumen["borrados"] = borrados

    gb = total_bytes / (1024 ** 3)
    detalle = (f"dry-run: " if dry_run else "ejecutado: ") + \
        f"{resumen['csv_duplicados']} CSV duplicados, " \
        f"{resumen['zips_viejos']} ZIPs viejos, " \
        f"{gb:.2f} GB liberables"
    control.cerrar_corrida(corrida, "OK", notas=detalle)
    resumen["estado"] = "DRY_RUN_OK" if dry_run else "COMPLETADO"
    return resumen


if __name__ == "__main__":
    import json
    import sys

    dry = "--ejecutar" not in sys.argv
    corrida = f"limpieza-disco-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    print(json.dumps(ejecutar_limpieza(corrida, dry_run=dry),
                     ensure_ascii=False, default=str, indent=2))
