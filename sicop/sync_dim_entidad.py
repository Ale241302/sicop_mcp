"""FASE B/D (ciclo): sincroniza dim_entidad de forma incremental.

Upsert por (tipo, cedula): inserta nuevas, actualiza nombre/nombre_norm de las
existentes. LOS ALIAS MANUALES (dim_alias_manual) quedan INTACTOS. Es idempotente.

Uso: python sync_dim_entidad.py [--full]  (--full reconstruye desde cero)
"""
import os
import sys

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.db import connection


def _upsert(tipo, tabla, col_ced, col_nombre):
    """Inserta/actualiza entidades de `tabla` en dim_entidad para el tipo dado."""
    sql = f"""
    INSERT INTO dim_entidad (tipo, cedula, nombre, nombre_norm, activo)
    SELECT '{tipo}', ced, nombre, f_norm(nombre), true FROM (
      SELECT "{col_ced}" AS ced, "{col_nombre}" AS nombre,
             ROW_NUMBER() OVER (PARTITION BY "{col_ced}" ORDER BY count(*) DESC, min("{col_nombre}")) AS rn
      FROM {tabla}
      WHERE "{col_ced}" IS NOT NULL AND "{col_ced}"<>''
        AND "{col_nombre}" IS NOT NULL AND "{col_nombre}"<>''
      GROUP BY 1,2
    ) t WHERE rn=1
    ON CONFLICT (tipo, cedula) DO UPDATE SET nombre=EXCLUDED.nombre,
        nombre_norm=EXCLUDED.nombre_norm, activo=true
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        return cur.rowcount


def run(full=False):
    if full:
        with connection.cursor() as cur:
            # no tocar alias manuales: solo marca inactivo lo que no aparece ya
            cur.execute("UPDATE dim_entidad SET activo=false WHERE alias_norm='{}' OR alias_norm IS NULL")
    n1 = _upsert("PROVEEDOR", "sicop_proveedores", "CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR")
    n2 = _upsert("INSTITUCION", "sicop_instituciones", "CEDULA", "NOMBRE_INSTITUCION")
    print(f"dim_entidad: +{n1} proveedores, +{n2} instituciones")


if __name__ == "__main__":
    run(full="--full" in sys.argv)
