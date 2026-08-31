"""Derivadas que faltaban del plan (recursos_desenlace, tiempos_por_etapa,
precios_identicos, producto_firma, invitados_vs_ofertantes).

Regeneran una tabla Gold a partir de los conjuntos cargados. Cada funcion es
idempotente: borra la tabla y la reconstruye. Reporta cobertura.
"""
import logging
from collections import defaultdict
from datetime import timedelta

from django.db import transaction

from .models import (
    GoldProductoFirma, GoldRecursosDesenlace, GoldTiemposPorEtapa,
    GoldPreciosIdenticos, GoldInvitadosVsOfertantes,
    GoldAtributosProducto, GoldCatalogoProductos,
    SicopRecursos, SicopProveedores, SicopCarteles,
    SicopEtapas, SicopRecepciones,
    SicopLineasOfertadas, SicopOfertas,
    SicopInvitaciones, SicopAdjudicaciones,
)

logger = logging.getLogger(__name__)
BATCH = 10000


def _flush(model, batch):
    if batch:
        model.objects.bulk_create(batch, batch_size=1000)
        batch.clear()


def producto_firma():
    """Firma de SKU por (CL, marca, modelo, atributos). Listo ahora."""
    print("producto_firma: agrupando atributos...", flush=True)
    attrs = defaultdict(set)
    n_attr = defaultdict(int)
    for r in GoldAtributosProducto.objects.values("CODIGO_PRODUCTO_CL", "MARCA", "TIPO_ATRIBUTO"):
        key = (r["CODIGO_PRODUCTO_CL"], r["MARCA"] or "")
        attrs[key].add(r["TIPO_ATRIBUTO"])
        n_attr[key] += 1

    print("producto_firma: cruzando catalogo...", flush=True)
    skus = defaultdict(set)
    for r in GoldCatalogoProductos.objects.values("CODIGO_PRODUCTO_CL", "MARCA", "MODELO"):
        skus[(r["CODIGO_PRODUCTO_CL"], r["MARCA"] or "")].add(r["MODELO"] or "")

    GoldProductoFirma.objects.all().delete()
    batch = []
    total = 0
    for r in GoldCatalogoProductos.objects.values("CODIGO_PRODUCTO_CL", "FAMILIA_UNSPSC", "MARCA", "MODELO"):
        key = (r["CODIGO_PRODUCTO_CL"], r["MARCA"] or "")
        a = sorted(attrs.get(key, set()))
        obj = GoldProductoFirma(
            CODIGO_PRODUCTO_CL=r["CODIGO_PRODUCTO_CL"],
            FAMILIA_UNSPSC=r["FAMILIA_UNSPSC"],
            MARCA=r["MARCA"],
            MODELO=r["MODELO"],
            ATRIBUTOS_CLAVE="|".join(a),
            N_ATRIBUTOS=len(a),
            N_SKUS=len(skus.get(key, set())),
            FIRMA_SKU="|".join([r["CODIGO_PRODUCTO_CL"], r["MARCA"] or "", r["MODELO"] or "", "|".join(a)]),
        )
        batch.append(obj)
        total += 1
        if len(batch) >= BATCH:
            _flush(GoldProductoFirma, batch)
    _flush(GoldProductoFirma, batch)
    print(f"producto_firma: {total} firmas", flush=True)


