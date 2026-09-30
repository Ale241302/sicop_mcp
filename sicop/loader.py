"""Carga de CSV de Salidas/ a Postgres.

Cada archivo se carga una vez (seguimiento por sha256 en `LoadState`);
re-ejecutar un archivo con el mismo hash es un no-op. `--force` lo recarga
haciendo DELETE previo de esa tabla.
"""
import csv
import hashlib
import logging
import os
import shutil
from decimal import Decimal, InvalidOperation
from datetime import datetime, date

from django.db import transaction
from django.utils import timezone

from .models import LoadState

logger = logging.getLogger(__name__)

BATCH = 10000

# tablas ya forzadas en esta corrida (--force borra una vez por tabla, no por archivo)
_FORCED = set()

# modelo -> (nombre del archivo sin .csv, es_por_anio)
# core: sicop_{set}.csv por anio  |  gold: {set}.csv transversal
CORE_SETS = {
    "adjudicaciones": "SicopAdjudicaciones",
    "adjudicaciones_firme": "SicopAdjudicacionesFirme",
    "carteles": "SicopCarteles",
    "contratos": "SicopContratos",
    "etapas": "SicopEtapas",
    "evaluacion_ofertas": "SicopEvaluacionOfertas",
    "garantias": "SicopGarantias",
    "inhibiciones": "SicopInhibiciones",
    "instituciones": "SicopInstituciones",
    "procedimientos_adm": "SicopProcedimientosAdm",
    "reajustes": "SicopReajustes",
    "remates": "SicopRemates",
    "sanciones_registro": "SicopSancionesRegistro",
    # --- conjuntos recuperados desde el Observatorio (falta re-extraer) ---
    "ofertas": "SicopOfertas",
    "lineas_cartel": "SicopLineasCartel",
    "lineas_ofertadas": "SicopLineasOfertadas",
    "lineas_adjudicadas": "SicopLineasAdjudicadas",
    "lineas_contratadas": "SicopLineasContratadas",
    "lineas_recibidas": "SicopLineasRecibidas",
    "recursos": "SicopRecursos",
    "proveedores": "SicopProveedores",
    "recepciones": "SicopRecepciones",
    "ordenes_pedido": "SicopOrdenesPedido",
    "invitaciones": "SicopInvitaciones",
}

GOLD_SETS = {
    "atributos_producto": "GoldAtributosProducto",
    "barato_y_prorrogado_resumen": "GoldBaratoYProrrogadoResumen",
    "cartera_proveedor": "GoldCarteraProveedor",
    "cartera_resumen": "GoldCarteraResumen",
    "catalogo_productos": "GoldCatalogoProductos",
    "competencia_por_linea": "GoldCompetenciaPorLinea",
    "desempeno_proveedor": "GoldDesempenoProveedor",
    "desempeno_por_familia": "GoldDesempenoPorFamilia",
    "excepciones_por_adjudicatario": "GoldExcepcionesPorAdjudicatario",
    "expediente_trazabilidad": "GoldExpedienteTrazabilidad",
    "invitaciones_concentracion": "GoldInvitacionesConcentracion",
    "precio_por_institucion": "GoldPrecioPorInstitucion",
    "ranking_captacion_ejecucion": "GoldRankingCaptacionEjecucion",
    "representante_competencia": "GoldRepresentanteCompetencia",
    "representante_empresas": "GoldRepresentanteEmpresas",
    "sanciones_proveedores": "GoldSancionesProveedores",
    "carteles_objetados": "GoldCartelesObjetados",
    "barato_y_prorrogado": "GoldBaratoYProrrogado",
}

YEARS = [str(y) for y in range(2020, 2027)]


def set_for_filename(path):
    """Deriva el conjunto de un CSV por su nombre `{set}_{AAAA}.csv`.

    Usa rpartition (NO split('_')[0]): con split, `adjudicaciones_firme_2026.csv`
    daria `adjudicaciones` y se cargaria en el modelo equivocado. Ver O5
    (bug 2026-09 que vacio la captacion 2026).
    """
    stem = os.path.basename(path)[:-4] if path.endswith(".csv") else os.path.basename(path)
    setn, _, year = stem.rpartition("_")
    if setn and year.isdigit() and len(year) == 4:
        return setn
    return None


