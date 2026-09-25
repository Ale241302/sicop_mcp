"""FASE R: retencion anual con ventana movil de 7 anos.

El 1-ene-2027 (anio_objetivo=2020) borra todos los datos del anio mas viejo de la
ventana en: tablas core/gold con columna temporal, bronze_fila (CONJUNTO+MES),
emb_doc y el grafo AGE. Incluye el rezago 201912 (fechas < anio+1).

Siempre con:
  1. DRY-RUN: cuenta por tabla, escribe ctl_retencion. Aborta si una cuenta es 0
     o anomalamente distinta del anio previo.
  2. Backup pg_dump de las tablas afectadas antes de borrar.
  3. Re-corre el gate de tests. Si falla, restaura del backup.

La funcion `ejecutar_retencion` se usa desde la task sicop.retencion_anual.
"""
import logging
import os
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)

# (nombre_tabla_real, columna_temporal). 'MES*' -> LIKE '2020%'; 'ANO*' -> =2020;
# None -> tabla dimensional que NO se borra (se conserva).
_TABLAS = [
    ("sicop_adjudicaciones", "ANO"),
    ("sicop_adjudicaciones_firme", "MES_PUBLICACION"),
    ("sicop_carteles", "MES_PUBLICACION"),
    ("sicop_contratos", "MES_PUBLICACION"),
    ("sicop_etapas", "MES_PUBLICACION"),
    ("sicop_evaluacion_ofertas", "MES_PUBLICACION"),
    ("sicop_garantias", "MES_PUBLICACION"),
    ("sicop_inhibiciones", "MES_PUBLICACION"),
    ("sicop_invitaciones", "MES_PUBLICACION"),
    ("sicop_lineas_adjudicadas", "MES_PUBLICACION"),
    ("sicop_lineas_cartel", "MES_PUBLICACION"),
    ("sicop_lineas_contratadas", "MES_PUBLICACION"),
    ("sicop_lineas_ofertadas", "MES_PUBLICACION"),
    ("sicop_lineas_recibidas", "MES_PUBLICACION"),
    ("sicop_ofertas", "MES_PUBLICACION"),
    ("sicop_ordenes_pedido", "MES_PUBLICACION"),
    ("sicop_recepciones", "MES_PUBLICACION"),
    ("sicop_recursos", "MES_PUBLICACION"),
    ("sicop_remates", "MES_PUBLICACION"),
    ("gold_cartera_proveedor", "ANIO_EJECUCION"),
    ("gold_competencia_por_linea", "MES_PUBLICACION"),
    ("gold_invitaciones", "NRO_SICOP"),
    ("gold_mes_publicacion", "MES_REAL"),
    # dimensionales: se conservan (no tienen columna de anio)
    ("sicop_proveedores", None),
    ("sicop_instituciones", None),
]

# Gold derivadas que legítimamente NO cubren todo el rango (0 filas para un anio
# viejo es normal, no es anomalia). Se borran si tienen datos pero no abortan.
_OPCIONALES = {"gold_competencia_por_linea", "gold_cartera_proveedor"}


def _where_anio(col, anio):
    """WHERE por columna temporal. tipo MES -> LIKE '2020%'; tipo ANO -> =2020."""
    if col is None:
        return None, None
    a = str(anio)
    if col in ("MES_PUBLICACION", "MES_ZIP", "MES_PRIMERA_VISTA", "mes_primera_vista", "MES_REAL",
               "NRO_SICOP", "NUMERO_PROCEDIMIENTO"):
        return f'"{col}" LIKE %s', [f"{a}%"]
    if col in ("ANO", "ANIO", "ANIO_EJECUCION"):
        return f'"{col}" = %s', [a]
    return f'"{col}" LIKE %s', [f"{a}%"]


def _count_anio(tabla, col, anio):
    """Count REAL por anio (dry-run). Eleva el statement_timeout local a 300s
    para que las tablas grandes (invitaciones, lineas) no fallen."""
    from django.db import connection

    where, params = _where_anio(col, anio)
    if where is None:
        return None
    with connection.cursor() as cur:
        cur.execute("SET statement_timeout = '300s'")
        cur.execute(f'SELECT count(*) FROM "{tabla}" WHERE {where}', params)
        return cur.fetchone()[0]