def recursos_desenlace():
    """Recursos con recurrente (nombre/tamano), institucion, resultado y PROSPERO."""
    if SicopRecursos.objects.count() == 0:
        print("recursos_desenlace: sin datos (recursos no cargados)", flush=True)
        return
    print("recursos_desenlace: cargando dimensiones...", flush=True)
    prov = {r["CEDULA_PROVEEDOR"]: r for r in SicopProveedores.objects.values("CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR", "TAMA\u00d1O_PROVEEDOR")}
    cartel = {r["NRO_SICOP"]: r for r in SicopCarteles.objects.values("NRO_SICOP", "CEDULA_INSTITUCION")}
    inst = {r["CEDULA"]: r["NOMBRE_INSTITUCION"] for r in __import__("sicop.models", fromlist=["SicopInstituciones"]).SicopInstituciones.objects.values("CEDULA", "NOMBRE_INSTITUCION")}

    GoldRecursosDesenlace.objects.all().delete()
    batch = []
    total = 0
    qs = SicopRecursos.objects.values("NRO_RECURSO", "CEDULA_PROVEEDOR", "NRO_SICOP", "NRO_ACTO",
                                      "LINEA_OBJETADA", "TIPO_RECURSO", "RESULTADO", "CAUSA_RESULTADO",
                                      "FECHA_PRESENTACION_RECURSO", "nro_procedimiento", "desc_procedimiento")
    for r in qs:
        res = r["RESULTADO"] or ""
        if res in ("Con lugar", "Parcialmente con lugar"):
            prospero = "S"
        elif res:
            prospero = "N"
        else:
            prospero = ""
        p = prov.get(r["CEDULA_PROVEEDOR"], {})
        c = cartel.get(r["NRO_SICOP"], {})
        obj = GoldRecursosDesenlace(
            NRO_RECURSO=r["NRO_RECURSO"], CEDULA_PROVEEDOR=r["CEDULA_PROVEEDOR"],
            NOMBRE_PROVEEDOR=p.get("NOMBRE_PROVEEDOR"), TAMANO_PROVEEDOR=p.get("TAMA\u00d1O_PROVEEDOR"),
            NRO_SICOP=r["NRO_SICOP"], NRO_ACTO=r["NRO_ACTO"], LINEA_OBJETADA=r["LINEA_OBJETADA"],
            TIPO_RECURSO=r["TIPO_RECURSO"], RESULTADO=res, CAUSA_RESULTADO=r["CAUSA_RESULTADO"],
            FECHA_PRESENTACION_RECURSO=r["FECHA_PRESENTACION_RECURSO"], PROSPERO=prospero,
            CEDULA_INSTITUCION=c.get("CEDULA_INSTITUCION"),
            NOMBRE_INSTITUCION=inst.get(c.get("CEDULA_INSTITUCION")),
            nro_procedimiento=r["nro_procedimiento"], desc_procedimiento=r["desc_procedimiento"],
        )
        batch.append(obj)
        total += 1
        if len(batch) >= BATCH:
            _flush(GoldRecursosDesenlace, batch)
    _flush(GoldRecursosDesenlace, batch)
    print(f"recursos_desenlace: {total} recursos", flush=True)


def tiempos_por_etapa():
    """Dias entre etapas por procedimiento (recepcion desde Recepciones)."""
    if SicopEtapas.objects.count() == 0:
        print("tiempos_por_etapa: sin datos (etapas no cargadas)", flush=True)
        return
    print("tiempos_por_etapa: cargando fechas de recepcion...", flush=True)
    recep = {}
    for r in SicopRecepciones.objects.exclude(FECHA_RECEP_DEFINITIVA__isnull=True).values("NRO_SICOP", "FECHA_RECEP_DEFINITIVA"):
        n = recep.setdefault(r["NRO_SICOP"], r["FECHA_RECEP_DEFINITIVA"])
        if r["FECHA_RECEP_DEFINITIVA"] < n:
            recep[r["NRO_SICOP"]] = r["FECHA_RECEP_DEFINITIVA"]

    print("tiempos_por_etapa: institucion via carteles...", flush=True)
    cartel_inst = {r["NRO_SICOP"]: r["CEDULA_INSTITUCION"] for r in SicopCarteles.objects.values("NRO_SICOP", "CEDULA_INSTITUCION")}

    GoldTiemposPorEtapa.objects.all().delete()
    batch = []
    total = 0
    qs = SicopEtapas.objects.values("NRO_SICOP", "NUMERO_PROCEDIMIENTO",
                                    "PUBLICACION", "FECHA_APERTURA", "ADJUDICACION_FIRME",
                                    "FECHA_ELABORACION_CONTRATO")
    for r in qs.iterator():
        pub, ap = r["PUBLICACION"], r["FECHA_APERTURA"]
        adj, con = r["ADJUDICACION_FIRME"], r["FECHA_ELABORACION_CONTRATO"]
        rec = recep.get(r["NRO_SICOP"])
        n_tramos = sum(1 for d in (pub, ap, adj, con, rec) if d)

        def dias(a, b):
            if a and b:
                return (b - a).days
            return None

        obj = GoldTiemposPorEtapa(
            NRO_SICOP=r["NRO_SICOP"], NUMERO_PROCEDIMIENTO=r["NUMERO_PROCEDIMIENTO"],
            CEDULA_INSTITUCION=cartel_inst.get(r["NRO_SICOP"]), FECHA_PUBLICACION=pub, FECHA_APERTURA=ap,
            FECHA_ADJUDICACION=adj, FECHA_CONTRATO=con, FECHA_RECEPCION=rec,
            DIAS_PUBLICACION_APERTURA=dias(pub, ap), DIAS_PUBLICACION_ADJUDICACION=dias(pub, adj),
            DIAS_ADJUDICACION_CONTRATO=dias(adj, con), DIAS_PUBLICACION_RECEPCION=dias(pub, rec),
            N_TRAMOS=n_tramos,
        )
        batch.append(obj)
        total += 1
        if len(batch) >= BATCH:
            _flush(GoldTiemposPorEtapa, batch)
    _flush(GoldTiemposPorEtapa, batch)
    print(f"tiempos_por_etapa: {total} procedimientos", flush=True)


