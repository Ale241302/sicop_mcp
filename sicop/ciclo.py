"""Ciclo diario (plan FASE 2.4.2): 06:00 descarga+delta+senales+cola, gold y gates.

Pasos: vigilar reescritura -> resolver PENDIENTES de resultado -> senales ->
cola priorizada -> gold (recalcular derivadas + tests como gate). El reproceso
del mes cambiado se delega al extractor (sicop_loop) con --months.
"""
import logging
import os
import subprocess
import sys
from datetime import datetime

from django.utils import timezone

from . import control, resultado, senales, vigilancia
from .models import Senal, CtlCorrida

logger = logging.getLogger(__name__)


def _corrida_id(prefix="diario"):
    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        print(f"  subprocess ERROR {r.returncode}: {' '.join(cmd)}", flush=True)
    return r.returncode


def _cola_priorizada(corrida, max_n=20):
    orden = {"alta": 0, "media": 1, "baja": 2}
    q = list(Senal.objects.filter(corrida=corrida, estado="DETECTADA")
             .order_by("prioridad", "-fecha")[:max_n])
    print(f"cola priorizada: {len(q)} senales", flush=True)
    return q


def ciclo_diario(corrida=None, reprocesar=True, gold=True):
    """Un dia del ciclo. Devuelve el resumen."""
    from django.conf import settings
    from sicop.derivadas import run as run_derivadas

    corrida = corrida or _corrida_id()
    control.registrar_corrida(corrida, "ciclo_diario", notas="FASE 2")
    print(f"== ciclo diario {corrida} ==", flush=True)

    # 0) TC del dia: consultar UNA vez, guardar en ctl_bccr_tc (el resto del
    #    dia el MCP/API leen de ahi, sin volver a la API del BCCR)
    print("-- tipo de cambio del dia --", flush=True)
    try:
        from sicop import bccr
        bccr.guardar_tc_del_dia(corrida=corrida)
    except Exception as e:  # noqa: BLE001
        print(f"  bccr fallo (no bloquea el ciclo): {e}", flush=True)

    # 1) vigilancia de reescritura (mes en curso + 3 cerrados + 2 rotativos)
    print("-- vigilancia reescritura --", flush=True)
    cambios = vigilancia.revisar_reescritura(corrida=corrida)
    recargados = []
    if cambios and reprocesar:
        from sicop import loader, silver

        extractor = os.path.join(settings.SICOP_SCRIPTS_DIR, "harness_actualizado", "sicop_loop.py")
        out = settings.SICOP_RECOVERY_DIR
        for m in cambios:
            senales._emit(corrida, "cambio_hash_fuente", "alta", "", None,
                          f"la fuente reescribio {m}", "reprocesar el mes", m)
            # anio completo, con --pesados (invitaciones + ordenes_pedido) y --force
            # (reconstruye el archivo del anio en fresco: captura filas nuevas Y
            # modificadas/eliminadas; el _cache del extractor solo re-descarga el
            # mes que cambio).
            _run([sys.executable, extractor, "--year", m[:4], "--pesados", "--force",
                  "--no-vigilancia", "--out", out], cwd=os.path.dirname(extractor))
        # recargar a Postgres el/los anio(s) afectado(s) y reconstruir silver
        for y in sorted({m[:4] for m in cambios}):
            try:
                r = loader.recargar_anio_afectado(out, settings.SICOP_DATA_DIR, y, corrida=corrida)
                recargados.append(r)
            except Exception as e:  # noqa: BLE001
                print(f"  recarga anio {y} fallo (no bloquea el ciclo): {e}", flush=True)
        if any(r.get("copiados") for r in recargados):
            print("-- silver (reconstruir hechos) --", flush=True)
            try:
                silver.build_all(corrida)
            except Exception as e:  # noqa: BLE001
                print(f"  silver fallo (no bloquea el ciclo): {e}", flush=True)

    # 2) consolidar PENDIENTES de resultado_decision
    print("-- consolidar resultados --", flush=True)
    resultado.consolidar_resultados(corrida)

    # 3) senales del dia
    print("-- senales --", flush=True)
    n = senales.generar_senales(corrida)

    # 4) cola priorizada
    _cola_priorizada(corrida)

    # 5) gold + gates
    if gold:
        print("-- gold + gates --", flush=True)
        run_derivadas(None)
        ok, failed = control.run_tests(corrida)
        control.cerrar_corrida(corrida, "PUBLICADO" if not failed else "BLOQUEADO",
                               notas=f"senales={n}; tests={len(failed)} fallidos")
    else:
        control.cerrar_corrida(corrida, "OK", notas=f"senales={n}")
    print(f"== fin ciclo {corrida} ==", flush=True)
    return {"corrida": corrida, "senales": n, "cambios": cambios}
