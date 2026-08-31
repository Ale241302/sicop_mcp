"""Capa SILVER: los 6 hechos canonicos (plan PLAN_CONSTRUCCION Fase 1.3.2).

Convenciones:
- dinero en DECIMAL(18,4)
- trio de moneda completo: _ORIG + _MONEDA + _TC + _CRC
- claves normalizadas a entero-string (NUMERO_LINEA vs NRO_LINEA)
- bitemporal: OBSERVADO_DESDE / OBSERVADO_HASTA / ES_VIGENTE + HASH_FILA + CORRIDA_ID
"""
import hashlib
import logging
from datetime import datetime

from django.utils import timezone

from .models import (
    SicopLineasCartel, SicopLineasOfertadas, SicopOfertas,
    SicopAdjudicaciones, SicopAdjudicacionesFirme,
    SicopLineasContratadas, SicopOrdenesPedido, SicopLineasRecibidas,
    FactRequerimiento, FactOferta, FactAdjudicacion,
    FactContratoLinea, FactOrden, FactRecepcion,
)

logger = logging.getLogger(__name__)
BATCH = 20000
OUTLIER = 10**12


def _nl(v):
    """Normaliza numero de linea a entero-string."""
    if v is None or v == "":
        return None
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return str(v).strip()


def _cl(cod24):
    return (cod24 or "")[:16] or None


def _crc(monto, moneda, tc):
    """Convierte monto a CRC usando el TC de la propia fila.

    Bug corregido 2026-08-31: `monto * float(tc)` lanzaba TypeError
    (Decimal * float) y la excepcion se tragaba en silencio -> TODAS las filas
    no-CRC quedaban con *_CRC null aunque tuvieran TC. Se convierte a float.
    """
    if monto is None:
        return None
    if (moneda or "CRC") == "CRC":
        return monto
    if tc:
        try:
            r = float(monto) * float(tc)
            # campo DECIMAL(18,4): max ~9.99e13. Valores mayores son precios
            # contaminados de la fuente (no representables) -> null (no crashear)
            if abs(r) >= 10**14:
                return None
            return r
        except (TypeError, ValueError):
            return None
    return None


def _h(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p or "").encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def _flush(model, batch, seen):
    if batch:
        model.objects.bulk_create(batch, batch_size=2000)
        batch.clear()
        seen[0] += len(batch) if batch else 0


def corrida_now():
    return timezone.now()


def fact_requerimiento(corrida):
    """Grano: procedimiento x linea x partida (el cartel).

    La fuente re-publica el cartel de procedimientos abiertos en varios meses
    (snapshots mensuales). Se deduplica por clave quedandose con el snapshot
    MAS RECIENTE (max MES_PUBLICACION) -> el fact es el cartel canonico, una
    fila por linea, sin duplicados cross-mes.
    """
    FactRequerimiento.objects.all().delete()
    now = corrida_now()
    batch = []
    visto = set()
    qs = (SicopLineasCartel.objects
          .order_by("NRO_SICOP", "NUMERO_LINEA", "NUMERO_PARTIDA", "-MES_PUBLICACION")
          .values().iterator())
    for r in qs:
        n_linea = _nl(r.get("NUMERO_LINEA"))
        n_partida = _nl(r.get("NUMERO_PARTIDA"))
        clave = (r.get("NRO_SICOP"), n_linea, n_partida)
        if clave in visto:
            continue
        visto.add(clave)
        cod_cl = _cl(r.get("CODIGO_IDENTIFICACION"))
        pu = r.get("PRECIO_UNITARIO_ESTIMADO")
        mon = r.get("TIPO_MONEDA")
        tc = r.get("TIPO_CAMBIO_CRC")
        obj = FactRequerimiento(
            NRO_SICOP=r.get("NRO_SICOP"), NUMERO_LINEA=n_linea,
            NUMERO_PARTIDA=n_partida, CODIGO_CL=cod_cl,
            CODIGO_PRODUCTO=r.get("CODIGO_IDENTIFICACION"), DESC_LINEA=r.get("DESC_LINEA"),
            CANTIDAD_SOLICITADA=r.get("CANTIDAD_SOLICITADA"), PU_ESTIMADO_ORIG=pu,
            MONEDA_ESTIMADO=mon, TC_ESTIMADO=tc, PU_ESTIMADO_CRC=_crc(pu, mon, tc),
            OBSERVADO_DESDE=now, ES_VIGENTE=True,
            HASH_FILA=_h(r.get("NRO_SICOP"), n_linea, n_partida, cod_cl, pu, mon, tc),
            CORRIDA_ID=corrida,
        )
        batch.append(obj)
        if len(batch) >= BATCH:
            FactRequerimiento.objects.bulk_create(batch, batch_size=2000)
            batch = []
    if batch:
        FactRequerimiento.objects.bulk_create(batch, batch_size=2000)
    print(f"fact_requerimiento: {FactRequerimiento.objects.count()}", flush=True)


