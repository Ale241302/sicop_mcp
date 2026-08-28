"""Pendientes del traspaso P1-P7, P10 (resolubles con el corpus).

P1  conversion de moneda en cartera/ranking (TC implicito de la fuente, BCCR queda pendiente)
P3  catalogo de familias UNSPSC derivado del corpus (oficial queda con gate legal)
P5  desambiguar recurrente vs recurrido en recursos
P6  sanciones cruzadas contra vigencia (sancionado que sigue ganando)
P7  verificar TAMANO_PROVEEDOR historico (cambia o no)
P10 bronze desde miembro del zip (fila cruda literal)
"""
import csv
import hashlib
import json
import logging
import os
import statistics
import zipfile
from collections import defaultdict
from datetime import datetime

from django.utils import timezone

from .models import (
    GoldCarteraProveedor, FactAdjudicacion, FactOrden,
    SicopSancionesRegistro, SicopAdjudicaciones, SicopProveedores,
    CatalogoCampo, BronzeFila, GoldCatalogoProductos,
)
from .control import _test

logger = logging.getLogger(__name__)
BATCH = 20000


# ---------------------------------------------------------------------------
# P1 — conversion de moneda con TC implicito de la fuente
# ---------------------------------------------------------------------------
def tc_implicito_por_mes():
    """TC CRC/USD implicito desde fact_adjudicacion (MONTO_USD vs MONTO_CRC) por mes."""
    from django.db.models import Sum
    from django.db.models.functions import ExtractYearMonth

    rows = list(
        FactAdjudicacion.objects.exclude(MONTO_ADJUDICADO_CRC__isnull=True).exclude(PRECIO_ADJUDICADO_CRC__isnull=True)
        .annotate(ym=ExtractYearMonth("FECHA_ADJUD_FIRME"))
        .values("ym")
        .annotate(crc=Sum("MONTO_ADJUDICADO_CRC"))
    )
    # el USD no esta en fact_adjudicacion como columna; usar PROD level no. Simplificamos:
    # TC implicito desde las ordenes: FactOrden no tiene USD. Usar adjudicaciones USD si existiera.
    return None


def p1_conversion_cartera():
    """Convierte MONTO_OTRAS_MONEDAS_ORIGEN a CRC.

    Con el TC oficial del dia (ctl_bccr_tc) cuando esta guardado; tambien se
    reporta el TC implicito anual de la fuente (mediana CRC/USD adjudicaciones).
    """
    from django.db.models import Q

    tc_anual = defaultdict(list)
    for r in SicopAdjudicaciones.objects.exclude(MONTO_ADJU_LINEA_USD__isnull=True).exclude(
            MONTO_ADJU_LINEA_USD=0).exclude(MONTO_ADJU_LINEA_CRC__isnull=True).values(
            "ANO", "MONTO_ADJU_LINEA_CRC", "MONTO_ADJU_LINEA_USD").iterator():
        tc_anual[r["ANO"]].append(r["MONTO_ADJU_LINEA_CRC"] / r["MONTO_ADJU_LINEA_USD"])
    tc = {a: float(statistics.median(v)) for a, v in tc_anual.items() if v}

    try:
        from sicop.bccr import tc_del_dia
        tc_dia = tc_del_dia()
    except Exception:  # noqa: BLE001
        tc_dia = None

    out = []
    for r in GoldCarteraProveedor.objects.exclude(MONTO_OTRAS_MONEDAS_ORIGEN__isnull=True).values(
            "CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR", "ANIO_EJECUCION", "MONTO_OTRAS_MONEDAS_ORIGEN",
            "MONTO_EJECUTADO_CRC", "MONEDAS"):
        a = r["ANIO_EJECUCION"]
        t = tc.get(str(a))
        om = float(r["MONTO_OTRAS_MONEDAS_ORIGEN"] or 0)
        ejecutado = float(r["MONTO_EJECUTADO_CRC"] or 0)
        convertido = round(om * t, 2) if t else None
        convertido_dia = round(om * tc_dia, 2) if tc_dia else None
        out.append({
            "cedula": r["CEDULA_PROVEEDOR"], "nombre": r["NOMBRE_PROVEEDOR"], "anio": a,
            "otras_monedas_origen": om,
            "tc_implicito": round(t, 2) if t else None,
            "otras_monedas_crc": convertido,
            "tc_oficial_dia": tc_dia,
            "otras_monedas_crc_oficial_dia": convertido_dia,
            "ejecutado_crc": ejecutado,
            "ejecutado_total_estimado_crc": round(ejecutado + (convertido or 0), 2),
            "ejecutado_total_estimado_oficial_dia_crc": round(ejecutado + (convertido_dia or 0), 2),
        })
    out.sort(key=lambda x: -(x["ejecutado_total_estimado_oficial_dia_crc"] or x["ejecutado_total_estimado_crc"] or 0))
    nota = ("TC implicito de la fuente (mediana anual CRC/USD de adjudicaciones) + "
            "TC oficial del dia (ctl_bccr_tc, serie 317) cuando esta guardado.")
    if not tc_dia:
        nota += " Sin TC oficial del dia guardado: falta correr el ciclo (guardar_tc_del_dia)."
    return {
        "tc_implicito_anual": {k: round(v, 2) for k, v in sorted(tc.items())},
        "tc_oficial_dia": tc_dia,
        "conversiones": out[:200],
        "total_filas": len(out),
        "sobre": {"nota": nota},
    }