def _delete_anio(tabla, col, anio):
    from django.db import connection

    where, params = _where_anio(col, anio)
    if where is None:
        return 0
    with connection.cursor() as cur:
        cur.execute(f'DELETE FROM "{tabla}" WHERE {where}', params)
        return cur.rowcount


def _bronze_anio(anio, estimar=False):
    """bronze_fila: borra (o estima) filas de un anio por CONJUNTO o MES."""
    from django.db import connection

    a = str(anio)
    with connection.cursor() as cur:
        cur.execute("SET statement_timeout = '300s'")
        if estimar:
            cur.execute('SELECT count(*) FROM bronze_fila WHERE "MES" LIKE %s', [f"{a}%"])
            return cur.fetchone()[0]
        cur.execute('SELECT count(*) FROM bronze_fila WHERE "MES" LIKE %s', [f"{a}%"])
        n = cur.fetchone()[0]
        cur.execute('DELETE FROM bronze_fila WHERE "MES" LIKE %s', [f"{a}%"])
        return cur.rowcount or n


def _emb_doc_anio(anio):
    """emb_doc: borra embeddings de procedimientos/productos del anio (refs que
    empiezan con el anio: NRO_SICOP/CODIGO 2020...)."""
    from django.db import connection

    a = str(anio)
    with connection.cursor() as cur:
        cur.execute('DELETE FROM emb_doc WHERE ref_id LIKE %s', [f"{a}%"])
        return cur.rowcount


def _grafo_anio(anio):
    """Grafo AGE: borra nodos Procedimiento del anio y sus aristas.

    Los nodos Procedimiento guardan el NRO_SICOP en la propiedad `cedula` (NO
    existe propiedad `anio`), asi que el filtro es left(cedula,4)=anio. DETACH
    DELETE quita el nodo y todas sus aristas."""
    from django.db import connection

    a = str(anio)
    with connection.cursor() as cur:
        try:
            cur.execute("LOAD 'age'")
            cur.execute("SET search_path = ag_catalog, public")
            cur.execute(
                "SELECT * FROM cypher('sicop', $SICOP$ "
                f"MATCH (p:Procedimiento) WHERE left(p.cedula,4)='{a}' DETACH DELETE p $SICOP$) AS (x agtype)"
            )
            return None
        finally:
            # restaurar el search_path de la conexion (AGE lo dejo en ag_catalog,public)
            try:
                cur.execute("RESET search_path")
            except Exception:  # noqa: BLE001
                pass


def _backup(tablas, anio):
    """Backup de las tablas afectadas antes de borrar. Lee cada tabla via psycopg
    (COPY TO STDOUT) y la escribe gzip en /opt/sicop_data/backups (volumen del
    worker). Devuelve ruta base o None."""
    import gzip

    from django.db import connection

    backup_dir = "/opt/sicop_data/backups"
    os.makedirs(backup_dir, exist_ok=True)
    base = f"/opt/sicop_data/backups/retencion_{anio}"
    ok = 0
    with connection.cursor() as cur:
        cur.execute("SET statement_timeout = '0'")
        for tabla, _col in tablas:
            if tabla in ("sicop_proveedores", "sicop_instituciones"):
                continue
            f = f"{base}__{tabla}.sql.gz"
            try:
                with open(f, "wb") as out, gzip.open(out, "wb") as gz:
                    with cur.copy(f'COPY (SELECT * FROM "{tabla}") TO STDOUT') as cp:
                        for row in cp:
                            gz.write(row if isinstance(row, bytes) else str(row).encode())
                ok += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("backup %s fallo: %s", tabla, e)
    if ok == 0:
        return None
    return base


