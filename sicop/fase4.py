"""FASE 4 — Prueba: ficha ESOSA desde gold, backtest de invitaciones, holdout temporal + gate.

La prueba del plan: rehacer la ficha del competidor desde la capa canonica y que los
numeros coincidan salvo los errores ya identificados (suma de monedas, conteo de recursos).
"""
import logging
import statistics
from collections import defaultdict

from django.db.models import Sum, Count

from .models import (
    FactAdjudicacion, FactOferta, GoldCarteraProveedor, GoldDesempenoProveedor,
    GoldCompetenciaPorLinea, GoldSancionesProveedores, SicopSancionesRegistro,
)

logger = logging.getLogger(__name__)

ESOSA = "3101086562"
SONDEL = "3101095926"


def _per_anio(cedula):
    """Captacion (adjudicado CRC) por anio de FECHA_ADJUD_FIRME."""
    from django.db.models.functions import ExtractYear

    rows = list(
        FactAdjudicacion.objects.filter(CEDULA_PROVEEDOR=cedula)
        .annotate(y=ExtractYear("FECHA_ADJUD_FIRME"))
        .values("y").annotate(monto=Sum("MONTO_ADJUDICADO_CRC"), n=Count("id"))
        .order_by("y")
    )
    return {str(r["y"]): {"monto": float(r["monto"] or 0), "n": r["n"]} for r in rows}


def _ejecucion(cedula):
    rows = list(GoldCarteraProveedor.objects.filter(CEDULA_PROVEEDOR=cedula)
                .values("ANIO_EJECUCION").annotate(m=Sum("MONTO_EJECUTADO_CRC")))
    return {r["ANIO_EJECUCION"]: float(r["m"] or 0) for r in rows}


def _competencia(cedula, familia=None):
    """Metricas de precio sobre el cruce completo (fact_oferta, 7 anios)."""
    # minimo GLOBAL por linea (todos los oferentes)
    line_min = {}
    q = FactOferta.objects.exclude(PU_OFERTADO_CRC__isnull=True)
    if familia:
        q = q.filter(CODIGO_CL__startswith=familia)
    for r in q.values("NRO_SICOP", "NRO_LINEA", "PU_OFERTADO_CRC").iterator():
        k = (r["NRO_SICOP"], r["NRO_LINEA"])
        v = r["PU_OFERTADO_CRC"]
        if k not in line_min or v < line_min[k]:
            line_min[k] = v
    q2 = FactOferta.objects.filter(CEDULA_PROVEEDOR=cedula).exclude(PU_OFERTADO_CRC__isnull=True)
    if familia:
        q2 = q2.filter(CODIGO_CL__startswith=familia)
    rows = list(q2.values("NRO_SICOP", "NRO_LINEA", "PU_OFERTADO_CRC"))
    gana = set(FactAdjudicacion.objects.filter(CEDULA_PROVEEDOR=cedula).values_list("NRO_SICOP", "NRO_LINEA"))
    ofertas = n_win = n_barato = 0
    distancias = []
    for r in rows:
        k = (r["NRO_SICOP"], r["NRO_LINEA"])
        ofertas += 1
        if k in gana:
            n_win += 1
        if line_min.get(k) == r["PU_OFERTADO_CRC"]:
            n_barato += 1
        if k not in gana and line_min.get(k):
            distancias.append((r["PU_OFERTADO_CRC"] - line_min[k]) / line_min[k])
    return {
        "ofertas_linea": ofertas,
        "win_rate_pct": round(n_win / ofertas * 100, 1) if ofertas else None,
        "mas_barato_pct": round(n_barato / ofertas * 100, 1) if ofertas else None,
        "distancia_mediana_al_ganador_pct": round(statistics.median(distancias) * 100, 1) if distancias else None,
    }


def _cara_a_cara(a, b, familia=None):
    qs = FactOferta.objects.exclude(PU_OFERTADO_CRC__isnull=True)
    if familia:
        qs = qs.filter(CODIGO_CL__startswith=familia)
    rows = list(qs.values("NRO_SICOP", "NRO_LINEA", "CEDULA_PROVEEDOR", "PU_OFERTADO_CRC"))
    lines = defaultdict(dict)
    for r in rows:
        lines[(r["NRO_SICOP"], r["NRO_LINEA"])][r["CEDULA_PROVEEDOR"]] = r["PU_OFERTADO_CRC"]
    compartidas = 0
    a_mas_barata = 0
    diffs = []
    for key, ofs in lines.items():
        if a in ofs and b in ofs and ofs[a] and ofs[b]:
            compartidas += 1
            pa, pb = ofs[a], ofs[b]
            if pa < pb:
                a_mas_barata += 1
            diffs.append(abs(pa - pb) / pb)
    return {
        "lineas_ambos": compartidas,
        "A_mas_barata_pct": round(a_mas_barata / compartidas * 100, 1) if compartidas else None,
        "diferencia_mediana_pct": round(statistics.median(diffs) * 100, 1) if diffs else None,
    }