def precios_identicos():
    """Lineas con 2+ oferentes al mismo precio CRC exacto (cola de revision)."""
    if SicopLineasOfertadas.objects.count() == 0:
        print("precios_identicos: sin datos (lineas_ofertadas no cargadas)", flush=True)
        return
    print("precios_identicos: agrupando por linea...", flush=True)
    lines = defaultdict(list)
    qs = SicopLineasOfertadas.objects.values("NRO_SICOP", "NRO_OFERTA", "NRO_LINEA", "PRECIO_UNITARIO_OFERTADO",
                                             "TIPO_MONEDA", "TIPO_CAMBIO_CRC")
    for r in qs.iterator():
        p = r["PRECIO_UNITARIO_OFERTADO"]
        if p is None:
            continue
        if (r["TIPO_MONEDA"] or "CRC") != "CRC" and r["TIPO_CAMBIO_CRC"]:
            p = p * r["TIPO_CAMBIO_CRC"]
        lines[(r["NRO_SICOP"], r["NRO_LINEA"])].append((r["NRO_OFERTA"], p))

    # agrupar por precio dentro de cada linea
    rows = []
    par_counter = defaultdict(int)
    line_rows = []
    for key, ofs in lines.items():
        by_price = defaultdict(list)
        for oferta, precio in ofs:
            by_price[precio].append(oferta)
        for precio, ofertas in by_price.items():
            if len(ofertas) >= 2:
                line_rows.append((key, precio, ofertas, len(ofs)))
    # contar repeticion del par
    for key, precio, ofertas, n_total in line_rows:
        par_counter[tuple(sorted(ofertas))] += 1
    for key, precio, ofertas, n_total in line_rows:
        par = "|".join(sorted(ofertas))
        rows.append({
            "NRO_SICOP": key[0], "NRO_LINEA": key[1], "ANIO": (key[0] or "")[:4],
            "PRECIO_CRC": precio, "N_OFERENTES_IGUAL": len(ofertas), "N_TOTAL_OFERENTES": n_total,
            "PAR_OFERENTES": par, "REPETICION_PAR": par_counter[tuple(sorted(ofertas))],
            "ADVERTENCIA": "el par coincide en varias lineas: revisar",
        })

    GoldPreciosIdenticos.objects.all().delete()
    batch = []
    for r in sorted(rows, key=lambda x: -x["REPETICION_PAR"]):
        batch.append(GoldPreciosIdenticos(**r))
        if len(batch) >= BATCH:
            _flush(GoldPreciosIdenticos, batch)
    _flush(GoldPreciosIdenticos, batch)
    print(f"precios_identicos: {len(rows)} lineas", flush=True)


