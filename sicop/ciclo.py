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

from . import autocorregir, control, resultado, senales, vigilancia
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
        from collections import defaultdict

        from sicop import bronze, loader, silver

        extractor = os.path.join(settings.SICOP_SCRIPTS_DIR, "harness_actualizado", "sicop_loop.py")
        out = settings.SICOP_RECOVERY_DIR
        # Agrupar los meses cambiados por anio y reemplazar SOLO esos meses con
        # --replace: re-descarga el zip reescrito y reprocesa ese mes. Antes se
        # corria --year <anio> --force, que reconstruia los 12 meses aunque solo
        # uno hubiera cambiado (4-6 h, ~38% CPU).
        por_anio = defaultdict(list)
        for m in cambios:
            senales._emit(corrida, "cambio_hash_fuente", "alta", "", None,
                          f"la fuente reescribio {m}", "reprocesar el mes", m)
            por_anio[m[:4]].append(m[4:])
        for y, mms in sorted(por_anio.items()):
            meses_arg = ",".join(sorted(set(mms)))
            rc = _paso(corrida, f"extractor_{y}_{meses_arg}",
                       lambda y=y, meses_arg=meses_arg: _run(
                           [sys.executable, extractor, "--year", y, "--pesados",
                            "--months", meses_arg, "--replace", "--no-vigilancia",
                            "--out", out],
                           cwd=os.path.dirname(extractor)),
                       detalle_ok=lambda r, y=y, meses_arg=meses_arg:
                           f"anio {y} meses {meses_arg} re-extraidos rc={r}",
                       detalle_err=lambda e, y=y: f"extractor {y}: {e}")
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
        # tras un gold largo (5-10 min) la conexion Django puede quedar con un
        # cursor server-side heredado que muere en el gate de tests ("cursor
        # _django_curs_... does not exist"). Cerrar para que tests abran conexion
        # fresca (cursores server-side de silver/derivadas NO se tocan).
        try:
            from django.db import connection
            connection.close()
        except Exception:  # noqa: BLE001
            pass
        # INTEGRIDAD: derivadas.run() no retorna nada (None tambien en exito),
        # asi que el exito se lee del paso registrado en corrida_paso, NO del
        # retorno de _paso. Si el paso gold quedo ERROR, NO servimos tests/capas
        # como si el dato fuera nuevo -> corrida BLOQUEADO y autocorregir re-corre.
        gold_ok = CorridaPaso.objects.filter(
            corrida=corrida, paso="gold", estado="OK").exists()
        if not gold_ok:
            fallidos = ["gold: derivadas no recalcularon (paso ERROR)"]
            ok = []
        else:
            res_tests = _paso(corrida, "tests",
                              lambda: control.run_tests(corrida),
                              detalle_ok=lambda r: f"{len(r[0])} PASS / {len(r[1])} FAIL")
            # robustez: _paso devuelve None si el paso lanzo excepcion; tratar
            # como fallo de tests (no crashear el ciclo con TypeError).
            if res_tests is None:
                ok, failed = [], ["tests: paso fallo (excepcion interna)"]
            else:
                ok, failed = res_tests
            fallidos = (failed or [])
        control.cerrar_corrida(corrida, "PUBLICADO" if not fallidos else "BLOQUEADO",
                               notas=f"senales={n}; tests={len(fallidos)} fallidos")
        # 5b) CAPAS DERIVADAS: SOLO si el gold + gate pasaron (el dato que se
        # sirve es el nuevo). Si gold/tests fallaron la corrida queda BLOQUEADO
        # y autocorregir re-corre gold+tests; las capas se sincronizan entonces.
        if not fallidos:
            from sicop.sync_capas import sync_capas as run_sync_capas

            _paso(corrida, "capas", lambda: run_sync_capas(corrida=f"{corrida}-capas"),
                  detalle_ok=lambda r: f"{len(r['pasos'])} pasos; "
                                       f"{sum(1 for p in r['pasos'] if p['estado']=='OK')} OK")
    else:
        control.cerrar_corrida(corrida, "OK", notas=f"senales={n}")

    # 6) AUTOCORREGIR: el cron detecta FAIL/BLOQUEADO/EN_CURSO colgadas y las
    # corrige dejando log (solo re-corre gold+tests una vez, boundado 6h).
    _paso(corrida, "autocorregir", lambda: autocorregir.corregir(),
          detalle_ok=lambda a: "; ".join(a))
    print(f"== fin ciclo {corrida} ==", flush=True)
    return {"corrida": corrida, "senales": n, "cambios": cambios}
