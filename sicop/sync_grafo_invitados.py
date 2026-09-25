"""FASE §3.8: arista INVITADO_A (Institucion -> Proveedor) en el grafo.

Desde gold_invitaciones: para cada (inst, proveedor) unico crea arista con
propiedades n_procedimientos y ultima_fecha. Usa MERGE (idempotente).
"""
import os
import sys
import time

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
    # solo invitaciones de procedimientos recientes (2 meses) para no explotar el
    # grafo con el historico completo (62M filas). El historico sigue en
    # gold_invitaciones / tool invitaciones_procedimiento.
    from datetime import datetime
    hoy = datetime.now()
    meses = []
    for k in range(2):
        m = hoy.year * 100 + hoy.month - k
        if m % 100 <= 0:
            m = (hoy.year - 1) * 100 + (hoy.month + 12 - k)
        meses.append(str(m))
    mm = "','".join(meses)
    sql = f"""
    SELECT i."CED_INSTITUCION" AS inst,
           i."CEDULA_PROVEEDOR" AS prov,
           count(*) AS n_proc,
           max("FECHA_INVITACION") AS ultima
    FROM sicop.gold_invitaciones i
    WHERE i."CED_INSTITUCION" IS NOT NULL AND i."CED_INSTITUCION" <> ''
      AND i."CEDULA_PROVEEDOR" IS NOT NULL AND i."CEDULA_PROVEEDOR" <> ''
      AND left(i."NRO_SICOP",6) IN ('{mm}')
    GROUP BY 1,2
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    print(f"pares institucion-proveedor: {len(rows)}", flush=True)

    total = 0
    for i in range(0, len(rows), BATCH):
        qs = []
        for inst, prov, n_proc, ultima in rows[i:i+BATCH]:
            inst_ = str(inst).replace("'", "\\'")
            prov_ = str(prov).replace("'", "\\'")
            qs.append(
                f"MATCH (i:Institucion {{cedula: '{inst_}'}}), (p:Proveedor {{cedula: '{prov_}'}}) "
                f"MERGE (i)-[r:INVITADO_A]->(p) "
                f"SET r.n_procedimientos={n_proc}, r.ultima_fecha='{str(ultima or '')[:19]}'"
            )
        for q in qs:
            try:
                run_cypher(q)
                total += 1
            except Exception:  # noqa: BLE001
                pass  # nodo institucion/proveedor ausente -> ignorar
        if i % 10000 == 0:
            print(f"  {i}/{len(rows)}", flush=True)
    print(f"DONE {total} aristas INVITADO_A en {time.time()-t0:.1f}s", flush=True)


main()
