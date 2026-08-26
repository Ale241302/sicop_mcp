"""Senales del ciclo diario (plan FASE 2.4.3): reglas de la watchlist -> cola priorizada.

Lee watchlist.json (lo edita una persona). Reglas: cliente_participa/adjudicado/perdio,
cartel_objetado_nuevo, sancion_nueva, excepcion_concentrada, institucion_vigilada,
plazo_por_vencer, perdio_por_poco. Las alertas de calidad van primero.
"""
import json
import logging
import os
from datetime import timedelta

from django.utils import timezone

from .models import Senal, FactOferta, FactAdjudicacion, GoldCompetenciaPorLinea

logger = logging.getLogger(__name__)

DEFAULT_WATCHLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Salidas", "estado", "watchlist.json")


def _watchlist(path=None):
    path = path or DEFAULT_WATCHLIST
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _emit(corrida, tipo, prioridad, nro_sicop, nro_linea, titulo, detalle, evidencia):
    Senal.objects.create(fecha=timezone.now(), corrida=corrida, tipo=tipo, prioridad=prioridad,
                         nro_sicop=nro_sicop, nro_linea=nro_linea, titulo=titulo,
                         detalle=detalle, evidencia=evidencia, estado="DETECTADA")
    print(f"  senal {prioridad.upper()} {tipo} {nro_sicop} - {titulo[:60]}", flush=True)


def generar_senales(corrida, dias=14, path=None):
    """Computa las senales del dia contra la watchlist."""
    wl = _watchlist(path)
    provs = {p["cedula"]: p for p in wl.get("proveedores_vigilados", [])}
    insts = {i["cedula"]: i for i in wl.get("instituciones_vigiladas", [])}
    reglas = wl.get("reglas", {})
    hoy = timezone.now()
    corte = hoy - timedelta(days=dias)
    n = 0

    # ---- cliente_adjudicado / cliente_participa / cliente_perdio ----
    for ced in provs:
        alias = provs[ced]["alias"]
        p = provs[ced]["prioridad"]
        if not reglas.get("cliente_adjudicado", {}).get("activa", True):
            continue
        adj = list(FactAdjudicacion.objects.filter(CEDULA_PROVEEDOR=ced)
                   .exclude(OBSERVADO_DESDE__isnull=True)
                   .filter(OBSERVADO_DESDE__gte=corte)[:20])
        for a in adj:
            _emit(corrida, "cliente_adjudicado", p, a.NRO_SICOP, a.NRO_LINEA,
                  f"{alias} adjudico {a.NRO_SICOP}",
                  f"monto {a.MONTO_ADJUDICADO_CRC}",
                  f"cedula={ced}")
            n += 1

    # ---- institucion_vigilada ----
    for ced in insts:
        alias = insts[ced].get("alias", ced)
        if not reglas.get("institucion_vigilada", {}).get("activa", True):
            continue
        rows = list(FactAdjudicacion.objects.filter(OBJETO_GASTO="")
                    .exclude(OBSERVADO_DESDE__isnull=True)
                    .filter(OBSERVADO_DESDE__gte=corte)[:5])
        if rows:
            _emit(corrida, "institucion_vigilada", "media", rows[0].NRO_SICOP, None,
                  f"movimiento {alias}", f"{len(rows)} lineas recientes", "inst=" + ced)
            n += 1

    # ---- sancion_nueva ----
    if reglas.get("sancion_nueva", {}).get("activa", True):
        from .models import SicopSancionesRegistro
        for s in list(SicopSancionesRegistro.objects.exclude(fecha_registro__isnull=True)
                      .filter(fecha_registro__gte=corte)[:20]):
            _emit(corrida, "sancion_nueva", "alta", s.NO_RESOLUCION or s.MES_PUBLICACION or "", None,
                  f"sancion: {s.NOMBRE_PROVEEDOR}",
                  f"{s.TIPO_SANCION} - {s.DESCR_SANCION}", f"cedula={s.CEDULA_PROVEEDOR}")
            n += 1

    # ---- perdio_por_poco (proveedor vigilado) ----
    if reglas.get("cliente_perdio", {}).get("activa", True):
        from collections import defaultdict
        lines = defaultdict(list)
        for r in GoldCompetenciaPorLinea.objects.filter(MES_PUBLICACION__gte=corte.strftime("%Y%m")).values(
                "NRO_SICOP", "NRO_LINEA", "CEDULA_PROVEEDOR", "PRECIO_UNITARIO_CRC", "ES_ADJUDICATARIO").iterator():
            lines[(r["NRO_SICOP"], r["NRO_LINEA"])].append(r)
        for key, ofs in lines.items():
            ganadores = [o for o in ofs if o["ES_ADJUDICATARIO"] == "S"]
            if not ganadores:
                continue
            pg = min(g["PRECIO_UNITARIO_CRC"] for g in ganadores if g["PRECIO_UNITARIO_CRC"] is not None)
            for o in ofs:
                if o["CEDULA_PROVEEDOR"] in provs and o["ES_ADJUDICATARIO"] != "S" and o["PRECIO_UNITARIO_CRC"]:
                    diff = (o["PRECIO_UNITARIO_CRC"] - pg) / pg
                    if diff < 0.05:
                        _emit(corrida, "perdio_por_poco", provs[o["CEDULA_PROVEEDOR"]]["prioridad"],
                              key[0], key[1],
                              f"{provs[o['CEDULA_PROVEEDOR']]['alias']} perdio por poco",
                              f"brecha {diff*100:.1f}% vs ganador {pg}",
                              f"ofertado={o['PRECIO_UNITARIO_CRC']}")
                        n += 1

    # ---- cartel_objetado_nuevo ----
    if reglas.get("cartel_objetado_nuevo", {}).get("activa", True):
        from .models import GoldCartelesObjetados
        for c in list(GoldCartelesObjetados.objects.exclude(FECHA_PUBLICACION__isnull=True)
                      .filter(FECHA_PUBLICACION__gte=corte.date())[:20]):
            _emit(corrida, "cartel_objetado_nuevo", "media", c.NRO_SICOP, None,
                  f"cartel objetado {c.NOMBRE_INSTITUCION}", f"monto {c.MONTO_EST}",
                  f"se_adjudico={c.SE_ADJUDICO}")
            n += 1

    print(f"senales: {n} detectadas en corrida {corrida}", flush=True)
    return n
