"""Tipo de cambio BCCR (plan F5 / P1): serie 317 compra / 318 venta.

El TC del dia se consulta UNA vez en la manana (ciclo diario -> guardar_tc_del_dia)
y se guarda en ctl_bccr_tc. El resto del dia el MCP y la API leen de ahi
(tipo_cambio), sin volver a la API del BCCR.

Requiere BCCR_TOKEN + BCCR_EMAIL en .env (token gratuito del BCCR). Sin token,
guarda el TC implicito de la fuente (mediana anual CRC/USD de adjudicaciones)
y lo marca como tal — nunca asume CRC ni mezcla monedas.
"""
import json
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

WSDL = ("https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/wsindicadoreseconomicos.asmx/"
        "ObtenerIndicadoresEconomicosXML")

FUENTE_BCCR = "BCCR oficial (317/318)"
FUENTE_IMPLICITO = "implicito_fuente"


def _hay_token():
    return bool(getattr(settings, "BCCR_TOKEN", "") or "")


def tc_bccr(fecha=None, indicador="317"):
    """TC del BCCR para la fecha. None si no hay token o falla."""
    fecha = fecha or date.today()
    token = getattr(settings, "BCCR_TOKEN", "") or ""
    email = getattr(settings, "BCCR_EMAIL", "") or ""
    if not token:
        return None
    params = urllib.parse.urlencode({
        "Indicador": indicador, "FechaInicio": fecha.isoformat(),
        "FechaFinal": fecha.isoformat(), "Nombre": "N", "SubNiveles": "N",
        "CorreoElectronico": email, "Token": token,
    })
    url = f"{WSDL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            xml = r.read().decode("utf-8", errors="replace")
        root = ET.fromstring(xml)
        for num in root.iter():
            if num.tag.endswith("NUM_VALOR"):
                return float(num.text)
    except Exception as e:  # noqa: BLE001
        logger.warning("BCCR fallo: %s", e)
    return None


def tc_implicito(fecha):
    """TC implicito de la fuente para el anio de la fecha (mediana CRC/USD adjudicaciones)."""
    import statistics

    from sicop.models import SicopAdjudicaciones

    anio = str(fecha.year)
    vals = []
    for r in SicopAdjudicaciones.objects.filter(ANO=anio).exclude(MONTO_ADJU_LINEA_USD__isnull=True).exclude(
            MONTO_ADJU_LINEA_USD=0).exclude(MONTO_ADJU_LINEA_CRC__isnull=True).values(
            "MONTO_ADJU_LINEA_CRC", "MONTO_ADJU_LINEA_USD").iterator():
        vals.append(r["MONTO_ADJU_LINEA_CRC"] / r["MONTO_ADJU_LINEA_USD"])
    return round(statistics.median(vals), 2) if vals else None


def guardar_tc_del_dia(fecha=None, corrida=None):
    """Consulta el TC del dia UNA vez y lo guarda en ctl_bccr_tc (upsert por fecha).

    Llamada desde el ciclo diario (manana). Devuelve el dict del TC guardado.
    """
    from sicop.models import CtlBccrTc

    fecha = fecha or date.today()
    compra = tc_bccr(fecha, "317")
    venta = tc_bccr(fecha, "318")
    if compra:
        fuente = FUENTE_BCCR
        sobre = {"moneda": "CRC/USD"}
    else:
        compra = tc_implicito(fecha)
        fuente = FUENTE_IMPLICITO
        sobre = {"moneda": "CRC/USD",
                 "aviso": "implicito de la fuente, no oficial — no usar en reportes comerciales"}
    obj, created = CtlBccrTc.objects.update_or_create(
        fecha=fecha,
        defaults={
            "tc_compra": compra, "tc_venta": venta, "fuente": fuente,
            "sobre": json.dumps(sobre, ensure_ascii=False), "corrida": corrida or "",
        },
    )
    logger.info("TC del dia %s guardado (%s): %s (nuevo=%s)", fecha, fuente, compra, created)
    return _a_dict(obj)


def _a_dict(obj):
    sobre = {}
    if obj.sobre:
        try:
            sobre = json.loads(obj.sobre)
        except ValueError:
            sobre = {}
    return {
        "fecha": obj.fecha.isoformat(),
        "tc_bccr_compra": float(obj.tc_compra) if obj.tc_compra is not None else None,
        "tc_bccr_venta": float(obj.tc_venta) if obj.tc_venta is not None else None,
        "fuente": obj.fuente,
        "sobre": sobre,
    }


def tipo_cambio(fecha=None):
    """TC para una fecha, LEYENDO de ctl_bccr_tc (guardado en la manana).

    Si no hay fila guardada para esa fecha (p.ej. antes de la primera corrida),
    consulta y guarda en el momento.
    """
    from sicop.models import CtlBccrTc

    fecha = fecha or date.today()
    obj = CtlBccrTc.objects.filter(fecha=fecha).first()
    if obj:
        return _a_dict(obj)
    return guardar_tc_del_dia(fecha)
