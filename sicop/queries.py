"""Consultas de negocio SICOP compartidas entre la API y el MCP."""
from decimal import Decimal
from datetime import date, datetime

from django.db.models import Count, Q, Sum

from .models import (
    SicopAdjudicaciones,
    SicopEvaluacionOfertas,
    SicopInvitaciones,
    GoldCarteraProveedor,
    GoldDesempenoProveedor,
    GoldDesempenoPorFamilia,
    GoldCatalogoProductos,
    GoldCompetenciaPorLinea,
    GoldExpedienteTrazabilidad,
    GoldCartelesObjetados,
    GoldRepresentanteEmpresas,
    GoldRepresentanteCompetencia,
    GoldExcepcionesPorAdjudicatario,
    GoldSancionesProveedores,
    GoldPrecioPorInstitucion,
)


def to_plain(value):
    """Convierte tipos Django/Decimal/date a JSON-serializable."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "_meta") and not isinstance(value, dict):
        return {f.name: to_plain(getattr(value, f.name)) for f in value._meta.fields if f.name != "id"}
    if isinstance(value, dict):
        return {k: to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(v) for v in value]
    return value


def _tc_del_dia():
    """TC CRC/USD oficial del dia guardado (ctl_bccr_tc). None si no hay."""
    try:
        from .bccr import tc_del_dia
        return tc_del_dia()
    except Exception:  # noqa: BLE001
        return None


def resumen():
    import inspect

    from . import models as m
    from .loader import CORE_SETS, GOLD_SETS

    counts = {}
    for name, model_name in {**CORE_SETS, **GOLD_SETS}.items():
        cls = getattr(m, model_name, None)
        if cls is None:
            continue
        try:
            counts[name] = cls.objects.count()
        except Exception:  # noqa: BLE001
            counts[name] = None
    return {
        "total_tablas": len(counts),
        "tablas": {k: v for k, v in sorted(counts.items())},
    }


def ficha_proveedor(cedula):
    """Ficha completa de un proveedor por cedula."""
    adj = list(
        SicopAdjudicaciones.objects.filter(CEDULA_PROVEEDOR=cedula)
        .values("ANO")
        .annotate(
            n_lineas=Count("id"),
            monto_crc=Sum("MONTO_ADJU_LINEA_CRC"),
            instituciones=Count("CEDULA", distinct=True),
            procedimientos=Count("NRO_SICOP", distinct=True),
        )
        .order_by("ANO")
    )
    perfil = SicopAdjudicaciones.objects.filter(CEDULA_PROVEEDOR=cedula).values("NOMBRE_PROVEEDOR", "PERFIL_PROV").first()
    cartera = list(GoldCarteraProveedor.objects.filter(CEDULA_PROVEEDOR=cedula).order_by("ANIO_EJECUCION"))
    desempeno = list(GoldDesempenoProveedor.objects.filter(CEDULA_PROVEEDOR=cedula))
    familias = list(GoldDesempenoPorFamilia.objects.filter(CEDULA_PROVEEDOR=cedula, MUESTRA_SUFICIENTE="S").order_by("-LINEAS_RECIBIDAS")[:10])
    tc_dia = _tc_del_dia()
    cartera_plain = []
    for c in cartera:
        d = to_plain(c)
        om = d.get("MONTO_OTRAS_MONEDAS_ORIGEN")
        base = float(d.get("MONTO_EJECUTADO_CRC") or 0)
        if tc_dia and om:
            d["EJECUTADO_TOTAL_ESTIMADO_CRC"] = round(base + float(om) * tc_dia, 2)
            d["TC_OFICIAL_DIA_USADO"] = tc_dia
            d["MONTO_OTRAS_MONEDAS_CRC_EST"] = round(float(om) * tc_dia, 2)
        cartera_plain.append(d)
    extra = ["adjudicaciones = captacion; cartera = ejecucion real; NO comparar niveles entre si"]
    if tc_dia:
        extra.append(f"monedas no CRC de cartera convertidas con el TC oficial del dia ({tc_dia}) cuando hay MONTO_OTRAS_MONEDAS_ORIGEN")
    else:
        extra.append("monedas no CRC en cartera sin convertir (sin TC del dia guardado)")
    return to_plain({
        "cedula": cedula,
        "nombre": perfil["NOMBRE_PROVEEDOR"] if perfil else None,
        "perfil": perfil["PERFIL_PROV"] if perfil else None,
        "adjudicaciones_por_anio": adj,
        "cartera_ejecucion_vs_captacion": cartera_plain,
        "tc_oficial_dia": tc_dia,
        "desempeno": desempeno,
        "familias_top": familias,
        "sobre": sobre("mixto: captacion (adjudicaciones) + ejecucion (cartera) + entrega (desempeno)", COBERTURA_CRUCE,
                       extra=extra),
    })


def mercado_familia(familia):
    """Mercado de una familia UNSPSC (8 digitos = prefijo de CODIGO_PRODUCTO_CL):
    adjudicatarios top, ofertas, catalogo y desempeno."""
    adj = list(
        SicopAdjudicaciones.objects.filter(PROD_ID_CL__startswith=familia)
        .values("CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR")
        .annotate(n_lineas=Count("id"), monto_crc=Sum("MONTO_ADJU_LINEA_CRC"))
        .order_by("-monto_crc")[:20]
    )
    ofertas = list(
        GoldCompetenciaPorLinea.objects.filter(CODIGO_PRODUCTO_CL__startswith=familia)
        .values("CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR")
        .annotate(n_ofertas=Count("id"), n_ganadas=Count("id", filter=Q(ES_ADJUDICATARIO="S")))
        .order_by("-n_ofertas")[:20]
    )
    catalogo = list(GoldCatalogoProductos.objects.filter(FAMILIA_UNSPSC=familia).order_by("-LINEAS_EJECUCION")[:20])
    desempeno = list(GoldDesempenoPorFamilia.objects.filter(FAMILIA_UNSPSC=familia).order_by("-LINEAS_RECIBIDAS")[:10])
    return to_plain({
        "familia": familia,
        "adjudicatarios_top_por_monto": adj,
        "oferentes_top": ofertas,
        "productos_top": catalogo,
        "desempeno_top": desempeno,
        "sobre": sobre("captacion (adjudicaciones) + ejecucion por lineas (desempeno)", COBERTURA_CRUCE,
                       extra=["adjudicatarios por monto usa PROD_ID_CL (16) y cubre solo 2021/2022/2025/2026",
                              "oferentes top limitado a la cobertura del cruce 62,6%"]),
    })


def competencia_procedimiento(nro_sicop):
    rows = GoldCompetenciaPorLinea.objects.filter(NRO_SICOP=nro_sicop).order_by("NRO_LINEA")
    return to_plain({"nro_sicop": nro_sicop, "lineas": list(rows),
                     "sobre": sobre("captacion (ofertas x adjudicaciones)", COBERTURA_CRUCE,
                                    extra=["la ausencia de registro no es ausencia del hecho (cobertura 62,6%)"])})


def producto(codigo):
    rows = GoldCatalogoProductos.objects.filter(CODIGO_PRODUCTO_CL=codigo)
    return to_plain(list(rows))


def expediente(nro_sicop):
    row = GoldExpedienteTrazabilidad.objects.filter(NRO_SICOP=nro_sicop).first()
    return to_plain(row)


def adjudicaciones(cedula=None, institucion=None, anio=None, nro_sicop=None, objeto=None, limit=50):
    qs = SicopAdjudicaciones.objects.all()
    if cedula:
        qs = qs.filter(CEDULA_PROVEEDOR=cedula)
    if institucion:
        qs = qs.filter(CEDULA=institucion)
    if anio:
        qs = qs.filter(ANO=str(anio))
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    if objeto:
        qs = qs.filter(OBJETO_GASTO=objeto)
    return to_plain(list(qs[:limit]))


def carteles_objetados(institucion=None, limit=100):
    qs = GoldCartelesObjetados.objects.all()
    if institucion:
        qs = qs.filter(CEDULA_INSTITUCION=institucion)
    return to_plain(list(qs.order_by("-MONTO_EST")[:limit]))


def representantes(limit=50):
    return to_plain(list(GoldRepresentanteEmpresas.objects.order_by("-N_ADJUDICACIONES")[:limit]))


def representante_competencia(cedula_representante=None, limit=100):
    qs = GoldRepresentanteCompetencia.objects.all()
    if cedula_representante:
        qs = qs.filter(CEDULA_REPRESENTANTE=cedula_representante)
    return to_plain(list(qs.order_by("-N_OFERENTES_TOTAL")[:limit]))


def excepciones(cedula=None, limit=100):
    qs = GoldExcepcionesPorAdjudicatario.objects.all()
    if cedula:
        qs = qs.filter(CEDULA_PROVEEDOR=cedula)
    return to_plain(list(qs.order_by("-MONTO_CRC")[:limit]))


def sanciones(cedula=None):
    qs = GoldSancionesProveedores.objects.all()
    if cedula:
        qs = qs.filter(CEDULAS_PROVEEDOR__icontains=cedula)
    return to_plain(list(qs))


def precios_institucion(familia=None, marca=None, anio=None, limit=100):
    qs = GoldPrecioPorInstitucion.objects.all()
    if familia:
        qs = qs.filter(FAMILIA_UNSPSC=familia)
    if marca:
        qs = qs.filter(MARCA__icontains=marca)
    if anio:
        qs = qs.filter(ANIO=str(anio))
    return to_plain(list(qs.order_by("-RATIO_MAX_MIN")[:limit]))


# ---- sobre (envelope) requerido por el plan §5.4 ----
COBERTURA_CRUCE = 0.626
CAVEATS_BASE = [
    "cobertura del cruce oferta x oferente: 62,6% (1 mes 8%, acumulado)",
    "2026 parcial (corte 2026-08-25); '2026' en adjudicaciones/contratos/recepciones es actividad observada, no procedimientos nacidos 2026",
    "conversiones de moneda usan TIPO_CAMBIO_CRC de la propia fila; monedas no CRC convertidas con el TC oficial del dia cuando esta guardado (ctl_bccr_tc)",
    "ninguna serie multianual se publica sin declarar sus huecos: consultar /api/v1/ctl-deriva (deriva por anio)",
    "lineas_* / ofertas / proveedores / recepciones / recursos / ordenes_pedido en carga (recuperacion desde Observatorio)",
]


def sobre(nivel_medicion="no_aplica", cobertura=None, moneda=None, extra=None):
    caveats = list(CAVEATS_BASE)
    if extra:
        caveats.extend(extra)
    return {
        "schema_version": 1,
        "nivel_medicion": nivel_medicion,
        "cobertura_cruce": cobertura,
        "moneda": moneda or "CRC | USD | EUR | JPY | GBP - nunca sumar sin convertir",
        "caveats": caveats,
    }


def _attached(data, **kwargs):
    if isinstance(data, dict):
        data["sobre"] = sobre(**kwargs)
    return data


def cara_a_cara(cedula_a, cedula_b, familia=None):
    """Comparacion directa de dos proveedores (plan: cara_a_cara)."""
    from collections import defaultdict

    qs = GoldCompetenciaPorLinea.objects.all()
    if familia:
        qs = qs.filter(CODIGO_PRODUCTO_CL__startswith=familia)
    rows = list(qs.values("NRO_SICOP", "NRO_LINEA", "CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR",
                          "PRECIO_UNITARIO_CRC", "ES_ADJUDICATARIO", "CODIGO_PRODUCTO_CL", "MES_PUBLICACION"))

    lines = defaultdict(dict)  # (nro_sicop, linea) -> {cedula: row}
    for r in rows:
        lines[(r["NRO_SICOP"], r["NRO_LINEA"])][r["CEDULA_PROVEEDOR"]] = r

    shared = []
    for key, ofs in lines.items():
        if cedula_a in ofs and cedula_b in ofs:
            shared.append((key, ofs[cedula_a], ofs[cedula_b]))

    a_wins = b_wins = 0
    a_cheaper = b_cheaper = 0
    deltas = []
    familias = defaultdict(lambda: {"A": 0, "B": 0})
    for key, ra, rb in shared:
        if ra["ES_ADJUDICATARIO"] == "S":
            a_wins += 1
        if rb["ES_ADJUDICATARIO"] == "S":
            b_wins += 1
        pa, pb = ra["PRECIO_UNITARIO_CRC"], rb["PRECIO_UNITARIO_CRC"]
        if pa is not None and pb is not None and pb:
            if pa < pb:
                a_cheaper += 1
            elif pb < pa:
                b_cheaper += 1
            deltas.append((pa - pb) / pb)
        fam = (ra.get("CODIGO_PRODUCTO_CL") or "")[:8]
        if fam:
            familias[fam]["A"] += 1
            familias[fam]["B"] += 1

    def per(ced):
        adj = SicopAdjudicaciones.objects.filter(CEDULA_PROVEEDOR=ced)
        agg = adj.aggregate(n=Count("id"), monto=Sum("MONTO_ADJU_LINEA_CRC"))
        car = GoldCarteraProveedor.objects.filter(CEDULA_PROVEEDOR=ced)
        ejec = car.aggregate(m=Sum("MONTO_EJECUTADO_CRC"))
        return {"cedula": ced, "adjudicaciones": {"lineas": agg["n"], "monto_crc": agg["monto"]},
                "ejecucion_total_crc": ejec["m"], "anios_cartera": car.count()}

    import statistics

    result = {
        "cedula_a": cedula_a,
        "cedula_b": cedula_b,
        "familia": familia,
        "lineas_ambos_ofertaron": len(shared),
        "victorias_a": a_wins,
        "victorias_b": b_wins,
        "veces_mas_barato_a": a_cheaper,
        "veces_mas_barato_b": b_cheaper,
        "delta_precio_mediano_A_vs_B_pct": round(statistics.median(deltas) * 100, 2) if deltas else None,
        "familias_compartidas": {f: v for f, v in sorted(familias.items(), key=lambda x: -x[1]["A"])[:15]},
        "perfil_a": per(cedula_a),
        "perfil_b": per(cedula_b),
        "sobre": sobre("captacion + ejecucion", COBERTURA_CRUCE,
                       extra=["cara_a_cara limitado a la cobertura del cruce 62,6%"]),
    }
    return result


def producto_historia(codigo_cl):
    """Historia de un producto (codigo CL 16): catalog, secuencia de precios ofertados, adjudicaciones e instituciones."""
    import statistics

    catalogo = list(GoldCatalogoProductos.objects.filter(CODIGO_PRODUCTO_CL=codigo_cl))
    ofertas = list(
        GoldCompetenciaPorLinea.objects.filter(CODIGO_PRODUCTO_CL=codigo_cl)
        .values("MES_PUBLICACION", "PRECIO_UNITARIO_CRC", "ES_ADJUDICATARIO", "NOMBRE_PROVEEDOR")
    )
    por_anio = {}
    for o in ofertas:
        a = (o["MES_PUBLICACION"] or "")[:4]
        d = por_anio.setdefault(a, [])
        d.append(o)
    serie = []
    for anio in sorted(por_anio):
        vals = [o["PRECIO_UNITARIO_CRC"] for o in por_anio[anio] if o["PRECIO_UNITARIO_CRC"] is not None]
        n_ganadas = sum(1 for o in por_anio[anio] if o["ES_ADJUDICATARIO"] == "S")
        serie.append({
            "anio": anio,
            "n_ofertas": len(por_anio[anio]),
            "n_adjudicaciones": n_ganadas,
            "precio_crc_mediano": statistics.median(vals) if vals else None,
            "precio_crc_min": min(vals) if vals else None,
            "precio_crc_max": max(vals) if vals else None,
        })

    adj = list(
        SicopAdjudicaciones.objects.filter(PROD_ID_CL=codigo_cl)
        .values("ANO").annotate(n_lineas=Count("id"), monto_crc=Sum("MONTO_ADJU_LINEA_CRC")).order_by("ANO")
    )
    proveedores = list(
        SicopAdjudicaciones.objects.filter(PROD_ID_CL=codigo_cl)
        .values("CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR")
        .annotate(n_lineas=Count("id"), monto_crc=Sum("MONTO_ADJU_LINEA_CRC"))
        .order_by("-monto_crc")[:10]
    )
    precio_inst = list(GoldPrecioPorInstitucion.objects.filter(CODIGO_PRODUCTO_CL=codigo_cl))
    return to_plain({
        "codigo_cl": codigo_cl,
        "catalogo": catalogo,
        "serie_precios_ofertados": serie,
        "adjudicaciones_por_anio": adj,
        "proveedores_top": proveedores,
        "precio_por_institucion": precio_inst,
        "sobre": sobre("captacion (adjudicaciones) + ofertas", COBERTURA_CRUCE,
                       extra=["CL ausente en 2020/2023/2024: serie incompleta esos anios",
                              "precios simbólicos (<=1 CRC) y digitaciones contaminan min/max - mirar mediana"]),
    })


def campo_buscar(termino, limit=20):
    """Busqueda en el catalogo de productos y proveedores (plan: campo_buscar)."""
    from django.db.models import Q

    q = Q()
    for field in ("DESCRIPCION", "MARCA", "MODELO"):
        q |= Q(**{field + "__icontains": termino})
    productos = list(GoldCatalogoProductos.objects.filter(q).order_by("-LINEAS_EJECUCION")[:limit])
    prov = (
        SicopAdjudicaciones.objects.filter(NOMBRE_PROVEEDOR__icontains=termino)
        .values("CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR")
        .annotate(lineas=Count("id"), monto_crc=Sum("MONTO_ADJU_LINEA_CRC"))
        .order_by("-monto_crc")[:limit]
    )
    inst = (
        SicopAdjudicaciones.objects.filter(INSTITUCION__icontains=termino)
        .values("CEDULA", "INSTITUCION")
        .annotate(lineas=Count("id"), monto_crc=Sum("MONTO_ADJU_LINEA_CRC"))
        .order_by("-monto_crc")[:limit]
    )
    return to_plain({
        "termino": termino,
        "productos": productos,
        "proveedores": list(prov),
        "instituciones": list(inst),
        "sobre": sobre("no aplica"),
    })


def perdidas_baratas(cedula=None, familia=None, limit=200):
    """Lineas donde un proveedor oferto mas barato que el ganador y perdio (cola de revision)."""
    from collections import defaultdict

    qs = GoldCompetenciaPorLinea.objects.all()
    if familia:
        qs = qs.filter(CODIGO_PRODUCTO_CL__startswith=familia)
    if cedula:
        qs = qs.filter(CEDULA_PROVEEDOR=cedula)
    rows = list(qs.values("NRO_SICOP", "NRO_LINEA", "CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR",
                          "PRECIO_UNITARIO_CRC", "ES_ADJUDICATARIO", "CODIGO_PRODUCTO_CL", "MES_PUBLICACION"))

    lines = defaultdict(list)
    for r in rows:
        lines[(r["NRO_SICOP"], r["NRO_LINEA"])].append(r)

    out = []
    for key, ofs in lines.items():
        ganadores = [o for o in ofs if o["ES_ADJUDICATARIO"] == "S"]
        if not ganadores:
            continue
        precio_ganador = min(g["PRECIO_UNITARIO_CRC"] for g in ganadores if g["PRECIO_UNITARIO_CRC"] is not None)
        if precio_ganador is None:
            continue
        for o in ofs:
            if o["ES_ADJUDICATARIO"] != "S" and o["PRECIO_UNITARIO_CRC"] is not None \
               and o["PRECIO_UNITARIO_CRC"] < precio_ganador:
                out.append({
                    "nro_sicop": o["NRO_SICOP"], "linea": o["NRO_LINEA"],
                    "proveedor": o["NOMBRE_PROVEEDOR"], "cedula": o["CEDULA_PROVEEDOR"],
                    "precio_ofertado_crc": o["PRECIO_UNITARIO_CRC"],
                    "precio_ganador_crc": precio_ganador,
                    "delta_vs_ganador_pct": round((precio_ganador - o["PRECIO_UNITARIO_CRC"]) / precio_ganador * 100, 2),
                    "mes": o["MES_PUBLICACION"],
                })
    out.sort(key=lambda x: -x["delta_vs_ganador_pct"])
    return {
        "perdidas_baratas": out[:limit],
        "total": len(out),
        "sobre": sobre("captacion (ofertas x adjudicaciones)", COBERTURA_CRUCE,
                       extra=["cola de revision, no conclusion: el motivo vive en el acta de estudio tecnico"]),
    }


def regimen_evaluacion(nro_sicop):
    """Regimen de evaluacion de un procedimiento (evaluacion_ofertas)."""
    rows = list(SicopEvaluacionOfertas.objects.filter(NRO_SICOP=nro_sicop).order_by("EVAL_ITEM_SEQNO"))
    return to_plain({"nro_sicop": nro_sicop, "factores": rows})


# ---- conjuntos recuperados (ofertas, lineas, proveedores, recepciones, recursos, ordenes, invitaciones) ----

def invitaciones_procedimiento(nro_sicop, limit=500):
    """Quien fue invitado a un procedimiento (contratacion directa: la institucion elige a quien invitar)."""
    rows = list(SicopInvitaciones.objects.filter(NRO_SICOP=nro_sicop).order_by("FECHA_INVITACION")[:limit])
    return to_plain({"nro_sicop": nro_sicop, "invitados": rows})


def invitaciones_proveedor(cedula, limit=200):
    """Procedimientos donde un proveedor fue invitado (plan: invitaciones_pendientes)."""
    rows = list(
        SicopInvitaciones.objects.filter(CEDULA_PROVEEDOR=cedula)
        .values("NRO_SICOP", "NUMERO_PROCEDIMIENTO", "CED_INSTITUCION", "INSTITUCION", "FECHA_INVITACION", "MES_PUBLICACION")
        .order_by("-FECHA_INVITACION")[:limit]
    )
    return to_plain({"cedula": cedula, "invitaciones": rows, "total": len(rows)})


def invitados_vs_ofertantes(nro_sicop):
    """Direccionamiento ex-ante: cuantos invitados vs cuantos ofertaron en un procedimiento."""
    invitados = list(SicopInvitaciones.objects.filter(NRO_SICOP=nro_sicop))
    ofertaron = list(GoldCompetenciaPorLinea.objects.filter(NRO_SICOP=nro_sicop))
    inv_ceds = {i.CEDULA_PROVEEDOR for i in invitados}
    of_ceds = {o.CEDULA_PROVEEDOR for o in ofertaron}
    return to_plain({
        "nro_sicop": nro_sicop,
        "n_invitados": len(inv_ceds),
        "n_ofertaron": len(of_ceds),
        "invitados_que_no_ofertaron": len(inv_ceds - of_ceds),
        "oferto_sin_invitacion": len(of_ceds - inv_ceds),
        "tasa_respuesta_pct": round(len(of_ceds & inv_ceds) / len(inv_ceds) * 100, 1) if inv_ceds else None,
    })


def lineas_procedimiento(nro_sicop):
    """Cadena de linea de un procedimiento: lo que se pidio (cartel), se oferto y se adjudico."""
    from .models import SicopLineasCartel, SicopLineasOfertadas, SicopLineasAdjudicadas, SicopLineasContratadas, SicopLineasRecibidas

    def rows(model):
        return list(model.objects.filter(NRO_SICOP=nro_sicop)[:1000])

    return to_plain({
        "nro_sicop": nro_sicop,
        "lineas_cartel": rows(SicopLineasCartel),
        "lineas_ofertadas": rows(SicopLineasOfertadas),
        "lineas_adjudicadas": rows(SicopLineasAdjudicadas),
        "lineas_contratadas": rows(SicopLineasContratadas),
        "lineas_recibidas": rows(SicopLineasRecibidas),
    })


def proveedor_dim(cedula):
    """Registro del proveedor (dimension): tipo, tamano, zona, fechas de constitucion."""
    from .models import SicopProveedores

    row = SicopProveedores.objects.filter(CEDULA_PROVEEDOR=cedula).first()
    return to_plain(row)


def ordenes_proveedor(cedula, anio=None, limit=1000):
    """Ordenes de pedido de un proveedor (nivel EJECUCION). Total CRC sumable;
    monedas no CRC convertidas con el TC oficial del dia cuando esta disponible."""
    from .models import SicopOrdenesPedido

    qs = SicopOrdenesPedido.objects.filter(CEDULAPROVEEDOR=cedula)
    if anio:
        qs = qs.filter(FECHA_ELABORACION_ORDEN__year=anio)
    rows = list(qs.order_by("-FECHA_ELABORACION_ORDEN")[:limit])
    tc_dia = _tc_del_dia()
    n_crc = sum(1 for r in rows if r.MONEDA_ORDEN == "CRC")
    otras = [r for r in rows if (r.MONEDA_ORDEN or "") not in ("", "CRC")]
    n_otras = len(otras)
    total_crc = sum((r.TOTAL_ORDEN or 0) for r in rows if r.MONEDA_ORDEN == "CRC")
    total_otras_convertido = (float(sum((r.TOTAL_ORDEN or 0) for r in otras)) * tc_dia) if (tc_dia and n_otras) else None
    ordenes_plain = []
    for r in rows:
        d = to_plain(r)
        if tc_dia and (r.MONEDA_ORDEN or "") not in ("", "CRC") and r.TOTAL_ORDEN:
            d["TOTAL_ORDEN_CRC_EST"] = round(float(r.TOTAL_ORDEN) * tc_dia, 2)
        ordenes_plain.append(d)
    extra = ["TOTAL_ORDEN esta replicado por linea: totales solo deduplicados por NRO_ORDEN"]
    if tc_dia and n_otras:
        extra.append(f"monedas no CRC convertidas con el TC oficial del dia ({tc_dia}) -> TOTAL_ORDEN_CRC_EST por orden y total_otras_monedas_crc_est")
    elif n_otras:
        extra.append("monedas no CRC sin convertir (sin TC del dia guardado)")
    return to_plain({
        "cedula": cedula,
        "anio": anio,
        "n_ordenes_muestra": len(rows),
        "n_crc": n_crc,
        "n_otras_monedas": n_otras,
        "total_orden_crc_muestra": total_crc,
        "total_otras_monedas_crc_est": round(total_otras_convertido, 2) if total_otras_convertido is not None else None,
        "total_orden_crc_estimado_muestra": round(total_crc + total_otras_convertido, 2) if total_otras_convertido is not None else total_crc,
        "tc_oficial_dia": tc_dia,
        "ordenes": ordenes_plain,
        "sobre": sobre("ejecucion (ordenes de pedido)", None, extra=extra),
    })


def recursos_procedimiento(nro_sicop):
    """Recursos de objecion de un procedimiento con su desenlace."""
    from .models import SicopRecursos

    rows = list(SicopRecursos.objects.filter(NRO_SICOP=nro_sicop))
    return to_plain({"nro_sicop": nro_sicop, "recursos": rows})
