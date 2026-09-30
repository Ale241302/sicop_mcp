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
    """El ciclo de las 00:00 CR (dom-vie): vigilancia + consolidar + senales + cola + gold."""
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
def reparar_mes(self, aaaamm, corrida=None, reextraer=False):
    """REPARA un mes: carga el anio desde la extraccion ya presente (mode liviano),
    recarga Postgres, broncea el mes, reconstruye silver + gold y corre el gate.
    Con reextraer=True fuerza re-descarga completa del anio desde la fuente.

    Modo liviano (reextraer=False, por defecto): el extractor corre SIN --force,
    asi que salta los meses ya en OK del manifiesto (no re-descarga, no re-extrae;
    las reescrituras reales de la fuente las detecta el ciclo diario). La recarga
    es no-op si el hash no cambio. El repair queda en bronze(month)+silver+gold,
    sin el pico de ~200GB de disco del re-extraido.

    Lock global (Redis): las reparaciones se serializan porque el extractor
    escribe el mismo anio en el mismo directorio y silver/gold son globales."""
    import os
    import subprocess
    import sys
    import time
    from datetime import datetime

    from django.conf import settings
    from django.core.cache import cache

    from sicop import bronze, control, loader, sellos, silver
    from sicop.derivadas import run as run_derivadas

    corrida = corrida or f"reparar-{aaaamm}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    # Lock global (Redis) para serializar reparaciones (el extractor escribe el
    # mismo anio y silver/gold son globales). TTL CORTO + heartbeat que lo renueva
    # cada 60s: si el worker muere, el lock vence solo en <=3 min en vez de quedar
    # 90 min bloqueando toda reparacion (bug que dejo una corrida colgada).
    import threading

    LOCK = "sicop:reparar_mes_lock"
    LOCK_TTL = 180
    if not cache.add(LOCK, corrida, timeout=LOCK_TTL):
        for _ in range(120):
            time.sleep(15)
            if cache.add(LOCK, corrida, timeout=LOCK_TTL):
                break
        else:
            return {"corrida": corrida, "estado": "ERROR", "motivo": "lock ocupado 30 min"}

    stop_hb = threading.Event()

    def _latido():
        while not stop_hb.wait(60):
            try:
                cache.set(LOCK, corrida, timeout=LOCK_TTL)
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=_latido, daemon=True).start()
    try:
        control.registrar_corrida(corrida, "reparar_mes", notas=f"reparar {aaaamm}")
        y = aaaamm[:4]
        extractor = os.path.join(settings.SICOP_SCRIPTS_DIR, "harness_actualizado", "sicop_loop.py")
        out = settings.SICOP_RECOVERY_DIR

        # sembrar la base COMPLETA del anio en recuperacion: si no, el extractor
        # opera sobre una copia parcial y el mes re-extraido no llega a silver.
        sello = sellos.sellar(corrida)
        sembrados = loader.sembrar_recuperacion(out, settings.SICOP_DATA_DIR, y)
        if sembrados:
            print(f"  sembrados {len(sembrados)} CSV anuales en recuperacion", flush=True)
        rc = subprocess.run([sys.executable, extractor, "--year", y, "--pesados",
                             "--no-vigilancia", "--out", out,
                             "--base", settings.SICOP_DATA_DIR]
                            + (["--force"] if reextraer else []),
                            cwd=os.path.dirname(extractor)).returncode
        if rc != 0:
            control.cerrar_corrida(corrida, "BLOQUEADO", notas=f"extractor rc={rc}")
            return {"corrida": corrida, "estado": "ERROR", "extractor_rc": rc}

        # skill §12.5: si codigo/config cambio a mitad de la reparacion, la mezcla
        # se rechaza (no se recarga a Salidas).
        diffs = sellos.comparar(sello, sellos.sello_actual())
        if diffs:
            control.cerrar_corrida(corrida, "BLOQUEADO",
                                   notas=f"sello roto: {diffs[:3]}")
            return {"corrida": corrida, "estado": "ERROR", "sello_roto": diffs}

        loader.recargar_anio_afectado(out, settings.SICOP_DATA_DIR, y, corrida=corrida,
                                      sello_esperado=sello)
        control.registrar_cuarentena_desde_archivo(corrida, os.path.join(out, "_cuarentena"))
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
        stop_hb.set()
        cache.delete(LOCK)


@shared_task(bind=True, name="sicop.sync_capas")
def sync_capas(self, corrida=None):
    """FASE C/D/E: sincroniza las capas derivadas (dim_entidad, embeddings, grafo,
    gold_invitaciones) DESPUES del gold+gate del ciclo diario. Idempotente e
    incremental. Se dispara desde celery-beat (00:20 CR, dom-vie) y tambien se corre
    dentro de sicop.ciclo_diario tras el gate (ver ciclo.py)."""
    from sicop.sync_capas import sync_capas as run

    return run(corrida=corrida)


@shared_task(bind=True, name="sicop.retencion_anual")
def retencion_anual(self, anio=None, dry_run=True):
    """FASE R: borrado anual por retencion movil (7 anos). El 1-ene-2027 borra
    2020 (y el rezago 201912) de la base + grafo. Si dry_run (default) solo
    cuenta y registra en ctl_retencion sin borrar. Con dry_run=False ejecuta:
    backup pg_dump -> DELETE por anio en core/gold/bronce/emb_doc/grafo ->
    re-corre el gate de tests. Nunca borra sin backup previo."""
    from sicop.control import cerrar_corrida, registrar_corrida
    from datetime import datetime

    hoy = datetime.now()
    # el beat corre el 1-ene 04:30: ese dia el anio mas viejo es (anio_actual - 7).
    # Si se invoca a mano en otra fecha, usa el anio del proximo/actual 1-ene.
    if hoy.month == 1:
        anio_1ene = hoy.year
    else:
        anio_1ene = hoy.year + 1
    anio_objetivo = anio or (anio_1ene - 7)  # ventana movil de 7 anos
    corrida = f"retencion-{anio_objetivo}-{hoy.strftime('%Y%m%d-%H%M%S')}"
    registrar_corrida(corrida, "retencion_anual",
                      notas=f"anio={anio_objetivo} dry_run={dry_run}")
    from sicop.retencion import ejecutar_retencion

    return ejecutar_retencion(corrida, anio_objetivo, dry_run=dry_run)


@shared_task(bind=True, name="sicop.limpieza_disco")
def limpieza_disco(self, dry_run=True):
    """Operativa: borra archivos intermedios duplicados para liberar disco.
    NUNCA toca CSVs de salidas (fuente canonica de Postgres) ni ZIPs recientes
    (la fuente reescribe meses). Dry-run por defecto: cuenta y loguea sin borrar.
    Con dry_run=False borra CSVs de recuperacion byte-identicos a salidas
    (>12 meses) y ZIPs de _cache (>24 meses), y vacia _cuarentena."""
    from datetime import datetime

    from sicop.control import cerrar_corrida, registrar_corrida

    corrida = f"limpieza-disco-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    registrar_corrida(corrida, "limpieza_disco", notas=f"dry_run={dry_run}")
    from sicop.limpieza_disco import ejecutar_limpieza

    return ejecutar_limpieza(corrida, dry_run=dry_run)
