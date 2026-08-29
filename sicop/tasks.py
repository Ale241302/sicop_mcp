import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="sicop.load_file")
def load_file(self, model_name, path, force=False):
    """Carga un CSV individual. Una tarea por archivo."""
    from .loader import load_csv

    try:
        return load_csv(model_name, path, force=force)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo cargando %s", path)
        raise self.retry(exc=exc, countdown=30, max_retries=3)


@shared_task(bind=True, name="sicop.load_all")
def load_all(self, force=False, only=None, gold=True, core=True):
    """Encola una tarea por archivo."""
    from django.conf import settings

    from .loader import CORE_SETS, GOLD_SETS, discover_files

    data_dir = settings.SICOP_DATA_DIR
    jobs = discover_files(data_dir)

    if only:
        jobs = [j for j in jobs if j[0].lower() == only.lower() or j[1].lower().endswith(only.lower())]
    if not core:
        jobs = [j for j in jobs if j[0].startswith("Gold")]
    if not gold:
        jobs = [j for j in jobs if not j[0].startswith("Gold")]

    queued = []
    for model, path in jobs:
        load_file.delay(model, path, force)
        queued.append(path)
    return {"queued": len(queued), "files": queued}


@shared_task(bind=True, name="sicop.ciclo_diario")
def ciclo_diario(self, corrida=None):
    """El ciclo de las 06:00: vigilancia + consolidar + senales + cola + gold."""
    from .ciclo import ciclo_diario as run

    return run(corrida=corrida, reprocesar=True, gold=True)


@shared_task(bind=True, name="sicop.vigilancia_reescritura")
def vigilancia_reescritura(self, corrida=None):
    """Vigilancia de reescritura (3 cerrados + 2 rotativos)."""
    from .vigilancia import revisar_reescritura

    return revisar_reescritura(corrida=corrida or "vig-{date}")


@shared_task(bind=True, name="sicop.consolidar_resultados")
def consolidar_resultados(self, corrida=None):
    from .resultado import consolidar_resultados

    return consolidar_resultados(corrida)


@shared_task(bind=True, name="sicop.reparar_mes")
def reparar_mes(self, aaaamm, corrida=None):
    """REPARA un mes: re-extrae el anio desde la fuente, recarga, broncea el mes,
    reconstruye silver + gold y corre el gate. Para llenar huecos / datos vacios.

    Lock global (Redis): las reparaciones se serializan porque el extractor
    escribe el mismo anio en el mismo directorio y silver/gold son globales."""
    import os
    import subprocess
    import sys
    import time
    from datetime import datetime

    from django.conf import settings
    from django.core.cache import cache

    from sicop import bronze, control, loader, silver
    from sicop.derivadas import run as run_derivadas

    corrida = corrida or f"reparar-{aaaamm}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    # lock global: esperar hasta ~30 min a que termine otra reparacion
    LOCK = "sicop:reparar_mes_lock"
    if not cache.add(LOCK, corrida, timeout=5400):
        for _ in range(120):
            time.sleep(15)
            if cache.add(LOCK, corrida, timeout=5400):
                break
        else:
            return {"corrida": corrida, "estado": "ERROR", "motivo": "lock ocupado 30 min"}
    try:
        control.registrar_corrida(corrida, "reparar_mes", notas=f"reparar {aaaamm}")
        y = aaaamm[:4]
        extractor = os.path.join(settings.SICOP_SCRIPTS_DIR, "harness_actualizado", "sicop_loop.py")
        out = settings.SICOP_RECOVERY_DIR

        rc = subprocess.run([sys.executable, extractor, "--year", y, "--pesados", "--force",
                             "--no-vigilancia", "--out", out], cwd=os.path.dirname(extractor)).returncode
        if rc != 0:
            control.cerrar_corrida(corrida, "BLOQUEADO", notas=f"extractor rc={rc}")
            return {"corrida": corrida, "estado": "ERROR", "extractor_rc": rc}

        loader.recargar_anio_afectado(out, settings.SICOP_DATA_DIR, y, corrida=corrida)
        for setn in bronze.BRONZE_SETS:
            p = os.path.join(out, f"{setn}_{y}.csv")
            if os.path.exists(p) and os.path.getsize(p) > 1000:
                bronze.construir(setn, p, corrida, meses={aaaamm})
        silver.build_all(corrida)
        run_derivadas(None)
        ok, failed = control.run_tests(corrida)
        control.cerrar_corrida(corrida, "PUBLICADO" if not failed else "BLOQUEADO",
                               notas=f"tests={len(ok)} PASS / {len(failed)} FAIL")
        return {"corrida": corrida, "estado": "PUBLICADO" if not failed else "BLOQUEADO", "tests_fail": len(failed)}
    finally:
        cache.delete(LOCK)