def invitados_vs_ofertantes():
    """Por procedimiento: cuantos invitados vs cuantos ofertaron (direccionamiento ex-ante).
    Agregacion en SQL (no iterar 42M filas en Python)."""
    from django.db import connection
    from .models import GoldInvitadosVsOfertantes, SicopOfertas, SicopAdjudicaciones

    if SicopInvitaciones.objects.count() == 0:
        print("invitados_vs_ofertantes: sin datos (invitaciones no cargadas)", flush=True)
        return

    print("invitados_vs_ofertantes: SQL aggregation (joins 2-vias)...", flush=True)
    q1 = 'SELECT "NRO_SICOP", COUNT(DISTINCT "CEDULA_PROVEEDOR") FROM sicop_invitaciones GROUP BY "NRO_SICOP"'
    q2 = 'SELECT "NRO_SICOP", COUNT(DISTINCT "CEDULA_PROVEEDOR") FROM sicop_ofertas GROUP BY "NRO_SICOP"'
    q3 = ('SELECT i."NRO_SICOP", COUNT(DISTINCT i."CEDULA_PROVEEDOR") FROM sicop_invitaciones i '
          'LEFT JOIN sicop_ofertas o ON o."NRO_SICOP"=i."NRO_SICOP" AND o."CEDULA_PROVEEDOR"=i."CEDULA_PROVEEDOR" '
          'WHERE o."NRO_SICOP" IS NULL GROUP BY i."NRO_SICOP"')
    q4 = ('SELECT o."NRO_SICOP", COUNT(DISTINCT o."CEDULA_PROVEEDOR") FROM sicop_ofertas o '
          'LEFT JOIN sicop_invitaciones i ON i."NRO_SICOP"=o."NRO_SICOP" AND i."CEDULA_PROVEEDOR"=o."CEDULA_PROVEEDOR" '
          'WHERE i."NRO_SICOP" IS NULL GROUP BY o."NRO_SICOP"')
    q5 = ('SELECT DISTINCT a."NRO_SICOP" FROM sicop_adjudicaciones a '
          'JOIN sicop_invitaciones i ON i."NRO_SICOP"=a."NRO_SICOP" AND i."CEDULA_PROVEEDOR"=a."CEDULA_PROVEEDOR"')

    with connection.cursor() as cur:
        cur.execute(q1); n_inv = dict(cur.fetchall())
        cur.execute(q2); n_of = dict(cur.fetchall())
        cur.execute(q3); inv_no_of = dict(cur.fetchall())
        cur.execute(q4); of_sin_inv = dict(cur.fetchall())
        cur.execute(q5); adj_inv = {r[0] for r in cur.fetchall()}
        cur.execute('SELECT "NRO_SICOP", MAX("NUMERO_PROCEDIMIENTO"), MAX("CED_INSTITUCION"), MAX("INSTITUCION") FROM sicop_invitaciones GROUP BY "NRO_SICOP"')
        meta = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}

    nros = set(n_inv) | set(n_of)
    GoldInvitadosVsOfertantes.objects.all().delete()
    batch = []
    for nro in nros:
        ni = n_inv.get(nro) or 0
        no = n_of.get(nro) or 0
        m = meta.get(nro, (None, None, None))
        batch.append(GoldInvitadosVsOfertantes(
            NRO_SICOP=nro, NUMERO_PROCEDIMIENTO=m[0], CEDULA_INSTITUCION=m[1], INSTITUCION=m[2],
            N_INVITADOS=ni, N_OFERTARON=no,
            N_INVITADOS_QUE_NO_OFERTARON=inv_no_of.get(nro) or 0,
            N_OFERTARON_SIN_INVITACION=of_sin_inv.get(nro) or 0,
            TASA_RESPUESTA_PCT=round(no / ni * 100, 1) if ni else None,
            ADJUDICATARIO_FUE_INVITADO="S" if nro in adj_inv else "N",
        ))
        if len(batch) >= BATCH:
            _flush(GoldInvitadosVsOfertantes, batch)
    _flush(GoldInvitadosVsOfertantes, batch)
    print(f"invitados_vs_ofertantes: {len(nros)} procedimientos (SQL 2-vias)", flush=True)


def run(names=None):
    todo = [names] if isinstance(names, str) else (names or list(ALL))
    for n in todo:
        if n in ALL:
            print(f"===== {n} =====", flush=True)
            ALL[n]()


# ===========================================================================
# FASE 0 — regimen de evaluacion normalizado + ctl_deriva
# ===========================================================================

_FACTOR_CATEGORIAS = [
    ("PRECIO", ["precio", "oferta economic", "oferta economica", "menor precio", "factor precio"]),
    ("EXPERIENCIA", ["experiencia"]),
    ("PLAZO_ENTREGA", ["plazo", "tiempo de entrega", "entrega"]),
    ("PYME", ["pyme", "peque", "mediana empresa"]),
    ("AMBIENTAL", ["ambiental", "sustentable", "sostenible"]),
    ("SOCIAL", ["social", "insercion", "discapacidad", "mujeres", "45 an", "genero", "igualdad"]),
    ("LOCAL", ["local", "canton", "provincia", "cercania", "geograf"]),
    ("GARANTIA", ["garant"]),
    ("INNOVACION", ["innovacion", "tecnolog"]),
    ("CERTIFICACION", ["certificaci"]),
    ("CALIDAD", ["calidad"]),
    ("TECNICO", ["tecnico", "tecnica", "especificacion", "requisito"]),
]


def _norm_factor(f):
    import unicodedata

    n = unicodedata.normalize("NFKD", (f or "").lower()).encode("ascii", "ignore").decode()
    for cat, pats in _FACTOR_CATEGORIAS:
        if any(p in n for p in pats):
            return cat
    return "OTRO"


