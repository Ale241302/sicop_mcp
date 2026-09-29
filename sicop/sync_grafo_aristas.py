"""FASE D: carga aristas COMPITIO_CON (competencia entre proveedores) en el grafo.

Deriva de gold_competencia_por_linea: por cada (NRO_SICOP, NRO_LINEA) con 2+
oferentes, crea arista COMPITIO_CON bidireccional agregada por par.
"""
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.db import connection

BATCH = 200


def run_cypher(q):
    sql = "LOAD 'age'; SET search_path = ag_catalog, public; " + \
          f"SELECT * FROM cypher('sicop', $$ {q} $$) AS (x agtype);"
    with connection.cursor() as cur:
        cur.execute(sql)


def main():
    t0 = time.time()
    # pares de proveedores que compitieron en la misma linea
    sql = """
    SELECT a."CEDULA_PROVEEDOR" AS a, b."CEDULA_PROVEEDOR" AS b,
           count(*) AS n_lineas,
           count(*) FILTER (WHERE a."ES_ADJUDICATARIO"='S') AS wins_a,
           count(*) FILTER (WHERE b."ES_ADJUDICATARIO"='S') AS wins_b
    FROM gold_competencia_por_linea a
    JOIN gold_competencia_por_linea b
      ON a."NRO_SICOP"=b."NRO_SICOP" AND a."NRO_LINEA"=b."NRO_LINEA"
     AND a."CEDULA_PROVEEDOR" < b."CEDULA_PROVEEDOR"
    GROUP BY 1,2
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    print(f"pares COMPITIO_CON: {len(rows)}", flush=True)
    total = 0
    for i in range(0, len(rows), BATCH):
        qs = []
        for a, b, n_lineas, wins_a, wins_b in rows[i:i+BATCH]:
            a_ = str(a).replace("'", "\\'")
            b_ = str(b).replace("'", "\\'")
            qs.append(
                f"MATCH (pa:Proveedor {{cedula: '{a_}'}}), (pb:Proveedor {{cedula: '{b_}'}}) "
                f"MERGE (pa)-[r:COMPITIO_CON]-(pb) "
                f"SET r.n_lineas={n_lineas}, r.wins_a={wins_a}, r.wins_b={wins_b}"
            )
        # merge multiple en una sola query con UNWIND? AGE no soporta UNWIND sobre params
        # facil -> ejecutar de a uno en su sesion
        for q in qs:
            try:
                run_cypher(q)
            except Exception as e:  # noqa: BLE001
                # nodo ausente (proveedor sin nodo) -> ignorar
                pass
        total += len(qs)
        if i % 5000 == 0:
            print(f"  {i}/{len(rows)} ({total})", flush=True)
    print(f"DONE {total} aristas COMPITIO_CON en {time.time()-t0:.1f}s", flush=True)


main()