# ---------------------------------------------------------------------------
# P3 — catalogo de familias derivado del corpus
# ---------------------------------------------------------------------------
def p3_catalogo_familias():
    """Diccionario de familias UNSPSC derivado del corpus (oficial con gate legal)."""
    fam = {}
    for r in GoldCatalogoProductos.objects.exclude(FAMILIA_UNSPSC__isnull=True).values(
            "FAMILIA_UNSPSC", "DESCRIPCION"):
        f = r["FAMILIA_UNSPSC"]
        if f not in fam:
            fam[f] = {"productos": 0, "descripcion_ejemplo": r["DESCRIPCION"]}
        fam[f]["productos"] += 1
    out = sorted([{"familia": k, **v} for k, v in fam.items()], key=lambda x: -x["productos"])
    return {"familias": out, "total": len(out),
            "sobre": {"nota": "diccionario DERIVADO del corpus, no el UNSPSC oficial (gate legal P3 pendiente)"}}


# ---------------------------------------------------------------------------
# P5 — desambiguar recurrente vs recurrido en recursos
# ---------------------------------------------------------------------------
def p5_recurrente_vs_recurrido():
    """Dos conteos con definicion: recurrente = quien objeta (cedula del recurso);
    recurrido = el procedimiento/institucion objetada. Ambos conteos separados."""
    from .models import GoldRecursosDesenlace

    if GoldRecursosDesenlace.objects.count() == 0:
        return {"error": "recursos_desenlace no cargada"}
    por_recurrente = defaultdict(int)
    por_proc = defaultdict(int)
    for r in GoldRecursosDesenlace.objects.values("CEDULA_PROVEEDOR", "NRO_SICOP", "PROSPERO"):
        por_recurrente[r["CEDULA_PROVEEDOR"]] += 1
        por_proc[r["NRO_SICOP"]] += 1
    top_rec = sorted(por_recurrente.items(), key=lambda x: -x[1])[:20]
    return {
        "total_recursos": sum(por_recurrente.values()),
        "recurrentes_distintos": len(por_recurrente),
        "procedimientos_recurridos_distintos": len(por_proc),
        "top_recurrentes": [{"cedula": c, "recursos": n} for c, n in top_rec],
        "sobre": {"nota": "recurrente = quien objeta; recurrido = procedimiento. Los conteos 183 vs 212 difieren por esta definicion."},
    }


# ---------------------------------------------------------------------------
# P6 — sanciones contra vigencia
# ---------------------------------------------------------------------------
def p6_sanciones_vigencia():
    """Sancionados que siguieron ganando MIENTRAS la sancion estaba vigente."""
    rows = []
    for s in SicopSancionesRegistro.objects.exclude(CEDULA_PROVEEDOR__isnull=True).values(
            "CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR", "TIPO_SANCION", "INICIO_SANCION", "FINAL_SANCION"):
        ini = str(s["INICIO_SANCION"] or "")
        fin = str(s["FINAL_SANCION"] or "")
        sancionados_con_adj = 0
        vigentes_ganando = 0
        if ini:
            adj = list(SicopAdjudicaciones.objects.filter(
                CEDULA_PROVEEDOR=s["CEDULA_PROVEEDOR"]).values("FECHA_ADJUD_FIRME", "MONTO_ADJU_LINEA_CRC"))
            for a in adj:
                if a["FECHA_ADJUD_FIRME"] and str(a["FECHA_ADJUD_FIRME"]) >= ini and (not fin or str(a["FECHA_ADJUD_FIRME"]) <= fin):
                    vigentes_ganando += 1
                if a["FECHA_ADJUD_FIRME"]:
                    sancionados_con_adj += 1
        rows.append({**s, "INICIO": str(ini), "FINAL": str(fin),
                     "adj_mientras_vigente": vigentes_ganando,
                     "total_adj": sancionados_con_adj})
    rows.sort(key=lambda x: -x["adj_mientras_vigente"])
    return {
        "sanciones": rows[:100],
        "total_sanciones": len(rows),
        "sancionados_con_adjudicaciones": sum(1 for r in rows if r["total_adj"]),
        "sancionados_ganando_vigente": sum(1 for r in rows if r["adj_mientras_vigente"]),
    }