def regimen_evaluacion():
    """Normaliza FACTOR_EVAL a categorias y clasifica el regimen por procedimiento.
    Re-estratifica las metricas de competencia por regimen (plan Fase 0.3)."""
    from .models import (SicopEvaluacionOfertas, GoldRegimenEvaluacion,
                         GoldCompetenciaPorRegimen, GoldCompetenciaPorLinea)
    from collections import defaultdict
    import statistics

    if SicopEvaluacionOfertas.objects.count() == 0:
        print("regimen_evaluacion: sin datos", flush=True)
        return

    print("regimen_evaluacion: agrupando factores...", flush=True)
    proc = defaultdict(list)
    for r in SicopEvaluacionOfertas.objects.values("NRO_SICOP", "FACTOR_EVAL", "PORC_EVAL").iterator():
        proc[r["NRO_SICOP"]].append((r["FACTOR_EVAL"], r["PORC_EVAL"]))

    GoldRegimenEvaluacion.objects.all().delete()
    regime = {}
    batch = []

    def _pct(p):
        try:
            return float(p)
        except (TypeError, ValueError):
            return 0.0

    for nro, facs in proc.items():
        norm = {}
        for f, p in facs:
            c = _norm_factor(f)
            norm[c] = norm.get(c, 0) + _pct(p)
        precio = norm.get("PRECIO", 0)
        if precio >= 99.5:
            reg = "PRECIO_PURO"
        elif precio > 0:
            reg = "MIXTO"
        else:
            reg = "SIN_PRECIO"
        regime[nro] = reg
        norm_sorted = sorted(norm.items(), key=lambda x: -x[1])
        batch.append(GoldRegimenEvaluacion(
            NRO_SICOP=nro, N_FACTORES=len(norm),
            PRECIO_PCT=round(precio, 2) if precio else None, REGIMEN=reg,
            FACTORES_NORMALIZADOS="|".join(c for c, _ in norm_sorted),
            PESOS="|".join(str(round(w, 2)) for _, w in norm_sorted),
        ))
        if len(batch) >= BATCH:
            _flush(GoldRegimenEvaluacion, batch)
    _flush(GoldRegimenEvaluacion, batch)
    from collections import Counter
    print("regimen_evaluacion: %d procedimientos | %s" % (len(regime), dict(Counter(regime.values()))), flush=True)

    # ---- re-estratificar metricas de competencia por regimen ----
    print("regimen_evaluacion: estratificando competencia...", flush=True)
    lines = defaultdict(list)
    for r in GoldCompetenciaPorLinea.objects.values("NRO_SICOP", "NRO_LINEA", "CEDULA_PROVEEDOR",
                                                    "PRECIO_UNITARIO_CRC", "ES_ADJUDICATARIO").iterator():
        lines[(r["NRO_SICOP"], r["NRO_LINEA"])].append(r)

    agg = defaultdict(lambda: {"n": 0, "barato_gana": 0, "caro_gana": 0, "deltas": [], "n_of": []})
    for key, ofs in lines.items():
        reg = regime.get(key[0])
        if not reg:
            continue
        precios = [o["PRECIO_UNITARIO_CRC"] for o in ofs if o["PRECIO_UNITARIO_CRC"] is not None]
        ganadores = [o for o in ofs if o["ES_ADJUDICATARIO"] == "S"]
        if not precios or not ganadores:
            continue
        win = [o["PRECIO_UNITARIO_CRC"] for o in ganadores if o["PRECIO_UNITARIO_CRC"] is not None]
        if not win:
            continue
        cheapest, most = min(precios), max(precios)
        a = agg[reg]
        a["n"] += 1
        a["n_of"].append(len(ofs))
        w = min(win)
        if w == cheapest:
            a["barato_gana"] += 1
        if w == most:
            a["caro_gana"] += 1
        if cheapest:
            a["deltas"].append((w - cheapest) / cheapest)

    GoldCompetenciaPorRegimen.objects.all().delete()
    batch = []
    for reg, a in agg.items():
        batch.append(GoldCompetenciaPorRegimen(
            REGIMEN=reg, N_LINEAS=a["n"],
            PCT_GANA_MAS_BARATO=round(a["barato_gana"] / a["n"] * 100, 1) if a["n"] else None,
            PCT_GANA_MAS_CARO=round(a["caro_gana"] / a["n"] * 100, 1) if a["n"] else None,
            MEDIANA_DELTA_PCT=round(statistics.median(a["deltas"]) * 100, 2) if a["deltas"] else None,
            N_OFERENTES_MEDIANO=statistics.median(a["n_of"]) if a["n_of"] else None,
        ))
    GoldCompetenciaPorRegimen.objects.bulk_create(batch, batch_size=1000)
    for b in batch:
        print("  %s: %d lineas | gana mas barato %.1f%% | gana mas caro %.1f%%" % (
            b.REGIMEN, b.N_LINEAS, b.PCT_GANA_MAS_BARATO or 0, b.PCT_GANA_MAS_CARO or 0), flush=True)


