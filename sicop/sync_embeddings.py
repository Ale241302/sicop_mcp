"""FASE C: sincroniza embeddings del catalogo de productos en emb_doc.

Upsert incremental: solo productos sin embedding o cuyo texto cambio.
Uso: python sync_embeddings.py [--full]
"""
import os
import sys
import time

sys.path.insert(0, "/app")  # para importar config.settings dentro del contenedor
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

import requests
from django.db import connection
from django.db.models import Count

EMBEDDER_URL = os.environ.get("EMBEDDER_URL", "http://sicop_mcp-embedder-1:8500")
BATCH = 512


def fetch_productos_con_atributos(offset, limit):
    """Productos con atributos agregados en texto, SOLO los que faltan embeker."""
    sql = """
    SELECT p."CODIGO_PRODUCTO_CL" AS cod,
           p."DESCRIPCION" AS descripcion,
           p."MARCA" AS marca,
           p."MODELO" AS modelo,
           COALESCE(string_agg(a."TIPO_ATRIBUTO" || ': ' || a."VALOR" || COALESCE(' ' || a."UNIDAD", ''), ' | '), '') AS specs
    FROM gold_catalogo_productos p
    LEFT JOIN gold_atributos_producto a
      ON a."CODIGO_PRODUCTO_CL" = p."CODIGO_PRODUCTO_CL"
    WHERE NOT EXISTS (
        SELECT 1 FROM emb_doc e
        WHERE e.coleccion='PRODUCTO' AND e.ref_id = p."CODIGO_PRODUCTO_CL" AND e.embedding IS NOT NULL
    )
    GROUP BY p."CODIGO_PRODUCTO_CL", p."DESCRIPCION", p."MARCA", p."MODELO"
    ORDER BY p."CODIGO_PRODUCTO_CL"
    LIMIT %s OFFSET %s
    """
    with connection.cursor() as cur:
        cur.execute(sql, [limit, offset])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def total_productos():
    with connection.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM gold_catalogo_productos p
            WHERE NOT EXISTS (
                SELECT 1 FROM emb_doc e
                WHERE e.coleccion='PRODUCTO' AND e.ref_id = p."CODIGO_PRODUCTO_CL" AND e.embedding IS NOT NULL
            )
        """)
        return cur.fetchone()[0]


def upsert_batch(rows):
    with connection.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO emb_doc (coleccion, ref_id, texto, embedding, actualizado)
                VALUES ('PRODUCTO', %s, %s, %s::vector, now())
                ON CONFLICT (coleccion, ref_id)
                DO UPDATE SET texto=EXCLUDED.texto, embedding=EXCLUDED.embedding, actualizado=now()
                """,
                [r["cod"], r["texto"], r["vec"]],
            )


def run(full=False):
    total = total_productos()
    print(f"productos totales: {total}", flush=True)
    offset = 0
    procesados = 0
    while offset < total:
        rows = fetch_productos_con_atributos(offset, BATCH)
        if not rows:
            break
        textos = []
        for r in rows:
            marca = (r["marca"] or "").strip()
            modelo = (r["modelo"] or "").strip()
            specs = (r["specs"] or "").strip()
            parts = [r["descripcion"] or ""]
            if marca:
                parts.append(f"Marca {marca}")
            if modelo:
                parts.append(f"Modelo {modelo}")
            if specs:
                parts.append(specs)
            r["texto"] = " ".join(p for p in parts if p)
            textos.append(r["texto"])

        # retry con backoff: el embedder en CPU puede tardar mas de 120s por batch
        vecs = None
        for intento in range(4):
            try:
                resp = requests.post(f"{EMBEDDER_URL}/embed", json={"textos": textos}, timeout=300)
                resp.raise_for_status()
                vecs = resp.json()["embeddings"]
                break
            except Exception as e:  # noqa: BLE001
                print(f"  retry {intento+1}/4 ({type(e).__name__})", flush=True)
                time.sleep(10 * (intento + 1))
        if vecs is None:
            raise RuntimeError(f"no se pudo embeber batch en {offset}")
        for r, v in zip(rows, vecs):
            r["vec"] = "[" + ",".join(f"{x:.6f}" for x in v) + "]"

        upsert_batch(rows)
        procesados += len(rows)
        offset += BATCH
        print(f"  offset {offset}/{total} ({procesados})", flush=True)

    print(f"listo: {procesados} productos embebidos", flush=True)
    # si quedaron pendientes (batch que fallo el upsert o se corto), reintentar
    restantes = total_productos()
    if restantes > 0 and procesados > 0:
        print(f"quedaron {restantes} pendientes; re-lanzando pasada incremental", flush=True)
        run(full=False)


if __name__ == "__main__":
    run(full="--full" in sys.argv)