def fact_oferta(corrida):
    """Grano: procedimiento x oferta x linea (N por linea)."""
    FactOferta.objects.all().delete()
    now = corrida_now()
    prov = {}
    for r in SicopOfertas.objects.values("NRO_SICOP", "NRO_OFERTA", "CEDULA_PROVEEDOR", "TIPO_OFERTA"):
        prov[(r["NRO_SICOP"], r["NRO_OFERTA"])] = r
    batch = []
    for r in SicopLineasOfertadas.objects.values().iterator():
        p = prov.get((r.get("NRO_SICOP"), r.get("NRO_OFERTA")), {})
        pu = r.get("PRECIO_UNITARIO_OFERTADO")
        mon = r.get("TIPO_MONEDA")
        tc = r.get("TIPO_CAMBIO_CRC")
        obj = FactOferta(
            NRO_SICOP=r.get("NRO_SICOP"), NRO_OFERTA=_nl(r.get("NRO_OFERTA")),
            NRO_LINEA=_nl(r.get("NRO_LINEA")), CODIGO_CL=_cl(r.get("CODIGO_PRODUCTO")),
            CODIGO_PRODUCTO=r.get("CODIGO_PRODUCTO"), CEDULA_PROVEEDOR=p.get("CEDULA_PROVEEDOR"),
            CANTIDAD_OFERTADA=r.get("CANTIDAD_OFERTADA"), PU_OFERTADO_ORIG=pu,
            MONEDA_OFERTA=mon, TC_OFERTA=tc, PU_OFERTADO_CRC=_crc(pu, mon, tc),
            ES_CONSORCIO="S" if p.get("TIPO_OFERTA") == "Consorcio" else "N",
            OBSERVADO_DESDE=now, ES_VIGENTE=True,
            HASH_FILA=_h(r.get("NRO_SICOP"), r.get("NRO_OFERTA"), r.get("NRO_LINEA"), p.get("CEDULA_PROVEEDOR"), pu, mon, tc),
            CORRIDA_ID=corrida,
        )
        batch.append(obj)
        if len(batch) >= BATCH:
            FactOferta.objects.bulk_create(batch, batch_size=2000)
            batch = []
    if batch:
        FactOferta.objects.bulk_create(batch, batch_size=2000)
    print(f"fact_oferta: {FactOferta.objects.count()}", flush=True)


def fact_adjudicacion(corrida):
    """Grano: acto x procedimiento x linea x proveedor (adjudicaciones divididas sobreviven)."""
    FactAdjudicacion.objects.all().delete()
    now = corrida_now()
    acto = {}
    for r in SicopAdjudicacionesFirme.objects.values("NRO_SICOP", "NRO_ACTO"):
        acto.setdefault(r["NRO_SICOP"], r["NRO_ACTO"])
    batch = []
    for r in SicopAdjudicaciones.objects.values().iterator():
        cant = r.get("CANTIDAD")
        mon = r.get("MONEDA_ADJUDICADA")
        monto_crc = r.get("MONTO_ADJU_LINEA_CRC")
        unit_orig = r.get("MONTO_UNITARIO")
        pu_crc = unit_orig if (mon or "CRC") == "CRC" else (monto_crc / cant if cant and monto_crc else None)
        obj = FactAdjudicacion(
            NRO_SICOP=r.get("NRO_SICOP"), NRO_ACTO=acto.get(r.get("NRO_SICOP")),
            NRO_OFERTA=None, NRO_LINEA=_nl(r.get("LINEA")),
            CEDULA_PROVEEDOR=r.get("CEDULA_PROVEEDOR"), NOMBRE_PROVEEDOR=r.get("NOMBRE_PROVEEDOR"),
            CODIGO_CL=r.get("PROD_ID_CL") or _cl(r.get("PROD_ID")), PROD_ID=r.get("PROD_ID"),
            DESCR_BIEN_SERVICIO=r.get("DESCR_BIEN_SERVICIO"),
            CANTIDAD_ADJUDICADA=cant, PU_ADJUDICADO_ORIG=unit_orig, MONEDA_ADJUDICACION=mon,
            TC_ADJUDICACION=None, PU_ADJUDICADO_CRC=pu_crc, MONTO_ADJUDICADO_CRC=monto_crc,
            OBJETO_GASTO=r.get("OBJETO_GASTO"), FECHA_ADJUD_FIRME=r.get("FECHA_ADJUD_FIRME"),
            OBSERVADO_DESDE=now, ES_VIGENTE=True,
            HASH_FILA=_h(r.get("NRO_SICOP"), r.get("LINEA"), r.get("CEDULA_PROVEEDOR"), monto_crc),
            CORRIDA_ID=corrida,
        )
        batch.append(obj)
        if len(batch) >= BATCH:
            FactAdjudicacion.objects.bulk_create(batch, batch_size=2000)
            batch = []
    if batch:
        FactAdjudicacion.objects.bulk_create(batch, batch_size=2000)
    print(f"fact_adjudicacion: {FactAdjudicacion.objects.count()}", flush=True)