def _guard_model_file(model_name, path):
    """Rechaza cargar un archivo en el modelo de OTRO conjunto (defensa en profundidad)."""
    setn = set_for_filename(path)
    if not setn:
        return
    expected = CORE_SETS.get(setn)
    if expected and expected != model_name:
        raise ValueError(
            f"{os.path.basename(path)} pertenece a {expected}, no a {model_name} "
            f"(conjunto '{setn}'). Rechazado por _guard_model_file."
        )


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _empty(v):
    if v is None:
        return None
    v = v.strip()
    return v or None


def _dec(v):
    v = _empty(v)
    if v is None:
        return None
    for candidate in (v, v.replace(",", "")):
        try:
            d = Decimal(candidate)
            if abs(d) >= Decimal(10) ** 20:
                return None
            return d
        except (InvalidOperation, ValueError):
            continue
    return None


def _d(v):
    v = _empty(v)
    if v is None:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(v[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.strptime(v[:19], "%d/%m/%Y %H:%M:%S").date()
    except ValueError:
        return None


def _dt(v):
    v = _empty(v)
    if v is None:
        return None
    dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(v[:19] if "%H:%M" in fmt else v[:10], fmt)
            break
        except ValueError:
            continue
    # La fuente publica fechas sin zona; con USE_TZ=True asignarlas naive emite
    # RuntimeWarning y guarda hora ambigua. Se interpretan en la zona local (CR).
    if dt is not None and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _int(v):
    v = _empty(v)
    if v is None:
        return None
    try:
        return int(Decimal(v))
    except (InvalidOperation, ValueError):
        return None


COERCERS = {
    "DecimalField": _dec,
    "DateField": _d,
    "DateTimeField": _dt,
    "BigIntegerField": _int,
    "TextField": _empty,
}


def load_csv(model, path, force=False):
    """Carga un CSV en el modelo. Devuelve dict de metricas."""
    from django.apps import apps

    _guard_model_file(model, path)
    model = apps.get_model("sicop", model)
    table = model._meta.db_table
    file_name = os.path.basename(path)

    sha = sha256_of(path)
    prev = LoadState.objects.filter(table_name=table, file_path=path).first()
    if prev and prev.sha256 == sha and not force:
        logger.info("  %s ya cargado (%s filas) - skip", file_name, prev.rows_loaded)
        return {"file": file_name, "status": "skipped", "rows": 0}

    if force:
        if table not in _FORCED:
            with transaction.atomic():
                model.objects.all().delete()
                LoadState.objects.filter(table_name=table).delete()
            _FORCED.add(table)
        force = False  # solo el primer archivo de la tabla borra
        # y reconstruye: si borramos la tabla, hay que volver a cargar los
        # archivos anteriores; se marca para no saltarlos
        prev = None

    field_spec = {f.name: type(f).__name__ for f in model._meta.fields if f.name != "id"}
    coerce = {name: COERCERS.get(typ, _empty) for name, typ in field_spec.items()}

    total = 0
    coerced = 0
    batch = []

    def flush():
        nonlocal batch
        if batch:
            model.objects.bulk_create(batch, batch_size=1000, ignore_conflicts=True)
            batch = []

    non_typed = {n for n, t in field_spec.items() if t == "TextField"}

    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            obj = model()
            for name in field_spec:
                raw = row.get(name)
                val = coerce[name](raw)
                if raw and val is None and name not in non_typed:
                    coerced += 1
                setattr(obj, name, val)
            batch.append(obj)
            total += 1
            if len(batch) >= BATCH:
                flush()
    flush()

    with transaction.atomic():
        LoadState.objects.update_or_create(
            table_name=table,
            file_path=path,
            defaults={
                "sha256": sha,
                "rows_loaded": total,
                "coerced_cells": coerced,
            },
        )
    logger.info("  %s -> %s filas (%s celdas no numericas) OK", file_name, total, coerced)
    return {"file": file_name, "status": "loaded", "rows": total, "coerced": coerced}


def discover_files(data_dir):
    """Devuelve lista de (modelo, path) para todos los CSV disponibles."""
    jobs = []
    for set_name, model in CORE_SETS.items():
        for year in YEARS:
            p = os.path.join(data_dir, f"{set_name}_{year}.csv")
            if os.path.exists(p):
                jobs.append((model, p))
    # invitaciones 2022 vive en el padre de Salidas (layout local) o dentro de
    # Salidas (layout del zip en el VPS): se busca en ambos
    inv22 = os.path.join(os.path.dirname(os.path.abspath(data_dir)), "invitaciones_2022-002.csv")
    if not os.path.exists(inv22):
        inv22 = os.path.join(data_dir, "invitaciones_2022-002.csv")
    if os.path.exists(inv22):
        jobs.append(("SicopInvitaciones", inv22))
    for set_name, model in GOLD_SETS.items():
        p = os.path.join(data_dir, f"{set_name}.csv")
        if os.path.exists(p):
            jobs.append((model, p))
    return jobs


def sembrar_recuperacion(recovery_dir, data_dir, year, sets=None):
    """Copia {set}_{year}.csv de data_dir (Salidas) a recovery_dir ANTES de correr
    el extractor.

    Sin esto, el extractor opera sobre una copia PARCIAL que vive en recuperacion:
    con --replace quita el mes y lo re-agrega, pero los meses que no estan en esa
    copia se pierden; el guard de recargar_anio_afectado (<50%) entonces rechaza
    copiarla a Salidas y el mes re-extraido NUNCA llega a las tablas/silver (bug
    2026-09: el mes en curso quedaba solo en bronze).

    Sembrar hace que el extractor parta de la base completa; el --replace deja el
    archivo completo con ese mes reemplazado y la recarga si lo copia.

    No pisa un recovery que ya sea >= que Salidas (evita retroceder). Devuelve la
    lista de archivos sembrados.
    """
    import shutil

    copiados = []
    for setn in (sets or list(CORE_SETS)):
        src = os.path.join(data_dir, f"{setn}_{year}.csv")
        if setn == "invitaciones" and not os.path.exists(src):
            # layout especial del Observatorio: invitaciones_{anio}-NNN.csv
            for fn in sorted(os.listdir(data_dir)):
                if fn.startswith(f"invitaciones_{year}-") and fn.endswith(".csv"):
                    src = os.path.join(data_dir, fn)
                    break
        if not os.path.exists(src):
            continue
        dst = os.path.join(recovery_dir, f"{setn}_{year}.csv")
        if os.path.exists(dst) and os.path.getsize(dst) >= os.path.getsize(src):
            continue
        os.makedirs(recovery_dir, exist_ok=True)
        shutil.copyfile(src, dst)
        copiados.append(f"{setn}_{year}.csv")
        logger.info("  sembrado %s (%dB) para extraccion", dst, os.path.getsize(dst))
    return copiados


def recargar_anio_afectado(recovery_dir, data_dir, year, corrida=None, umbral=0.5):
    """Recarga las tablas del anio afectado tras una reescritura de la fuente.

    1. Copia {set}_{year}.csv de recovery_dir a data_dir SOLO si cambio el hash.
    2. Borra el anio de la tabla (filtro MES_PUBLICACION) y recarga el archivo.

    Guarda de seguridad: si el archivo recuperado es notablemente mas chico que
    el vigente (< umbral de bytes), NO se borra nada y se reporta la omision
    (la extraccion pudo salir incompleta).
    """
    from django.apps import apps

    copied = []
    for fn in sorted(os.listdir(recovery_dir)):
        if not fn.endswith(".csv") or fn.startswith("_"):
            continue
        base = fn[:-4]
        setn, _, y = base.rpartition("_")
        if "_" not in base or y != year:
            continue
        src = os.path.join(recovery_dir, fn)
        dst = os.path.join(data_dir, fn)
        if os.path.exists(dst) and sha256_of(dst) == sha256_of(src):
            continue
        old_size = os.path.getsize(dst) if os.path.exists(dst) else 0
        new_size = os.path.getsize(src)
        if old_size and new_size < umbral * old_size:
            logger.warning("  %s: recuperado (%dB) << vigente (%dB) — se omite recarga", fn, new_size, old_size)
            continue
        shutil.copyfile(src, dst)
        copied.append((setn, fn))

    resultados = []
    for setn, fn in copied:
        model_name = CORE_SETS.get(setn)
        if not model_name:
            continue
        # proveedores/instituciones SI estan particionadas por anio (MES_PUBLICACION):
        # recargarlas con el anio evita que el gate falle (p.ej. cedula_orden_en_proveedores)
        # por tener ordenes nuevas sin el proveedor cargado.
        model = apps.get_model("sicop", model_name)
        borradas = model.objects.filter(MES_PUBLICACION__startswith=year).delete()[0]
        res = load_csv(model_name, os.path.join(data_dir, fn))
        resultados.append({"set": setn, "borradas_anio": borradas,
                           "status": res.get("status"), "filas": res.get("rows")})
        logger.info("  %s: %s (%s filas), borradas %s", setn, res.get("status"), res.get("rows"), borradas)
    return {"anio": year, "corrida": corrida, "copiados": len(copied), "recargados": resultados}
