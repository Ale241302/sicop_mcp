"""FASE D: carga nodos del grafo sicop desde las tablas gold/silver."""
import os
import subprocess
import sys
import time

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.db import connection

BATCH = 500
# Cypher preparado por lote. Cada statement crea un nodo si no existe via MERGE.
# Ejecutar por psql con LOAD + search_path en cada corrida.


def run_cypher(cypher_list):
    if not cypher_list:
        return
    # ejecutar cada query Cypher en su propia sesion con LOAD + search_path.
    for q in cypher_list:
        sql = "LOAD 'age'; SET search_path = ag_catalog, public; " + \
              f"SELECT * FROM cypher('sicop', $$ {q} $$) AS (x agtype);"
        with connection.cursor() as cur:
            cur.execute(sql)


def insert_nodes(tipo, tabla, clave, col_nombre=None, filtro=None):
    """Inserta nodos :<tipo> desde una tabla con clave en `clave`."""
    sel = f'SELECT DISTINCT "{clave}" FROM {tabla} WHERE "{clave}" IS NOT NULL AND "{clave}" <> \'\''
    if filtro:
        sel += f" AND {filtro}"
    with connection.cursor() as cur:
        cur.execute(sel)
        vals = [r[0] for r in cur.fetchall()]
    total = len(vals)
    print(f"{tipo}: {total} nodos", flush=True)
    for i in range(0, total, BATCH):
        chunk = vals[i:i+BATCH]
        cyphers = []
        for v in chunk:
            vv = str(v).replace("'", "\\'")
            cyphers.append(
                f"MERGE (n:{tipo} {{cedula: '{vv}'}}) ON CREATE SET n.cedula='{vv}'"
            )
        run_cypher(cyphers)
        if i % 5000 == 0:
            print(f"  {tipo} {i}/{total}", flush=True)


def _meses_recientes(n=2):
    """Meses AAAAMM recientes para el sync incremental de procedimientos."""
    from datetime import datetime

    hoy = datetime.now()
    meses = []
    for k in range(n):
        m = hoy.year * 100 + hoy.month - k
        if m % 100 <= 0:
            m = (hoy.year - 1) * 100 + (hoy.month + 12 - k)
        meses.append(str(m))
    return "','".join(meses)


def main():
    t0 = time.time()
    recientes = "--recientes" in sys.argv
    # Proveedores (siempre completo: 57k, MERGE idempotente, rapido)
    insert_nodes("Proveedor", "dim_entidad", "cedula", filtro="tipo='PROVEEDOR'")
    # Instituciones
    insert_nodes("Institucion", "dim_entidad", "cedula", filtro="tipo='INSTITUCION'")
    # Procedimientos: incremental por MES_PUBLICACION reciente salvo --full
    if recientes:
        mm = _meses_recientes(2)
        filtro_proc = f'"MES_PUBLICACION" IN (\'{mm}\')'
        print(f"procedimientos recientes ({mm})", flush=True)
    else:
        filtro_proc = None
    insert_nodes("Procedimiento", "sicop_carteles", "NRO_SICOP", filtro=filtro_proc)
    print(f"TOTAL {time.time()-t0:.1f}s", flush=True)


main()