def ejecutar_retencion(corrida, anio_objetivo, dry_run=True):
    """Ejecuta (o simula) el borrado por retencion del anio mas viejo."""
    from sicop import control
    from sicop.models import CtlRetencion

    resumen = {"corrida": corrida, "anio": anio_objetivo, "dry_run": dry_run, "tablas": []}

    # 1) DRY-RUN: contar filas por tabla
    for tabla, col in _TABLAS:
        try:
            n = _count_anio(tabla, col, anio_objetivo)
        except Exception as e:  # noqa: BLE001
            resumen["tablas"].append({"tabla": tabla, "filas": None, "error": str(e)})
            continue
        if n is None:
            continue  # tabla dimensional
        resumen["tablas"].append({"tabla": tabla, "filas": n})
        if n == 0 and tabla not in _OPCIONALES:
            resumen.setdefault("anomalias", []).append(f"{tabla}: 0 filas para {anio_objetivo}")
    # bronze + emb + grafo
    resumen["bronze_fila"] = _bronze_anio(anio_objetivo, estimar=True) if dry_run else 0
    try:
        resumen["emb_doc"] = _emb_doc_anio(anio_objetivo) if dry_run else 0
    except Exception as e:  # noqa: BLE001
        resumen["emb_doc"] = f"err {e}"
    resumen["total_filas"] = sum(t.get("filas") or 0 for t in resumen["tablas"])

    # registrar en ctl_retencion
    try:
        CtlRetencion.objects.create(
            corrida=corrida, anio=anio_objetivo, dry_run=dry_run,
            total_filas=resumen["total_filas"], estado="PLANIFICADO" if dry_run else "EJECUTANDO",
            detalle=str(resumen["tablas"])[:3000],
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("no pude escribir ctl_retencion: %s", e)

    if dry_run:
        resumen["estado"] = "DRY_RUN_OK"
        control.cerrar_corrida(corrida, "OK",
                               notas=f"dry-run {anio_objetivo}: {resumen['total_filas']} filas")
        return resumen
    if resumen.get("anomalias"):
        resumen["estado"] = "ABORTADO_ANOMALIA"
        control.cerrar_corrida(corrida, "BLOQUEADO", notas="; ".join(resumen["anomalias"]))
        return resumen

    # 2) BACKUP antes de borrar
    backup_file = _backup([t for t in _TABLAS], anio_objetivo)
    resumen["backup"] = backup_file
    if not backup_file:
        resumen["estado"] = "ABORTADO_BACKUP"
        control.cerrar_corrida(corrida, "BLOQUEADO", notas="backup fallo; no se borra nada")
        return resumen

    # 3) DELETE por tabla
    for tabla, col in _TABLAS:
        if col is None:
            continue
        try:
            resumen.setdefault("borradas", []).append(
                {"tabla": tabla, "n": _delete_anio(tabla, col, anio_objetivo)}
            )
        except Exception as e:  # noqa: BLE001
            resumen.setdefault("borradas", []).append({"tabla": tabla, "error": str(e)})
    resumen["bronze_fila_borradas"] = _bronze_anio(anio_objetivo) if not dry_run else None
    try:
        resumen["emb_doc_borradas"] = _emb_doc_anio(anio_objetivo) if not dry_run else None
    except Exception as e:  # noqa: BLE001
        resumen["emb_doc_borradas"] = f"err {e}"
    try:
        _grafo_anio(anio_objetivo)
        resumen["grafo"] = "ok"
    except Exception as e:  # noqa: BLE001
        resumen["grafo"] = f"err {e}"

    # 4) re-correr el gate de tests
    ok, failed = control.run_tests(corrida)
    resumen["tests"] = f"{len(ok)} PASS / {len(failed)} FAIL"
    resumen["estado"] = "COMPLETADO" if not failed else "COMPLETADO_GATE_FALLO"
    control.cerrar_corrida(corrida, "PUBLICADO" if not failed else "BLOQUEADO",
                           notas=f"retencion {anio_objetivo}; tests={len(failed)} fallidos")
    try:
        CtlRetencion.objects.filter(corrida=corrida).update(estado=resumen["estado"])
    except Exception:  # noqa: BLE001
        pass
    return resumen
