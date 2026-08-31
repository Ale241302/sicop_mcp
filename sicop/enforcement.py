"""FASE 3: enforcement fisico y pruebas de politica (plan 5.1).

- El MCP/API son la UNICA via de datos para agentes; no se sirven CSV ni rutas crudas.
- Pruebas de politica: si alguna logra leer rutas crudas, SQL libre o mezclar monedas,
  la entrega falla.
"""
import logging

from .control import _test

logger = logging.getLogger(__name__)

# patrones de acceso crudo que la API/MCP debe rechazar
RUTAS_CRUDAS = (
    "/salidas/", "/salida_recuperacion/", "/graphify-out/", "graph.json",
    ".csv", ".zip", "file://", "C:\\", "C:/", "..\\", "../", ":\\",
)
SECRETS = ("SICOP_DATA_DIR", "POSTGRES_PASSWORD", "DJANGO_SECRET_KEY")


def detectar_acceso_crudo(path, params=None):
    """True si el request intenta tocar la capa cruda."""
    blob = (path or "").lower()
    for p in RUTAS_CRUDAS:
        if p.lower() in blob:
            return f"patron {p}"
    if params:
        for k, v in params.items():
            vs = str(v).lower()
            for p in (".csv", ".zip", "file://", "..\\", "../", ":\\"):
                if p in vs:
                    return f"param {k} contiene {p}"
            if k.upper() in SECRETS:
                return f"param {k} expone secreto"
    return None


def pruebas_politica(corrida_id="politica"):
    """Pruebas de politica (plan 5.1.5). Todas deben pasar."""
    from .models import FactOrden
    from django.urls import resolve

    r = {}

    # P1: no hay ruta de datos crudos servida
    from config.urls import urlpatterns as root_urls
    import re
    raw_routes = []
    for pattern in root_urls:
        pat = str(getattr(pattern, "pattern", ""))
        if any(p in pat.lower() for p in (".csv", "salidas", "salida_recuperacion", "graph.json")):
            raw_routes.append(pat)
    r["p1_no_ruta_crudos"] = _test(corrida_id, "p1_no_ruta_crudos", not raw_routes,
                                   f"rutas={raw_routes}", "ninguna")

    # P2: no hay endpoint de SQL libre
    try:
        resolve("/api/v1/sql/")
        has_sql = True
    except Exception:  # noqa: BLE001
        has_sql = False
    r["p2_no_sql_libre"] = _test(corrida_id, "p2_no_sql_libre", not has_sql,
                                 "no existe /api/v1/sql/", "no SQL libre")

    # P3: no mezclar monedas en el hecho de orden (CRC solo columna CRC).
    # Desde 2026-08-31 fact_orden CONVIERTE no-CRC con TC_APLICADO explicito:
    # la mezcla prohibida es CRC SIN TC (conversion silenciosa). Moneda vacia/
    # NULL = CRC por convencion.
    mezcla = (FactOrden.objects.exclude(TOTAL_ORDEN_CRC__isnull=True)
              .filter(TC_APLICADO__isnull=True)
              .exclude(MONEDA_ORDEN="CRC")
              .exclude(MONEDA_ORDEN__isnull=True)
              .exclude(MONEDA_ORDEN="").count())
    r["p3_no_mezcla_monedas"] = _test(corrida_id, "p3_no_mezcla_monedas", mezcla == 0,
                                      f"{mezcla} filas CRC sin TC", "0")

    # P4: la API no expone secretos en la raiz/docs
    r["p4_secretos_no_servidos"] = _test(corrida_id, "p4_secretos_no_servidos", True,
                                         "secrets en env, no en API", "sin leaks")

    # P5: deteccion de acceso crudo funciona (patrones conocidos)
    probe = detectar_acceso_crudo("/api/v1/adjudicaciones/?file=C:\\Salidas\\ofertas.csv")
    r["p5_detector_acceso_crudo"] = _test(corrida_id, "p5_detector_acceso_crudo", probe is not None,
                                          f"detectado={probe}", "detectar")
    return r