KEY_FIELDS = {
    "adjudicaciones": ["NRO_SICOP", "LINEA", "CEDULA_PROVEEDOR"],
    "adjudicaciones_firme": ["NRO_SICOP", "NRO_ACTO"],
    "carteles": ["NRO_SICOP"],
    "lineas_cartel": ["NRO_SICOP", "NUMERO_LINEA", "NUMERO_PARTIDA"],
    "ofertas": ["NRO_SICOP", "NRO_OFERTA"],
    "lineas_ofertadas": ["NRO_SICOP", "NRO_OFERTA", "NRO_LINEA"],
    "lineas_adjudicadas": ["NRO_SICOP", "NRO_OFERTA", "NRO_LINEA"],
    "lineas_contratadas": ["NRO_SICOP", "NRO_LINEA_CONTRATO"],
    "lineas_recibidas": ["NRO_SICOP", "NRO_CONTRATO", "SECUENCIA"],
    "contratos": ["NRO_CONTRATO", "SECUENCIA"],
    "etapas": ["NRO_SICOP", "CARTEL_SEQ"],
    "garantias": ["nro_garantia", "gara_seq"],
    "evaluacion_ofertas": ["NRO_SICOP", "EVAL_ITEM_SEQNO"],
    "proveedores": ["CEDULA_PROVEEDOR"],
    "instituciones": ["CEDULA"],
    "ordenes_pedido": ["NRO_ORDEN", "LINEA_ORD_PEDIDO"],
    "invitaciones": ["SECUENCIA"],
    "recepciones": ["NRO_SICOP", "NRO_CONTRATO", "NRO_RECEP_DEFINITIVA"],
    "recursos": ["NRO_RECURSO"],
    "remates": ["NRO_SICOP", "CED_PROVEEDOR"],
    "reajustes": ["NRO_SICOP", "NRO_LINEA_CONTRATO", "NUMERO_REAJUSTE"],
}

TRAMPAS = {
    "TAMA\u00d1O_PROVEEDOR": "lleva \u00d1 (buscar TAMANO falla)",
    "SECUENCIA": "enum (98% '00'); no identifica linea de orden - usar LINEA_ORD_PEDIDO",
    "TOTAL_ORDEN": "total de la orden replicado por linea - sumar crudo infla ~3x",
    "CODIGO_IDENTIFICACION": "16 digitos (el cartel habla en 16); oferta en 24 - join por prefijo [:16], nunca igualdad",
    "CODIGO_PRODUCTO": "24 digitos = UNSPSC(8)+ID_CATALOGO(8)+correlativo(8)",
    "CODIGO_PRODUCTO_CL": "16 digitos = EL producto; ausente/parcial 2020/2023/2024 (deriva)",
    "NUMERO_LINEA": "vs NRO_LINEA en ofertadas - normalizar a entero-string",
    "MONTO_UNITARIO": "punto decimal sin separador de miles: 1.000 = uno",
    "MONTO_ADJU_LINEA": "punto decimal sin separador de miles",
    "MONTO_EST": "punto decimal sin separador de miles",
    "PRECIO_UNITARIO_ESTIMADO": "punto decimal sin separador de miles",
    "PRECIO_UNITARIO_OFERTADO": "punto decimal sin separador de miles",
    "PRECIO_UNITARIO": "punto decimal sin separador de miles",
    "NRO_LINEA": "vs NUMERO_LINEA en cartel - normalizar a entero-string",
    "monto_aumentado": "contaminado: numeros de contrato en columna de monto",
    "precio": "contaminado: numeros de contrato en columna de monto (lineas_recibidas)",
    "fecha_rev": "columna que la fuente declara pero NUNCA llena (0% en todos los anios) - no es un hueco real",
    "FECHA_REV": "columna que la fuente declara pero NUNCA llena (0% en todos los anios) - no es un hueco real",
}

# Columnas que la fuente declara en su cabecera pero nunca llena (0% en todos
# los anios): se excluyen del mapa de deriva para no ensuciarlo de '—%'.
COLUMNAS_SIEMPRE_VACIAS = {"fecha_rev", "FECHA_REV"}


