"""Tipo de cambio BCCR (plan F5 / P1): serie 317 compra / 318 venta.

Requiere BCCR_TOKEN + BCCR_EMAIL en .env (token gratuito del BCCR). Sin token,
devuelve el TC implicito de la fuente (mediana anual CRC/USD de adjudicaciones)
y lo marca como tal — nunca asume CRC ni mezcla monedas.
"""
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

from django.conf import settings

logger = logging.getLogger(__name__)

WSDL = ("https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/wsindicadoreseconomicos.asmx/"
        "ObtenerIndicadoresEconomicosXML")


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


def tipo_cambio(fecha=None):
    """TC para una fecha: BCCR oficial si hay token, si no el implicito de la fuente."""
    fecha = fecha or date.today()
    oficial = tc_bccr(fecha, "317")
    if oficial:
        return {"fecha": fecha.isoformat(), "tc_bccr_compra": oficial,
                "fuente": "BCCR oficial (317)", "sobre": {"moneda": "CRC/USD"}}
    impl = tc_implicito(fecha)
    return {
        "fecha": fecha.isoformat(), "tc_implicito_fuente": impl, "tc_bccr_compra": None,
        "fuente": "TC implicito de la fuente (BCCR pendiente: falta BCCR_TOKEN/BCCR_EMAIL en .env)",
        "sobre": {"moneda": "CRC/USD", "aviso": "implicito de la fuente, no oficial — no usar en reportes comerciales"},
    }