def fact_contrato_linea(corrida):
    """Grano: contrato x secuencia x linea."""
    FactContratoLinea.objects.all().delete()
    now = corrida_now()
    batch = []
    for r in SicopLineasContratadas.objects.values().iterator():
        pu = r.get("PRECIO_UNITARIO")
        mon = r.get("TIPO_MONEDA")
        tc = r.get("TIPO_CAMBIO_CRC")
        obj = FactContratoLinea(
            NRO_CONTRATO=r.get("NRO_CONTRATO"), SECUENCIA=_nl(r.get("SECUENCIA")),
            NRO_LINEA_CARTEL=_nl(r.get("NRO_LINEA_CARTEL")), NRO_SICOP=r.get("NRO_SICOP"),
            CEDULA_PROVEEDOR=r.get("CEDULA_PROVEEDOR"),
            CODIGO_CL=_cl(r.get("CODIGO_PRODUCTO")), CODIGO_PRODUCTO=r.get("CODIGO_PRODUCTO"),
            DESC_PRODUCTO=r.get("DESC_PRODUCTO"),
            CANTIDAD_CONTRATADA=r.get("CANTIDAD_CONTRATADA"), PU_CONTRATADO_ORIG=pu,
            MONEDA_CONTRATO=mon, TC_CONTRATO=tc, PU_CONTRATADO_CRC=_crc(pu, mon, tc),
            OBSERVADO_DESDE=now, ES_VIGENTE=True,
            HASH_FILA=_h(r.get("NRO_CONTRATO"), r.get("SECUENCIA"), r.get("NRO_SICOP"), pu, mon, tc),
            CORRIDA_ID=corrida,
        )
        batch.append(obj)
        if len(batch) >= BATCH:
            FactContratoLinea.objects.bulk_create(batch, batch_size=2000)
            batch = []
    if batch:
        FactContratoLinea.objects.bulk_create(batch, batch_size=2000)
    print(f"fact_contrato_linea: {FactContratoLinea.objects.count()}", flush=True)


