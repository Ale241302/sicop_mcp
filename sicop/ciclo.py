"""Ciclo diario (plan FASE 2.4.2): 06:00 descarga+delta+senales+cola, gold y gates.

Pasos: TC del dia -> vigilar reescritura -> (extractor + recarga + silver si hubo
cambios) -> consolidar PENDIENTES -> senales -> cola -> gold (derivadas) -> tests.

Cada paso se registra en corrida_paso (estado, detalle, filas, duracion) para
auditar y afinar: todo queda trazado, no solo en stdout.
"""
import logging
import os
import subprocess
import sys
import time
from datetime import datetime

from django.utils import timezone

from . import control, resultado, senales, vigilancia
from .models import CorridaPaso, Senal

logger = logging.getLogger(__name__)


def _corrida_id(prefix="diario"):
    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _registrar_paso(corrida, paso, estado, detalle, filas=None, duracion_ms=None):
    """Registra un paso del pipeline en corrida_paso (append-only)."""
    try:
        CorridaPaso.objects.create(
            corrida=corrida, paso=paso, estado=estado,
            detalle=str(detalle)[:3000], filas=filas, duracion_ms=duracion_ms,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("no pude registrar paso %s: %s", paso, e)


def _paso(corrida, paso, fn, detalle_ok=None, detalle_err=None):
    """Ejecuta fn, mide duracion y registra el paso OK/ERROR."""
    t0 = time.time()
    try:
        res = fn()
        ms = int((time.time() - t0) * 1000)
        _registrar_paso(corrida, paso, "OK",
                        detalle_ok(res) if detalle_ok else res,
                        duracion_ms=ms)
        return res
    except Exception as e:  # noqa: BLE001
        ms = int((time.time() - t0) * 1000)
        _registrar_paso(corrida, paso, "ERROR",
                        detalle_err(e) if detalle_err else str(e),
                        duracion_ms=ms)
        print(f"  paso {paso} ERROR (no bloquea el ciclo): {e}", flush=True)
        return None


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

    # 0) TC del dia: consultar UNA vez, guardar en ctl_bccr_tc
    def _tc():
        from sicop import bccr
        return bccr.guardar_tc_del_dia(corrida=corrida)
    _paso(corrida, "tc_dia", _tc,
          detalle_ok=lambda d: f"TC {d.get('tc_bccr_compra')} ({d.get('fuente')})")

    # 1) vigilancia de reescritura
    cambios = _paso(corrida, "vigilancia", lambda: vigilancia.revisar_reescritura(corrida=corrida),
                    detalle_ok=lambda c: f"meses revisados; cambios={c}")
    recargados = []
    if cambios and reprocesar:
        from sicop import bronze, loader, silver

        extractor = os.path.join(settings.SICOP_SCRIPTS_DIR, "harness_actualizado", "sicop_loop.py")
        out = settings.SICOP_RECOVERY_DIR
        for m in cambios:
            senales._emit(corrida, "cambio_hash_fuente", "alta", "", None,
                          f"la fuente reescribio {m}", "reprocesar el mes", m)
            # anio completo, con --pesados (invitaciones + ordenes_pedido) y --force
            # (reconstruye el archivo del anio en fresco; el _cache solo re-descarga
            # el mes que cambio).
            rc = _paso(corrida, f"extractor_{m[:4]}",
                       lambda: _run([sys.executable, extractor, "--year", m[:4],
                                     "--pesados", "--force", "--no-vigilancia", "--out", out],
                                    cwd=os.path.dirname(extractor)),
                       detalle_ok=lambda r: f"anio {m[:4]} re-extraido rc={r}",
                       detalle_err=lambda e: f"extractor {m[:4]}: {e}")
        # recargar a Postgres el/los anio(s) afectado(s)
        for y in sorted({m[:4] for m in cambios}):
            def _recargar(y=y):
                return loader.recargar_anio_afectado(out, settings.SICOP_DATA_DIR, y, corrida=corrida)
            r = _paso(corrida, f"recarga_{y}", _recargar,
                      detalle_ok=lambda rr: f"copiados={rr.get('copiados')}",
                      detalle_err=lambda e: f"recarga {y}: {e}")
            if r:
                recargados.append(r)
        # bronze: nuevo snapshot inmutable SOLO de los meses cambiados (append-only)
        def _broncear():
            total = 0
            for y in sorted({m[:4] for m in cambios}):
                meses_cambio = {m for m in cambios if m[:4] == y}
                for setn in bronze.BRONZE_SETS:
                    p = os.path.join(out, f"{setn}_{y}.csv")
                    if os.path.exists(p) and os.path.getsize(p) > 1000:
                        total += bronze.construir(setn, p, corrida, meses=meses_cambio)
            return total
        _paso(corrida, "broncear", _broncear,
              detalle_ok=lambda t: f"+{t} filas (meses {sorted(cambios)})")
        if any(r.get("copiados") for r in recargados):
            _paso(corrida, "silver",
                  lambda: silver.build_all(corrida),
                  detalle_ok=lambda _: "6 hechos reconstruidos (fact_*)")

    # 2) consolidar PENDIENTES de resultado_decision
    _paso(corrida, "consolidar", lambda: resultado.consolidar_resultados(corrida),
          detalle_ok=lambda _: "decisiones consolidadas")

    # 3) senales del dia
    n = _paso(corrida, "senales", lambda: senales.generar_senales(corrida),
              detalle_ok=lambda x: f"{x} senales")

    # 4) cola priorizada
    _paso(corrida, "cola", lambda: _cola_priorizada(corrida),
          detalle_ok=lambda q: f"{len(q)} senales en cola")

    # 5) gold + gates
    if gold:
        _paso(corrida, "gold", lambda: run_derivadas(None),
              detalle_ok=lambda _: "derivadas (gold) recalculadas")
        ok, failed = _paso(corrida, "tests",
                           lambda: control.run_tests(corrida),
                           detalle_ok=lambda r: f"{len(r[0])} PASS / {len(r[1])} FAIL")
        fallidos = (failed or [])
        control.cerrar_corrida(corrida, "PUBLICADO" if not fallidos else "BLOQUEADO",
                               notas=f"senales={n}; tests={len(fallidos)} fallidos")
    else:
        control.cerrar_corrida(corrida, "OK", notas=f"senales={n}")
    print(f"== fin ciclo {corrida} ==", flush=True)
    return {"corrida": corrida, "senales": n, "cambios": cambios}
