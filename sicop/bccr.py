"""Tipo de cambio BCCR (plan F5 / P1): serie 317 compra / 318 venta.

Fuente oficial: el paquete `bccr` (nuevo SDDE del BCCR, 2026), que usa la API
apim.bccr.fi.cr/SDDE con su token publico embebido — NO requiere BCCR_TOKEN.

El TC del dia se consulta UNA vez en la manana (ciclo diario -> guardar_tc_del_dia)
y se guarda en ctl_bccr_tc. El resto del dia el MCP y la API leen de ahi
(tipo_cambio), sin volver a la API del BCCR.

Si el SDDE falla (sin internet / API caida), guarda el TC implicito de la fuente
(mediana anual CRC/USD de adjudicaciones) y lo marca como tal — nunca asume CRC
ni mezcla monedas.
"""
import json
import logging
from datetime import date, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

FUENTE_BCCR = "BCCR oficial (SDDE 317/318)"
FUENTE_IMPLICITO = "implicito_fuente"


def tc_bccr_sdde(fecha=None, indicador="317", dias_ventana=12):
    """TC oficial del BCCR (nuevo SDDE) para la fecha.

    Trae una ventana de dias hasta `fecha` y devuelve el ultimo valor publicado
    <= fecha (si hoy aun no publica, el mas reciente disponible). None si falla.
    """
    try:
        from bccr import SW
    except Exception:  # noqa: BLE001
        logger.warning("paquete bccr no disponible")
        return None
    fecha = fecha or date.today()
    inicio = fecha - timedelta(days=dias_ventana)
    try:
        serie = SW.descargar_indicador(
            indicador,
            FechaInicio=inicio.isoformat().replace("-", "/"),
            FechaFinal=fecha.isoformat().replace("-", "/"),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("BCCR SDDE fallo (%s): %s", indicador, e)
        return None
    if serie is None or serie.empty:
        return None
    serie = serie.dropna()
    if serie.empty:
        return None
    return float(serie.iloc[-1])


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
    Fuente: BCCR oficial (SDDE) si responde; si no, implicito de la fuente.
    """
    from sicop.models import CtlBccrTc

    fecha = fecha or date.today()
    compra = tc_bccr_sdde(fecha, "317")
    venta = tc_bccr_sdde(fecha, "318")
    if compra:
        fuente = FUENTE_BCCR
        sobre = {"moneda": "CRC/USD", "serie_compra": "317", "serie_venta": "318"}
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


def tc_del_dia(fecha=None):
    """TC CRC/USD oficial del dia (compra) guardado en ctl_bccr_tc.

    Para conversiones monetarias en las respuestas del MCP/API. Si NO hay fila
    guardada para la fecha (p.ej. antes del primer ciclo o ciclo fallido),
    consulta y guarda en el momento (fallback on-demand); una vez guardado,
    el resto de llamadas del dia leen de la tabla y el ciclo solo lo refresca.
    None solo si la consulta en vivo tambien falla.
    """
    from sicop.models import CtlBccrTc

    fecha = fecha or date.today()
    obj = CtlBccrTc.objects.filter(fecha=fecha).first()
    if obj and obj.tc_compra is not None:
        return float(obj.tc_compra)
    try:
        d = guardar_tc_del_dia(fecha)
        return d.get("tc_bccr_compra")
    except Exception as e:  # noqa: BLE001
        logger.warning("tc_del_dia fallo on-demand: %s", e)
        return None