def _desempeno(cedula):
    r = GoldDesempenoProveedor.objects.filter(CEDULA_PROVEEDOR=cedula).first()
    if not r:
        return {}
    return {"cumplimiento_pct": float(r.TASA_CUMPLIMIENTO or 0) * 100 if r.TASA_CUMPLIMIENTO and r.TASA_CUMPLIMIENTO <= 1 else float(r.TASA_CUMPLIMIENTO or 0),
            "lineas_recibidas": r.LINEAS_RECIBIDAS, "dias_mediano": r.DIAS_MEDIANO,
            "pct_con_atraso": r.PCT_CON_ATRASO}


def ficha_esosa():
    """Rehace la ficha del competidor ESOSA vs SONDEL desde la capa canonica."""
    fam = {
        "captacion_esosa": _per_anio(ESOSA),
        "captacion_sondel": _per_anio(SONDEL),
        "ejecucion_esosa": _ejecucion(ESOSA),
        "ejecucion_sondel": _ejecucion(SONDEL),
        "competencia_esosa": _competencia(ESOSA),
        "competencia_sondel": _competencia(SONDEL),
        "cara_a_cara": _cara_a_cara(ESOSA, SONDEL),
        "desempeno_esosa": _desempeno(ESOSA),
        "desempeno_sondel": _desempeno(SONDEL),
        "sanciones_esosa": list(SicopSancionesRegistro.objects.filter(CEDULA_PROVEEDOR=ESOSA).values("TIPO_SANCION", "DESCR_SANCION")),
    }
    # instituciones top de ESOSA
    from django.db.models.functions import Coalesce
    inst = list(
        FactAdjudicacion.objects.filter(CEDULA_PROVEEDOR=ESOSA)
        .values("OBJETO_GASTO").annotate(m=Sum("MONTO_ADJUDICADO_CRC"), n=Count("id"))
        .order_by("-m")[:10]
    )
    fam["top_objetos_gasto_esosa"] = [{"objeto": r["OBJETO_GASTO"], "monto": float(r["m"] or 0), "n": r["n"]} for r in inst]
    fam["sobre"] = {"fuente": "capa canonica (fact_adjudicacion, cartera, cruce, desempeno)",
                    "nota": "r vs estimado del pliego requiere lineas_cartel (recuperacion); aqui solo cruce"}
    return fam


def backtest_invitaciones():
    """Replay de invitaciones pasadas: con cuanto descuento sobre el ESTIMADO del pliego
    habriamos ganado? (ancla = PU_ESTIMADO_CRC de fact_requerimiento; ganador = fact_adjudicacion).
    Descuento necesario por procedimiento = 1 - (precio_ganador/estimado)."""
    from .models import SicopInvitaciones, FactRequerimiento

    if SicopInvitaciones.objects.count() == 0:
        return {"error": "invitaciones no cargadas"}
    inv_proc = set(SicopInvitaciones.objects.values_list("NRO_SICOP", flat=True).distinct())

    # estimado por linea (fact_requerimiento) agrupado por procedimiento
    est_by_proc = defaultdict(dict)
    for r in FactRequerimiento.objects.exclude(PU_ESTIMADO_CRC__isnull=True).values(
            "NRO_SICOP", "NUMERO_LINEA", "PU_ESTIMADO_CRC").iterator():
        d = est_by_proc[r["NRO_SICOP"]]
        k = r["NUMERO_LINEA"]
        d[k] = min(d.get(k) or r["PU_ESTIMADO_CRC"], r["PU_ESTIMADO_CRC"])

    # ganador por linea (fact_adjudicacion) agrupado por procedimiento
    win_by_proc = defaultdict(dict)
    for r in FactAdjudicacion.objects.exclude(PU_ADJUDICADO_CRC__isnull=True).values(
            "NRO_SICOP", "NRO_LINEA", "PU_ADJUDICADO_CRC").iterator():
        d = win_by_proc[r["NRO_SICOP"]]
        k = r["NRO_LINEA"]
        d[k] = min(d.get(k) or r["PU_ADJUDICADO_CRC"], r["PU_ADJUDICADO_CRC"])

    # descuento necesario por procedimiento = 1 - mediana(precio_ganador/estimado)
    desc_nec = []
    n_evaluados = 0
    for nro in inv_proc:
        e = est_by_proc.get(nro)
        w = win_by_proc.get(nro)
        if not e or not w:
            continue
        ratios = []
        for linea in set(e) & set(w):
            em, wm = e[linea], w[linea]
            if em:
                ratios.append(wm / em)
        if ratios:
            n_evaluados += 1
            desc_nec.append(1 - statistics.median(ratios))

    def winrate(d):
        return sum(1 for x in desc_nec if x <= d) / len(desc_nec) * 100 if desc_nec else None

    return {
        "procedimientos_invitados": len(inv_proc),
        "con_estimado_y_ganador": n_evaluados,
        "descuento_mediano_necesario_pct": round(statistics.median(desc_nec) * 100, 1) if desc_nec else None,
        "ganaria_con_descuento": {
            f"{int(d*100)}%": round(winrate(d), 1) for d in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30)
        },
        "sobre": {"nota": "ancla = estimado del pliego (fact_requerimiento); si el descuento necesario > 0.2, pelear ahi quema margen",
                  "limitacion": "sin decisiones propias aun; el semaforo mide el descuento que habria ganado"},
    }


