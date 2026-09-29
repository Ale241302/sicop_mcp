"""FASE D: nodos Familia + aristas COMPITE_EN (Proveedor -> Familia).

Deriva de gold_competencia_por_linea: familia = left(CODIGO_PRODUCTO_CL,6).
Propiedades de la arista: n_lineas, wins (adjudicadas), monto_crc.
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
    with connection.cursor() as cur:
        cur.execute("LOAD 'age'")
        cur.execute("SET search_path = ag_catalog, public")
        cur.execute(f"SELECT * FROM cypher('sicop', $SICOP$ {q} $SICOP$) AS (x agtype)")


def main():
    t0 = time.time()
    sql = """
    SELECT "CEDULA_PROVEEDOR", left("CODIGO_PRODUCTO_CL",6) AS familia,
           count(*) AS n_lineas,
           count(*) FILTER (WHERE "ES_ADJUDICATARIO"='S') AS wins,
           sum(COALESCE("PRECIO_UNITARIO_CRC",0)) AS monto
    FROM gold_competencia_por_linea
    WHERE "CODIGO_PRODUCTO_CL" IS NOT NULL
    GROUP BY 1,2
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    print(f"filas proveedor-familia: {len(rows)}", flush=True)

    # nodos Familia (MERGE)
    familias = sorted({r[1] for r in rows})
    for i in range(0, len(familias), BATCH):
        qs = [f"MERGE (f:Familia {{familia: '{fam}'}})" for fam in familias[i:i+BATCH]]
        for q in qs:
            try:
                run_cypher(q)
            except Exception:  # noqa: BLE001
                pass
        if i % 2000 == 0:
            print(f"  familias {i}/{len(familias)}", flush=True)
    print(f"familias: {len(familias)}", flush=True)

    # aristas COMPITE_EN
    for i in range(0, len(rows), BATCH):
        for prov, fam, n_lineas, wins, monto in rows[i:i+BATCH]:
            p_ = str(prov).replace("'", "\\'")
            q = (
                f"MATCH (p:Proveedor {{cedula: '{p_}'}}), (f:Familia {{familia: '{fam}'}}) "
                f"MERGE (p)-[r:COMPITE_EN]->(f) "
                f"SET r.n_lineas={n_lineas}, r.wins={wins}, r.monto_crc={float(monto):.2f}"
            )
            try:
                run_cypher(q)
            except Exception:  # noqa: BLE001
                pass
        if i % 2000 == 0:
            print(f"  aristas {i}/{len(rows)}", flush=True)
    print(f"DONE {len(rows)} aristas COMPITE_EN en {time.time()-t0:.1f}s", flush=True)


main()