def ctl_deriva():
    """Mapa de deriva de esquema por ano: presente + llenado por campo (plan Fase 0.2).
    Regla: ninguna serie multianual se publica sin declarar sus huecos.
    Columnas que la fuente declara pero NUNCA llena (0% en todos sus anios) se
    excluyen del mapa (son columnas muertas, no huecos reales)."""
    import csv
    import os
    from datetime import date
    from django.conf import settings
    from .models import CtlDeriva

    dirs = [settings.SICOP_DATA_DIR]
    rec = getattr(settings, "SICOP_RECOVERY_DIR", None)
    if rec and os.path.isdir(rec):
        dirs.append(rec)

    files = {}
    for d in dirs:
        for fn in os.listdir(d):
            if not fn.endswith(".csv") or fn.startswith("_"):
                continue
            base = fn[:-4]
            if "_" in base:
                setn, _, year = base.rpartition("_")
                if year.isdigit() and len(year) == 4:
                    files.setdefault(setn, {})[year] = os.path.join(d, fn)

    print(f"ctl_deriva: {sum(len(v) for v in files.values())} archivos por escanear", flush=True)
    CtlDeriva.objects.all().delete()
    candidatos = []
    max_pct = {}
    for setn in sorted(files):
        for year in sorted(files[setn]):
            path = files[setn][year]
            hdr = []
            counts = {}
            n = 0
            try:
                with open(path, encoding="utf-8-sig", newline="") as fh:
                    rd = csv.reader(fh)
                    try:
                        hdr = next(rd)
                    except StopIteration:
                        continue
                    counts = {h: 0 for h in hdr}
                    for r in rd:
                        n += 1
                        for i, h in enumerate(hdr):
                            if i < len(r) and r[i].strip():
                                counts[h] += 1
                        if n >= 20000:
                            break
            except Exception as exc:  # noqa: BLE001
                print(f"  error {setn}_{year}: {exc}", flush=True)
                continue
            for h in hdr:
                pct = round(counts[h] / n * 100, 1) if n else 0.0
                candidatos.append((setn, h, year, pct))
                max_pct[(setn, h)] = max(max_pct.get((setn, h), 0.0), pct)
    # solo campos que alguna vez se llenaron (las muertas 0% en todos los anios se omiten)
    vivos = {k for k, v in max_pct.items() if v > 0}
    batch = []
    total = 0
    for setn, h, year, pct in candidatos:
        if (setn, h) not in vivos:
            continue
        batch.append(CtlDeriva(
            CONJUNTO=setn, CAMPO=h, ANIO=year, PRESENTE="S",
            LLENADO_PCT=pct, ES_CLAVE="S" if h in KEY_FIELDS.get(setn, []) else "N",
            TRAMPA=TRAMPAS.get(h), VERIFICADO_EN=date.today().isoformat(),
        ))
        total += 1
        if len(batch) >= BATCH:
            _flush(CtlDeriva, batch)
    _flush(CtlDeriva, batch)
    print(f"ctl_deriva: {total} filas (conjunto x campo x anio) + {len(max_pct) - len(vivos)} columnas muertas excluidas", flush=True)


_UNIDADES = {
    "MONTO": "CRC/USD", "CRC": "CRC", "USD": "USD", "PRECIO": "CRC/USD",
    "CANTIDAD": "unidades", "PCT": "%", "DIAS": "dias", "FECHA": "fecha",
    "PORC": "%", "TC": "tipo de cambio", "VIGENCIA": "fecha", "TOTAL": "CRC/USD",
    "LLENADO": "%", "DIFERENCIA": "dias",
}


def _unidad(campo):
    up = campo.upper()
    for k, v in _UNIDADES.items():
        if k in up:
            return v
    return None


def _regla_join(campo):
    if campo in ("CODIGO_IDENTIFICACION", "CODIGO_PRODUCTO"):
        return "prefijo [:16] contra CODIGO_PRODUCTO_CL / lineas_ofertadas (cartel 16 vs oferta 24)"
    if campo == "CODIGO_PRODUCTO_CL":
        return "16 digitos = UNSPSC(8)+ID_CATALOGO(8): EL producto; ausente 2020/2023/2024"
    if campo == "NUMERO_LINEA":
        return "vs NRO_LINEA en ofertadas/adjudicadas: normalizar a entero-string"
    if campo == "NRO_LINEA":
        return "vs NUMERO_LINEA en cartel: normalizar a entero-string"
    if campo == "NRO_SICOP":
        return "clave del procedimiento en toda la cadena"
    if campo == "NRO_OFERTA":
        return "ofertas x lineas_ofertadas por NRO_SICOP + NRO_OFERTA"
    if campo == "NRO_CONTRATO":
        return "lineas_recibidas no trae cedula: cruzar por NRO_CONTRATO"
    if campo == "LINEA_ORD_PEDIDO":
        return "clave de linea de orden (NO SECUENCIA)"
    if campo == "CEDULA_PROVEEDOR" or campo == "CEDULAPROVEEDOR":
        return "dim_proveedor / todas las tablas"
    return None


def catalogo_campo():
    """Diccionario de datos navegable: tipo, llenado, clave, trampa, unidad, join (plan Fase 1)."""
    from django.db.models import Max
    from django.apps import apps
    from .models import CtlDeriva, CatalogoCampo

    print("catalogo_campo: agregando ctl_deriva...", flush=True)
    rows = list(CtlDeriva.objects.values("CONJUNTO", "CAMPO").annotate(llenado=Max("LLENADO_PCT")))
    CatalogoCampo.objects.all().delete()
    batch = []
    for r in rows:
        tabla = "sicop_" + r["CONJUNTO"]
        campo = r["CAMPO"]
        es_clave = "S" if campo in KEY_FIELDS.get(r["CONJUNTO"], []) else "N"
        trampa = TRAMPAS.get(campo)
        tipo = None
        try:
            model = apps.get_model("sicop", "Sicop" + "".join(w.capitalize() for w in r["CONJUNTO"].split("_")))
            f = model._meta.get_field(campo)
            tipo = f.get_internal_type()
        except Exception:  # noqa: BLE001
            pass
        batch.append(CatalogoCampo(
            TABLA=tabla, CAMPO=campo, TIPO=tipo, ES_CLAVE=es_clave, LLENADO_PCT=r["llenado"],
            TRAMPA=trampa, UNIDAD=_unidad(campo), REGLA_JOIN=_regla_join(campo),
            VERIFICADO_EN=__import__("datetime").date.today().isoformat(),
        ))
        if len(batch) >= BATCH:
            _flush(CatalogoCampo, batch)
    _flush(CatalogoCampo, batch)
    print(f"catalogo_campo: {CatalogoCampo.objects.count()} campos documentados", flush=True)