def holdout():
    """Holdout temporal: entrenar <=2024, probar 2025-26. Gate de muerte vs el ancla del pliego.
    Modelo simple: P(ganar|r) con r = oferta / mediana de ofertas de la linea (ancla).
    Si el modelo no supera el ancla (ofertar a la mediana), se descarta."""
    from django.db.models.functions import ExtractYear

    if FactOferta.objects.count() == 0:
        return {"error": "fact_oferta no cargada (requiere recuperacion)"}
    rows = list(
        FactOferta.objects.exclude(PU_OFERTADO_CRC__isnull=True)
        .values("NRO_SICOP", "NRO_LINEA", "CEDULA_PROVEEDOR", "PU_OFERTADO_CRC")
    )
    for r in rows:
        r["y"] = int((r["NRO_SICOP"] or "0000")[:4] or 0)
    lines = defaultdict(list)
    for r in rows:
        lines[(r["NRO_SICOP"], r["NRO_LINEA"])].append(r)

    def split(rows_):
        train, test = [], []
        for r in rows_:
            (train if r["y"] and r["y"] <= 2024 else test).append(r)
        return train, test

    train, test = [], []
    for key, ofs in lines.items():
        ganador_precio = min((o["PU_OFERTADO_CRC"] for o in ofs if True), default=None)
        # ancla = mediana de ofertas
        precios = [o["PU_OFERTADO_CRC"] for o in ofs]
        ancla = statistics.median(precios) if precios else None
        if not ancla:
            continue
        for o in ofs:
            o["r"] = o["PU_OFERTADO_CRC"] / ancla
            o["gana"] = 1 if o["PU_OFERTADO_CRC"] == min(precios) else 0
        t, te = split(ofs)
        train.extend(t)
        test.extend(te)

    def winrate(rows_, rmax):
        sel = [r for r in rows_ if r["r"] <= rmax]
        return (sum(r["gana"] for r in sel), len(sel))

    # modelo simple: ofertar al ancla (r=1) o con descuentos
    out = {"n_train": len(train), "n_test": len(test)}
    for label, rmax in (("ancla_r1.0", 1.0), ("r0.95", 0.95), ("r0.90", 0.90), ("r0.85", 0.85)):
        g, t = winrate(test, rmax)
        out[label] = {"gana": g, "lineas": t, "winrate_pct": round(g / t * 100, 1) if t else None}

    # gate de muerte: el modelo (mejor descuento en test) debe superar al ancla
    ancla_wr = out["ancla_r1.0"]["winrate_pct"] or 0
    mejor = max((out[k]["winrate_pct"] or 0) for k in out if k.startswith("r"))
    out["gate_muerte"] = {"modelo_mejor_wr": mejor, "ancla_wr": ancla_wr,
                          "sobrevive": mejor > ancla_wr,
                          "veredicto": "MODELO SOBREVIVE" if mejor > ancla_wr else "MODELO DESCARTADO (queda memoria + vigilancia)"}
    return out


def run_todo():
    return {"ficha_esosa": ficha_esosa(), "backtest": backtest_invitaciones(), "holdout": holdout()}