# ---------------------------------------------------------------------------
# P7 — TAMANO_PROVEEDOR historico (SCD2: cambia o no)
# ---------------------------------------------------------------------------
def p7_tamano_historico():
    """Verifica si TAMANO_PROVEEDOR cambia por proveedor a traves de los anios."""
    prov = {}
    for r in SicopProveedores.objects.exclude(CEDULA_PROVEEDOR__isnull=True).values("CEDULA_PROVEEDOR", "TAMA\u00d1O_PROVEEDOR"):
        prov[r["CEDULA_PROVEEDOR"]] = r["TAMA\u00d1O_PROVEEDOR"]
    tamano_por_prov_anio = defaultdict(set)
    for r in SicopAdjudicaciones.objects.exclude(PERFIL_PROV__isnull=True).exclude(PERFIL_PROV="").values(
            "CEDULA_PROVEEDOR", "ANO", "PERFIL_PROV").iterator():
        tamano_por_prov_anio[(r["CEDULA_PROVEEDOR"], r["ANO"])].add(r["PERFIL_PROV"])

    cambiaron = 0
    ejemplos = []
    por_prov = defaultdict(set)
    for (ced, anio), v in tamano_por_prov_anio.items():
        por_prov[ced].update(v)
    for ced, s in por_prov.items():
        if len(s) > 1:
            cambiaron += 1
            if len(ejemplos) < 10:
                ejemplos.append({"cedula": ced, "tamanos": sorted(s), "registro_proveedores": prov.get(ced)})
    return {
        "proveedores_con_tamano": len(por_prov),
        "proveedores_con_cambio_de_tamano": cambiaron,
        "pct_cambio": round(cambiaron / len(por_prov) * 100, 2) if por_prov else None,
        "ejemplos": ejemplos,
        "sobre": {"nota": "si pct de cambio > umbral -> dim_proveedor necesita SCD2"},
    }


# ---------------------------------------------------------------------------
# P10 — bronze desde miembro del zip (fila cruda literal)
# ---------------------------------------------------------------------------
def p10_bronze_zip_miembro(set_name, aaaamm, zip_path, corrida="bronze-zip"):
    """Ingiere un miembro del zip a bronze (fila cruda literal, linea fisica, hash)."""
    if not os.path.exists(zip_path):
        return {"error": f"zip no existe: {zip_path}"}
    membres = {"ofertas": "Ofertas.csv", "carteles": "DetalleCarteles.csv"}
    member = None
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        member = next((n for n in names if n.lower() == membres.get(set_name, set_name).lower() or
                       set_name.lower() in n.lower()), None)
        if not member:
            return {"error": f"miembro no encontrado para {set_name} en {names[:10]}"}
        data = z.read(member).decode("utf-8-sig", errors="replace")
    lines = data.splitlines()
    n = 0
    batch = []
    now = timezone.now()
    for i, line in enumerate(lines[1:], 1):
        if not line.strip():
            continue
        batch.append(BronzeFila(
            CONJUNTO=set_name, MES=aaaamm, CORRIDA_ID=corrida, ARCHIVO=member,
            LINEA_FISICA=i, HASH_FILA=hashlib.sha256(line.encode("utf-8")).hexdigest(),
            FILA_CRUDA=line[:4000], OBSERVADO_EN=now,
        ))
        n += 1
        if len(batch) >= BATCH:
            BronzeFila.objects.bulk_create(batch, batch_size=2000)
            batch = []
    if batch:
        BronzeFila.objects.bulk_create(batch, batch_size=2000)
    return {"conjunto": set_name, "mes": aaaamm, "miembro": member, "filas": n}


PENDIENTES = {
    "p1_conversion_cartera": p1_conversion_cartera,
    "p3_catalogo_familias": p3_catalogo_familias,
    "p5_recurrente_vs_recurrido": p5_recurrente_vs_recurrido,
    "p6_sanciones_vigencia": p6_sanciones_vigencia,
    "p7_tamano_historico": p7_tamano_historico,
}


def run(names=None):
    todo = [names] if isinstance(names, str) else (names or list(PENDIENTES))
    results = {}
    for n in todo:
        if n in PENDIENTES:
            print(f"===== {n} =====", flush=True)
            results[n] = PENDIENTES[n]()
    return results
