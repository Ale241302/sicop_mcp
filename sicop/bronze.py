"""Capa BRONZE: fila cruda inmutable con linaje (plan FASE 1 / SPEC_BRONZE_REBUILD).

Una fila por registro observado: conjunto + mes + corrida + fila fisica + hash + crudo.
Se construye desde los CSV extraidos (snapshot observado); la variante zip-miembro
(fuente literal) queda documentada en SPEC_BRONZE_REBUILD.
"""
import csv
import hashlib
import json
import logging
import os
from datetime import datetime

from django.utils import timezone

from .models import BronzeFila

logger = logging.getLogger(__name__)
BATCH = 20000


def _linea_hash(row):
    h = hashlib.sha256()
    for v in row:
        h.update(str(v or "").encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def construir(set_name, path, corrida, mes=None):
    """Vuelca un CSV a bronze (inmutable). Devuelve filas escritas."""
    archivo = os.path.basename(path)
    now = timezone.now()
    n = 0
    batch = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.reader(fh)
        try:
            hdr = next(rd)
        except StopIteration:
            return 0
        mes_idx = hdr.index("MES_PUBLICACION") if "MES_PUBLICACION" in hdr else None
        for i, row in enumerate(rd, 1):
            mes_v = mes
            if mes_idx is not None and mes_idx < len(row) and row[mes_idx].strip():
                mes_v = row[mes_idx].strip()
            batch.append(BronzeFila(
                CONJUNTO=set_name, MES=mes_v, CORRIDA_ID=corrida, ARCHIVO=archivo,
                LINEA_FISICA=i, HASH_FILA=_linea_hash(row),
                FILA_CRUDA=json.dumps(row, ensure_ascii=False), OBSERVADO_EN=now,
            ))
            n += 1
            if len(batch) >= BATCH:
                BronzeFila.objects.bulk_create(batch, batch_size=2000)
                batch = []
    if batch:
        BronzeFila.objects.bulk_create(batch, batch_size=2000)
    print(f"bronze {set_name} {os.path.basename(path)}: {n} filas", flush=True)
    return n


def backfill_core(corrida, data_dir, sets=None, years=None):
    """Bronze desde los CSV por ano de los conjuntos indicados."""
    from django.conf import settings

    years = years or [str(y) for y in range(2020, 2027)]
    sets = sets or ["adjudicaciones", "adjudicaciones_firme", "carteles", "lineas_cartel",
                    "ofertas", "lineas_ofertadas", "lineas_adjudicadas", "lineas_contratadas",
                    "lineas_recibidas", "contratos", "etapas", "garantias", "inhibiciones",
                    "instituciones", "procedimientos_adm", "reajustes", "remates",
                    "sanciones_registro", "recursos", "proveedores", "recepciones",
                    "ordenes_pedido", "invitaciones"]
    total = 0
    for set_name in sets:
        for year in years:
            p = os.path.join(data_dir, f"{set_name}_{year}.csv")
            if os.path.exists(p) and os.path.getsize(p) > 1000:
                total += construir(set_name, p, corrida, mes=f"{year}XX")
        # invitaciones 2022 vive en archivo especial dentro de Salidas
        inv22 = os.path.join(data_dir, "invitaciones_2022-002.csv")
        if set_name == "invitaciones" and os.path.exists(inv22) and os.path.getsize(inv22) > 1000:
            total += construir("invitaciones", inv22, corrida, mes="2022XX")
    print(f"bronze total: {total} filas en corrida {corrida}", flush=True)
    return total
