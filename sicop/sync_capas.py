"""FASE C/D/E (ciclo): orquesta la sincronizacion de las capas derivadas
DESPUES del gold+gate del ciclo diario. Solo corre si el gate paso.

Pasos (idempotentes, incrementales, con --full para reconstruir):
  1. sync_dim_entidad  (upsert por cedula; alias manuales intactos)
  2. sync_embeddings   (upsert incremental por ref_id nuevo/cambiado)
  3. sync_grafo        (MERGE incremental: nodos proveedor/inst/familia + aristas)
  4. gold_invitaciones (reconstruir si la fuente reescribio invitaciones)

Cada paso se registra en corrida_paso (corrida=sync-capas-<ts>). Usado por
ciclo.py (tras el gate) y por la task sicop.sync_capas del beat.
"""
import logging
import os
import subprocess
import sys
import time
from datetime import datetime

logger = logging.getLogger(__name__)


def _registrar_paso(corrida, paso, estado, detalle, filas=None, duracion_ms=None):
    from sicop.models import CorridaPaso

    try:
        CorridaPaso.objects.create(
            corrida=corrida, paso=paso, estado=estado,
            detalle=str(detalle)[:3000], filas=filas, duracion_ms=duracion_ms,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("no pude registrar paso %s: %s", paso, e)


def _run_script(nombre, args=None, timeout=3600 * 3):
    """Corre un script de sync en /app/sicop/ y devuelve (rc, tail_output)."""
    base = "/app"
    cmd = [sys.executable, f"sicop/{nombre}"] + (args or [])
    p = subprocess.run(cmd, cwd=base, timeout=timeout,
                       capture_output=True, text=True)
    tail = (p.stdout or p.stderr or "").strip()[-500:]
    return p.returncode, tail


# indices de gold_invitaciones: (nombre_final, columnas). Los nombres finales se
# aplican en el swap; durante la construccion se usan con sufijo __new para no
# chocar con los de la tabla vigente (los indices son unicos POR ESQUEMA, no por
# tabla: con IF NOT EXISTS el planner se saltaba el indice y la tabla quedaba sin
# indices -> tools lentas).
_GINV_IDX = [
    ("idx_ginv_nro", '"NRO_SICOP"'),
    ("idx_ginv_ced", '"CEDULA_PROVEEDOR"'),
    ("idx_ginv_ced_fecha", '"CEDULA_PROVEEDOR", "FECHA_INVITACION" DESC'),
    ("idx_ginv_nro_fecha", '"NRO_SICOP", "FECHA_INVITACION"'),
]


def _reconstruir_gold_invitaciones():
    """Reconstruye gold_invitaciones desde la cruda (dedup por clave).

    ATOMICO: se construye en una tabla temporal y SOLO se reemplaza la tabla
    final cuando la nueva esta completa. Si algo falla (timeout, error), la tabla
    vieja queda INTACTA y funcionando. Nunca se borra la tabla vigente antes de
    tener la nueva lista. Advisory lock: evita que dos procesos compitan.

    SIEMPRE escribe en sicop.gold_invitaciones (nombres calificados con esquema).
    La conexion pooled de Django puede quedar con search_path=ag_catalog,public
    por las queries AGE de la misma sesion; sin calificar, el rebuild creaba una
    copia huerfana en el esquema de la extension (ag_catalog.gold_invitaciones)
    y dejaba sin actualizar la tabla que leen las tools (sicop)."""
    from django.db import connection, transaction

    with connection.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(888777)")
        if not cur.fetchone()[0]:
            return {"estado": "SKIP", "motivo": "otro proceso ya reconstruye gold_invitaciones"}
        try:
            # blindaje: no depender del search_path que haya dejado AGE en esta conexion
            cur.execute("RESET search_path")
            cur.execute("SET statement_timeout = '0'")
            # 1) construir la nueva en una tabla temporal (la vigente no se toca)
            cur.execute("DROP TABLE IF EXISTS sicop.gold_invitaciones_new")
            cur.execute("""
                CREATE TABLE sicop.gold_invitaciones_new AS
                SELECT "NRO_SICOP","NUMERO_PROCEDIMIENTO","CEDULA_PROVEEDOR","NOMBRE_PROVEEDOR",
                       "CED_INSTITUCION","INSTITUCION","FECHA_INVITACION",
                       min("MES_ZIP") AS MES_PRIMERA_VISTA
                FROM public.sicop_invitaciones
                GROUP BY 1,2,3,4,5,6,7
            """)
            # indices con nombre TEMPORAL (sin colision con la tabla vigente);
            # se renombran a los nombres finales en el swap.
            for nombre, cols in _GINV_IDX:
                cur.execute(
                    f"CREATE INDEX {nombre}__new ON sicop.gold_invitaciones_new({cols})")
            # 2) swap atomico y corto: solo DDL de metadatos
            with transaction.atomic():
                cur.execute("DROP TABLE IF EXISTS sicop.gold_invitaciones")
                cur.execute("ALTER TABLE sicop.gold_invitaciones_new RENAME TO gold_invitaciones")
                for nombre, _ in _GINV_IDX:
                    cur.execute(f"ALTER INDEX sicop.{nombre}__new RENAME TO {nombre}")
            cur.execute("ANALYZE sicop.gold_invitaciones")
            cur.execute("SELECT count(*) FROM sicop.gold_invitaciones")
            return {"estado": "OK", "filas": cur.fetchone()[0]}
        except Exception as e:  # noqa: BLE001
            # nunca dejar la tabla rota: si fallo el build, la vigente sigue
            try:
                cur.execute("DROP TABLE IF EXISTS sicop.gold_invitaciones_new")
            except Exception:  # noqa: BLE001
                pass
            return {"estado": "ERROR", "motivo": str(e)}
        finally:
            try:
                cur.execute("SELECT pg_advisory_unlock(888777)")
            except Exception:  # noqa: BLE001
                pass


def sync_capas(corrida=None, full=False, skip=None):
    """Ejecuta las capas derivadas tras el gate. Devuelve resumen con pasos."""
    corrida = corrida or f"sync-capas-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    skip = set(skip or [])
    resumen = {"corrida": corrida, "pasos": []}

    def _ejecutar(paso, fn, detalle_ok):
        t0 = time.time()
        try:
            res = fn()
            ms = int((time.time() - t0) * 1000)
            _registrar_paso(corrida, paso, "OK", detalle_ok(res), duracion_ms=ms)
            resumen["pasos"].append({"paso": paso, "estado": "OK", "ms": ms})
            return res
        except Exception as e:  # noqa: BLE001
            ms = int((time.time() - t0) * 1000)
            _registrar_paso(corrida, paso, "ERROR", str(e), duracion_ms=ms)
            resumen["pasos"].append({"paso": paso, "estado": "ERROR", "ms": ms, "err": str(e)})
            return None

    # 1) dim_entidad
    if "dim" not in skip:
        args = ["--full"] if full else []
        rc, tail = _ejecutar(
            "sync_dim_entidad",
            lambda: _run_script("sync_dim_entidad.py", args),
            lambda r: f"rc={r[0]}: {r[1]}",
        )

    # 2) embeddings (productos + KB)
    if "emb" not in skip:
        rc, tail = _ejecutar(
            "sync_embeddings",
            lambda: _run_script("sync_embeddings.py"),
            lambda r: f"rc={r[0]}: {r[1]}",
        )

    # 3) grafo (nodos + familias + aristas). En el ciclo diario es INCREMENTAL:
    #    --recientes limita los procedimientos a los ultimos 2 meses (MERGE
    #    idempotente). --full reconstruye todo (214k procedimientos).
    #    AUTOCURACION: si el grafo tiene MENOS procedimientos que la base por un
    #    margen grande (p.ej. nunca se hizo el full tras cargar anios viejos), el
    #    sync fuerza --full para que el grafo quede completo. El --recientes solo
    #    sirve cuando el grafo YA esta full (agrega el mes actual).
    if "grafo" not in skip:
        grafo_full = full
        if not grafo_full:
            try:
                from django.db import connection as _conn

                with _conn.cursor() as cur:
                    cur.execute("SELECT count(DISTINCT \"NRO_SICOP\") FROM sicop_carteles")
                    en_base = cur.fetchone()[0] or 0
                with _conn.cursor() as cur:
                    try:
                        cur.execute(
                            "LOAD 'age'; SET search_path=ag_catalog,public;"
                            "SELECT count(*) FROM cypher('sicop', $$ MATCH (p:Procedimiento) RETURN p $$) AS (p agtype)")
                        en_grafo = cur.fetchone()[0] or 0
                    finally:
                        # AGE deja search_path=ag_catalog,public en la conexion pooled;
                        # restaurarlo para que el resto de la sesion no resuelva mal
                        cur.execute("RESET search_path")
                # si falta >20% de los procedimientos, el grafo esta incompleto -> full
                if en_base and en_grafo < 0.8 * en_base:
                    print(f"grafo incompleto ({en_grafo}/{en_base} procedimientos) -> forzando --full",
                          flush=True)
                    grafo_full = True
            except Exception as e:  # noqa: BLE001
                print(f"no pude verificar cobertura del grafo ({e}); uso modo por defecto",
                      flush=True)
        nodos_args = ["--recientes"] if not grafo_full else []
        _ejecutar(
            "sync_grafo_nodos",
            lambda: _run_script("sync_grafo_nodos.py", nodos_args),
            lambda r: f"rc={r[0]}: {r[1]}",
        )
        for script in ("sync_grafo_familias.py", "sync_grafo_aristas.py"):
            _ejecutar(
                f"sync_grafo_{script.split('_')[-1].replace('.py','')}",
                lambda s=script: _run_script(s),
                lambda r: f"rc={r[0]}: {r[1]}",
            )

    # 4) gold_invitaciones (si no skip)
    if "invitaciones" not in skip:
        _ejecutar(
            "gold_invitaciones",
            _reconstruir_gold_invitaciones,
            lambda r: (f"{r['filas']} filas (dedup)" if r.get("estado") == "OK"
                       else f"{r.get('estado')}: {r.get('motivo','')}"),
        )

    resumen["estado"] = "OK" if all(p["estado"] == "OK" for p in resumen["pasos"]) else "PARCIAL"
    return resumen


if __name__ == "__main__":
    import json

    print(json.dumps(sync_capas(full="--full" in sys.argv), ensure_ascii=False, default=str))