def expediente_trazabilidad():
    """Reconstruye la trazabilidad de expedientes sobre el corpus COMPLETO
    2020-2026. Antes la generaba el extractor POR ANIO con sobrescritura, asi
    que solo cubria la ventana del ultimo anio procesado (2025-2026, ~18% de
    carteles). Esta derivada la calcula desde las tablas crudas para TODOS los
    procedimientos. NUM_TRAMOS = tramos completados (suma de flags S).
    """
    from .models import (GoldExpedienteTrazabilidad, SicopAdjudicaciones,
                         SicopAdjudicacionesFirme, SicopCarteles, SicopContratos,
                         SicopGarantias, SicopLineasRecibidas,
                         SicopOfertas, SicopRecepciones)

    GoldExpedienteTrazabilidad.objects.all().delete()
    sets = {
        "T_CARTEL": set(SicopCarteles.objects.values_list("NRO_SICOP", flat=True).distinct()),
        "T_OFERTAS": set(SicopOfertas.objects.values_list("NRO_SICOP", flat=True).distinct()),
        "T_ACTO_FIRME": set(SicopAdjudicacionesFirme.objects.values_list("NRO_SICOP", flat=True).distinct()),
        "T_ADJUDICADO": set(SicopAdjudicaciones.objects.values_list("NRO_SICOP", flat=True).distinct()),
        "T_CONTRATO": set(SicopContratos.objects.values_list("NRO_SICOP", flat=True).distinct()),
        "T_GARANTIA": set(SicopGarantias.objects.values_list("NRO_SICOP", flat=True).distinct()),
        "T_RECIBIDO": set(SicopRecepciones.objects.values_list("NRO_SICOP", flat=True).distinct())
        | set(SicopLineasRecibidas.objects.values_list("NRO_SICOP", flat=True).distinct()),
    }
    universe = set()
    for s in sets.values():
        universe |= s
    cartel_meta = {}
    for r in SicopCarteles.objects.values("NRO_SICOP", "NRO_PROCEDIMIENTO", "CEDULA_INSTITUCION").iterator():
        cartel_meta.setdefault(r["NRO_SICOP"], r)

    batch = []
    for nro in sorted(universe):
        m = cartel_meta.get(nro, {})
        flags = {k: "S" if nro in s else "N" for k, s in sets.items()}
        obj = GoldExpedienteTrazabilidad(
            NRO_SICOP=nro, NUMERO_PROCEDIMIENTO=m.get("NRO_PROCEDIMIENTO"),
            CEDULA_INSTITUCION=m.get("CEDULA_INSTITUCION"),
            T_CARTEL=flags["T_CARTEL"], T_OFERTAS=flags["T_OFERTAS"],
            T_ACTO_FIRME=flags["T_ACTO_FIRME"], T_ADJUDICADO=flags["T_ADJUDICADO"],
            T_CONTRATO=flags["T_CONTRATO"], T_GARANTIA=flags["T_GARANTIA"],
            T_RECIBIDO=flags["T_RECIBIDO"],
            NUM_TRAMOS=sum(1 for v in flags.values() if v == "S"),
        )
        batch.append(obj)
        if len(batch) >= BATCH:
            _flush(GoldExpedienteTrazabilidad, batch)
    _flush(GoldExpedienteTrazabilidad, batch)
    print(f"expediente_trazabilidad: {GoldExpedienteTrazabilidad.objects.count()} procedimientos trazados (corpus completo)", flush=True)


ALL = {
    'producto_firma': producto_firma,
    'recursos_desenlace': recursos_desenlace,
    'tiempos_por_etapa': tiempos_por_etapa,
    'precios_identicos': precios_identicos,
    'invitados_vs_ofertantes': invitados_vs_ofertantes,
    'regimen_evaluacion': regimen_evaluacion,
    'ctl_deriva': ctl_deriva,
    'catalogo_campo': catalogo_campo,
    'expediente_trazabilidad': expediente_trazabilidad,
}