def fact_orden(corrida):
    """Grano: UNA fila por NRO_ORDEN (TOTAL_ORDEN una sola vez; n_lineas aparte).

    Las ordenes en moneda != CRC se convierten con el TC implicito MEDIANO del
    mes (derivado de lineas_contratadas de la propia fuente), fallback al TC del
    dia. Total CRC sumable; las ES_OUTLIER se marcan y NO deben sumarse.
    """
    FactOrden.objects.all().delete()
    now = corrida_now()
    # TC implicito por mes (mediana CRC/USD de contratos en moneda != CRC)
    tc_por_mes = {}
    vals = {}
    for mes, tc in (SicopLineasContratadas.objects
                    .exclude(TIPO_MONEDA__in=["", "CRC"])
                    .exclude(TIPO_MONEDA__isnull=True)
                    .exclude(TIPO_CAMBIO_CRC__isnull=True)
                    .values_list("MES_PUBLICACION", "TIPO_CAMBIO_CRC")):
        vals.setdefault(mes, []).append(float(tc))
    for mes, v in vals.items():
        v.sort()
        tc_por_mes[mes] = v[len(v) // 2]
    tc_dia = None
    try:
        from .queries import _tc_del_dia
        tc_dia = _tc_del_dia()
    except Exception:  # noqa: BLE001
        pass

    ords = {}
    for r in SicopOrdenesPedido.objects.values(
            "NRO_ORDEN", "NRO_CONTRATO", "CEDULAPROVEEDOR", "FECHA_ELABORACION_ORDEN",
            "MONEDA_ORDEN", "TOTAL_ORDEN", "ESTADO_ORDEN").iterator():
        o = ords.setdefault(r["NRO_ORDEN"], {**r, "N_LINEAS": 0})
        o["N_LINEAS"] += 1
    batch = []
    for nro, r in ords.items():
        total = r.get("TOTAL_ORDEN")
        mon = r.get("MONEDA_ORDEN")
        tc = None
        if (mon or "CRC") != "CRC":
            fec = r.get("FECHA_ELABORACION_ORDEN")
            mes = f"{fec.year:04d}{fec.month:02d}" if fec else None
            tc = (tc_por_mes.get(mes) if mes else None) or tc_dia
        obj = FactOrden(
            NRO_ORDEN=nro, NRO_CONTRATO=r.get("NRO_CONTRATO"), CEDULA_PROVEEDOR=r.get("CEDULAPROVEEDOR"),
            FECHA_ELABORACION=r.get("FECHA_ELABORACION_ORDEN"), MONEDA_ORDEN=mon,
            TOTAL_ORDEN_ORIG=total, TC_APLICADO=tc,
            TOTAL_ORDEN_CRC=_crc(total, mon, tc),
            ES_OUTLIER="S" if total and abs(total) > OUTLIER else "N",
            ESTADO_ORDEN=r.get("ESTADO_ORDEN"), N_LINEAS=r.get("N_LINEAS"),
            OBSERVADO_DESDE=now, ES_VIGENTE=True,
            HASH_FILA=_h(nro, r.get("NRO_CONTRATO"), total, mon, tc),
            CORRIDA_ID=corrida,
        )
        batch.append(obj)
        if len(batch) >= BATCH:
            FactOrden.objects.bulk_create(batch, batch_size=2000)
            batch = []
    if batch:
        FactOrden.objects.bulk_create(batch, batch_size=2000)
    print(f"fact_orden: {FactOrden.objects.count()} (dedupe por NRO_ORDEN; TC por mes implicito)", flush=True)


def fact_recepcion(corrida):
    """Grano: contrato x secuencia x linea x recepcion."""
    FactRecepcion.objects.all().delete()
    now = corrida_now()
    batch = []
    for r in SicopLineasRecibidas.objects.values().iterator():
        obj = FactRecepcion(
            NRO_CONTRATO=r.get("NRO_CONTRATO"), SECUENCIA=_nl(r.get("SECUENCIA")),
            NRO_LINEA=_nl(r.get("NRO_LINEA")), NRO_SICOP=r.get("NRO_SICOP"),
            CODIGO_CL=_cl(r.get("CODIGO_PRODUCTO")), CODIGO_PRODUCTO=r.get("CODIGO_PRODUCTO"),
            DESC_PRODUCTO=r.get("desc_producto"),
            CANTIDAD_REAL_RECIBIDA=r.get("CANTIDAD_REAL_RECIBIDA"),
            ESTADO_RECEP_DEFINITIVA=r.get("ESTADO_RECEP_DEFINITIVA"),
            DIAS_ADELANTO_ATRASO=r.get("dias_adelanto_atraso"), FECHA_RECEPCION=r.get("fecha_recepcion_Definitiva"),
            OBSERVADO_DESDE=now, ES_VIGENTE=True,
            HASH_FILA=_h(r.get("NRO_CONTRATO"), r.get("SECUENCIA"), r.get("NRO_LINEA"), r.get("NRO_SICOP")),
            CORRIDA_ID=corrida,
        )
        batch.append(obj)
        if len(batch) >= BATCH:
            FactRecepcion.objects.bulk_create(batch, batch_size=2000)
            batch = []
    if batch:
        FactRecepcion.objects.bulk_create(batch, batch_size=2000)
    print(f"fact_recepcion: {FactRecepcion.objects.count()}", flush=True)


FACTS = {
    "fact_requerimiento": fact_requerimiento,
    "fact_oferta": fact_oferta,
    "fact_adjudicacion": fact_adjudicacion,
    "fact_contrato_linea": fact_contrato_linea,
    "fact_orden": fact_orden,
    "fact_recepcion": fact_recepcion,
}


def build_all(corrida=None):
    corrida = corrida or f"silver-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    for name, fn in FACTS.items():
        print(f"===== {name} =====", flush=True)
        fn(corrida)
    return corrida
