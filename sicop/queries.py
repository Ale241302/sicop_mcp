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


def f_norm_py(texto):
    """Normaliza texto en Python como la funcion SQL f_norm: minusculas, sin
    acentos, espacios simples. Usada para normalizar el input del resolver."""
    import unicodedata

    s = (texto or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(c))
    return " ".join(s.split())


def _tc_del_dia():
    """TC CRC/USD oficial del dia guardado (ctl_bccr_tc). None si no hay."""
    try:
        from .bccr import tc_del_dia
        return tc_del_dia()
    except Exception:  # noqa: BLE001
        return None


def resolver_procedimientos(nros):
    """Mapa NRO_SICOP -> label humano {NRO_PROCEDIMIENTO, TIPO_PROCEDIMIENTO,
    INSTITUCION, PROCEDIMIENTO_LABEL}. Usado por el MCP para que el chat muestre
    el numero de procedimiento y la institucion en vez del codigo crudo."""
    from .models import SicopCarteles, SicopInstituciones

    nros = [str(n) for n in nros if n]
    if not nros:
        return {}
    cart = {}
    for r in SicopCarteles.objects.filter(NRO_SICOP__in=nros).values(
            "NRO_SICOP", "NRO_PROCEDIMIENTO", "CEDULA_INSTITUCION", "TIPO_PROCEDIMIENTO"):
        cart.setdefault(r["NRO_SICOP"], r)
    ceds = {r.get("CEDULA_INSTITUCION") for r in cart.values() if r.get("CEDULA_INSTITUCION")}
    inst = {}
    if ceds:
        for r in SicopInstituciones.objects.filter(CEDULA__in=ceds).values("CEDULA", "NOMBRE_INSTITUCION"):
            inst.setdefault(r["CEDULA"], r["NOMBRE_INSTITUCION"])
    out = {}
    for nro, r in cart.items():
        nombre_inst = inst.get(r.get("CEDULA_INSTITUCION")) or r.get("CEDULA_INSTITUCION")
        nproc = r.get("NRO_PROCEDIMIENTO")
        out[nro] = {
            "NRO_PROCEDIMIENTO": nproc,
            "TIPO_PROCEDIMIENTO": r.get("TIPO_PROCEDIMIENTO"),
            "INSTITUCION": nombre_inst,
            "PROCEDIMIENTO_LABEL": f"{nproc} · {nombre_inst}" if nproc else (nombre_inst or nro),
        }
    return out


def resolver_proveedores(cedulas):
    """Mapa CEDULA_PROVEEDOR -> NOMBRE_PROVEEDOR (label humano)."""
    from .models import SicopProveedores

    cedulas = [str(c) for c in cedulas if c]
    if not cedulas:
        return {}
    out = {}
    for r in (SicopProveedores.objects.filter(CEDULA_PROVEEDOR__in=cedulas)
              .values("CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR")):
        out.setdefault(r["CEDULA_PROVEEDOR"], r["NOMBRE_PROVEEDOR"])
    return out


def resolver_instituciones(cedulas):
    """Mapa CEDULA_INSTITUCION -> NOMBRE_INSTITUCION (label humano)."""
    from .models import SicopInstituciones

    cedulas = [str(c) for c in cedulas if c]
    if not cedulas:
        return {}
    out = {}
    for r in (SicopInstituciones.objects.filter(CEDULA__in=cedulas)
              .values("CEDULA", "NOMBRE_INSTITUCION")):
        out.setdefault(r["CEDULA"], r["NOMBRE_INSTITUCION"])
    return out


def resolver(texto, limit=5, tipos=None):
    """FASE B: resuelve texto libre -> entidades (proveedor/institucion) por
    alias exacto + similitud trigram sobre nombre_norm y alias_norm.

    Devuelve [{tipo, cedula, nombre, score, via}]. Tolerante a mayusculas,
    acentos y typos. Si el texto es una cedula limpia, devuelve el match directo."""
    import re

    from .models import DimEntidad

    t = (texto or "").strip()
    if not t:
        return []

    # cedula directa (9-12 digitos)
    if re.fullmatch(r"\d{9,12}", t):
        qs = DimEntidad.objects.filter(cedula=t)
        if tipos:
            qs = qs.filter(tipo__in=tipos)
        r = qs.values("tipo", "cedula", "nombre").first()
        if r:
            return [{"tipo": r["tipo"], "cedula": r["cedula"],
                     "nombre": r["nombre"], "score": 1.0, "via": "cedula"}]
        return []

    t_norm = f_norm_py(t)
    qs = DimEntidad.objects.filter(activo=True)
    if tipos:
        qs = qs.filter(tipo__in=tipos)

    # 1) alias o nombre exactos (normalizado)
    r = qs.filter(nombre_norm=t_norm).values("tipo", "cedula", "nombre").first()
    if not r:
        r = (qs.extra(
            where=["%s = ANY(alias_norm)"],
            params=[t_norm],
        ).values("tipo", "cedula", "nombre").first())
    if r:
        return [{"tipo": r["tipo"], "cedula": r["cedula"],
                 "nombre": r["nombre"], "score": 1.0, "via": "alias"}]

    # 2) similitud trigram sobre nombre_norm
    rows = list(qs.extra(
        select={"score": "similarity(nombre_norm, %s)"},
        select_params=[t_norm],
        where=["similarity(nombre_norm, %s) >= 0.35"],
        params=[t_norm],
        order_by=["-score"],
    ).values("tipo", "cedula", "nombre", "score")[:limit])

    # 3) ampliar con similitud sobre alias_norm (unnest)
    rows2 = list(qs.extra(
        select={"score": "(SELECT max(similarity(a, %s)) FROM unnest(alias_norm) a)"},
        select_params=[t_norm],
        where=["EXISTS (SELECT 1 FROM unnest(alias_norm) a WHERE similarity(a, %s) >= 0.35)"],
        params=[t_norm],
    ).values("tipo", "cedula", "nombre", "score").order_by("-score")[:limit])
    seen = {(r["tipo"], r["cedula"]) for r in rows}
    rows += [r for r in rows2 if (r["tipo"], r["cedula"]) not in seen]

    out = []
    for r in rows[:limit]:
        out.append({"tipo": r["tipo"], "cedula": r["cedula"],
                    "nombre": r["nombre"],
                    "score": round(float(r.get("score") or 0), 3), "via": "similitud"})
    return out


def _resolver_cedula(texto, tipos=None):
    """FASE B: si `texto` es una cedula numerica la devuelve tal cual; si es
    texto libre, la resuelve a la mejor cedula (proveedor o institucion segun
    tipos). Devuelve (cedula, tipo) o (None, None) si no resuelve."""
    import re

    t = (texto or "").strip()
    if not t:
        return None, None
    if re.fullmatch(r"\d{9,12}", t):
        return t, None
    r = resolver(t, limit=1, tipos=tipos)
    if r:
        return r[0]["cedula"], r[0]["tipo"]
    return None, None


def resumen():
    """Conteos por tabla, cacheados ~6h. Usa pg_class.reltuples (estimación
    inmediata del planner) en vez de count() sobre tablas gigantes."""
    from django.core.cache import cache

    clave = "sicop:resumen:v1"
    try:
        cached = cache.get(clave)
        if cached:
            return cached
    except Exception:  # noqa: BLE001  (Redis caido -> computar sin cache)
        cached = None

    from . import models as m
    from .loader import CORE_SETS, GOLD_SETS

    from django.db import connection

    # estimaciones del planner desde pg_class (barato, ~0ms para 50 tablas)
    reltuples = {}
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT relname, reltuples::bigint FROM pg_class "
                "WHERE relkind='r' AND relname = ANY(%s)",
                [list(getattr(cls, "_meta").db_table for cls in
                      {getattr(m, mn, None) for mn in {**CORE_SETS, **GOLD_SETS}.values()}
                      if cls is not None)],
            )
            reltuples = {r[0]: r[1] for r in cur.fetchall()}
    except Exception:  # noqa: BLE001
        reltuples = {}

    counts = {}
    for name, model_name in {**CORE_SETS, **GOLD_SETS}.items():
        cls = getattr(m, model_name, None)
        if cls is None:
            continue
        try:
            counts[name] = reltuples.get(cls._meta.db_table)
        except Exception:  # noqa: BLE001
            counts[name] = None
    out = {
        "total_tablas": len(counts),
        "tablas": {k: v for k, v in sorted(counts.items())},
    }
    try:
        cache.set(clave, out, 6 * 3600)
    except Exception:  # noqa: BLE001
        pass
    return out


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
        extra.append("monedas no CRC en cartera sin convertir (fallo consultar el TC del dia)")
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
    if row:
        return to_plain(row)
    # fallback: la trazabilidad derivada solo cubre 2025-2026 (~18% de carteles);
    # si el procedimiento no esta, contar presencia directo desde tablas crudas.
    from .models import (SicopAdjudicaciones, SicopAdjudicacionesFirme, SicopCarteles,
                         SicopContratos, SicopOfertas, SicopOrdenesPedido,
                         SicopRecepciones)
    return to_plain({
        "NRO_SICOP": nro_sicop,
        "FALLBACK_CRUDO": True,
        "cartel": SicopCarteles.objects.filter(NRO_SICOP=nro_sicop).count(),
        "ofertas": SicopOfertas.objects.filter(NRO_SICOP=nro_sicop).count(),
        "adjudicacion_firme": SicopAdjudicacionesFirme.objects.filter(NRO_SICOP=nro_sicop).count(),
        "adjudicacion": SicopAdjudicaciones.objects.filter(NRO_SICOP=nro_sicop).count(),
        "contratos": SicopContratos.objects.filter(NRO_SICOP=nro_sicop).count(),
        "ordenes": SicopOrdenesPedido.objects.filter(NRO_SICOP=nro_sicop).count(),
        "recepciones": SicopRecepciones.objects.filter(NRO_SICOP=nro_sicop).count(),
        "nota": "la trazabilidad derivada solo cubre 2025-2026; conteos directos desde tablas crudas",
    })


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
    "conversiones de moneda usan TIPO_CAMBIO_CRC de la propia fila; ordenes no-CRC convertidas con TC implicito del mes (fallback TC del dia)",
    "MES_PUBLICACION NO es el mes de publicacion real: es el mes del primer ZIP donde se vio la fila (dedup del extractor). NO usar para series temporales/estacionalidad; los datos de un procedimiento pueden vivir bajo meses anteriores.",
    "ninguna serie multianual se publica sin declarar sus huecos: consultar /api/v1/ctl-deriva (deriva por anio)",
    "lineas_* / ofertas / proveedores / recepciones / recursos / ordenes_pedido en carga (recuperacion desde Observatorio)",
    "catalogo_productos.LINEAS_EJECUCION sale solo de lineas_contratadas+lineas_recibidas (no incluye ordenes): SKU con ejecucion sin adjudicacion respaldante son huecos de la fuente, no errores",
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
    """Busqueda en el catalogo de productos y proveedores (plan: campo_buscar).
    Usa f_norm() (inmutable, indexada por trigram) para tolerar mayusculas/
    acentos y bajar a <200ms."""
    from django.db.models import Func, Q

    termino_norm = "".join(
        c for c in (termino or "").strip().lower() if c.isalnum() or c == " "
    ).strip()
    if not termino_norm:
        return to_plain({
            "termino": termino,
            "productos": [],
            "proveedores": [],
            "instituciones": [],
        })

    # coincidencia de substring sobre la expresion indexada f_norm(col) LIKE '%term%'
    prov = (
        SicopAdjudicaciones.objects.annotate(
            prov_norm=Func("NOMBRE_PROVEEDOR", function="f_norm")
        )
        .filter(prov_norm__contains=termino_norm)
        .values("CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR")
        .annotate(lineas=Count("id"), monto_crc=Sum("MONTO_ADJU_LINEA_CRC"))
        .order_by("-monto_crc")[:limit]
    )
    inst = (
        SicopAdjudicaciones.objects.annotate(
            inst_norm=Func("INSTITUCION", function="f_norm")
        )
        .filter(inst_norm__contains=termino_norm)
        .values("CEDULA", "INSTITUCION")
        .annotate(lineas=Count("id"), monto_crc=Sum("MONTO_ADJU_LINEA_CRC"))
        .order_by("-monto_crc")[:limit]
    )
    productos = list(
        GoldCatalogoProductos.objects.annotate(
            desc_norm=Func("DESCRIPCION", function="f_norm")
        )
        .filter(desc_norm__contains=termino_norm)
        .order_by("-LINEAS_EJECUCION")[:limit]
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
    """Quien fue invitado a un procedimiento (contratacion directa: la institucion elige a quien invitar). Usa gold_invitaciones (dedup, indices)."""
    from django.db import connection

    rows = []
    try:
        with connection.cursor() as cur:
            cur.execute(
                'SELECT "NRO_SICOP","NUMERO_PROCEDIMIENTO","CEDULA_PROVEEDOR","NOMBRE_PROVEEDOR",'
                '"CED_INSTITUCION","INSTITUCION","FECHA_INVITACION" FROM sicop.gold_invitaciones '
                'WHERE "NRO_SICOP"=%s ORDER BY "FECHA_INVITACION" LIMIT %s',
                [nro_sicop, limit])
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:  # noqa: BLE001  (gold_invitaciones ausente -> cruda)
        rows = list(SicopInvitaciones.objects.filter(NRO_SICOP=nro_sicop).order_by("FECHA_INVITACION")[:limit])
    return to_plain({"nro_sicop": nro_sicop, "invitados": rows})


def invitaciones_proveedor(cedula, limit=200):
    """Procedimientos donde un proveedor fue invitado (plan: invitaciones_pendientes).
    Usa gold_invitaciones (indice idx_ginv_ced) en vez de la cruda de 62M filas."""
    from django.db import connection

    rows = []
    try:
        with connection.cursor() as cur:
            cur.execute(
                'SELECT "NRO_SICOP","NUMERO_PROCEDIMIENTO","CED_INSTITUCION","INSTITUCION",'
                '"FECHA_INVITACION" FROM sicop.gold_invitaciones '
                'WHERE "CEDULA_PROVEEDOR"=%s ORDER BY "FECHA_INVITACION" DESC LIMIT %s',
                [cedula, limit])
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:  # noqa: BLE001
        rows = list(
            SicopInvitaciones.objects.filter(CEDULA_PROVEEDOR=cedula)
            .values("NRO_SICOP", "NUMERO_PROCEDIMIENTO", "CED_INSTITUCION", "INSTITUCION", "FECHA_INVITACION", "MES_PUBLICACION")
            .order_by("-FECHA_INVITACION")[:limit]
        )
    return to_plain({"cedula": cedula, "invitaciones": rows, "total": len(rows)})


def invitados_vs_ofertantes(nro_sicop):
    """Direccionamiento ex-ante: cuantos invitados vs cuantos ofertaron en un procedimiento."""
    from django.db import connection

    inv_ceds = set()
    try:
        with connection.cursor() as cur:
            cur.execute('SELECT "CEDULA_PROVEEDOR" FROM sicop.gold_invitaciones WHERE "NRO_SICOP"=%s', [nro_sicop])
            inv_ceds = {r[0] for r in cur.fetchall()}
    except Exception:  # noqa: BLE001
        inv_ceds = {i.CEDULA_PROVEEDOR for i in SicopInvitaciones.objects.filter(NRO_SICOP=nro_sicop)}
    ofertaron = list(GoldCompetenciaPorLinea.objects.filter(NRO_SICOP=nro_sicop))
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
    total_crc = float(sum((r.TOTAL_ORDEN or 0) for r in rows if r.MONEDA_ORDEN == "CRC"))
    total_otras_convertido = (float(sum((r.TOTAL_ORDEN or 0) for r in otras)) * tc_dia) if (tc_dia and n_otras) else None
    ordenes_plain = []
    for r in rows:
        d = {
            "NRO_ORDEN": r.NRO_ORDEN,
            "NRO_SICOP": r.NRO_SICOP,
            "NRO_CONTRATO": r.NRO_CONTRATO,
            "FECHA_ELABORACION": r.FECHA_ELABORACION_ORDEN.isoformat() if r.FECHA_ELABORACION_ORDEN else None,
            "MONEDA_ORDEN": r.MONEDA_ORDEN,
            "TOTAL_ORDEN": float(r.TOTAL_ORDEN) if r.TOTAL_ORDEN is not None else None,
            "ESTADO_ORDEN": r.ESTADO_ORDEN,
        }
        if tc_dia and (r.MONEDA_ORDEN or "") not in ("", "CRC") and r.TOTAL_ORDEN:
            d["TOTAL_ORDEN_CRC_EST"] = round(float(r.TOTAL_ORDEN) * tc_dia, 2)
        ordenes_plain.append(d)
    extra = ["TOTAL_ORDEN esta replicado por linea: totales solo deduplicados por NRO_ORDEN"]
    if tc_dia and n_otras:
        extra.append(f"monedas no CRC convertidas con el TC oficial del dia ({tc_dia}) -> TOTAL_ORDEN_CRC_EST por orden y total_otras_monedas_crc_est")
    elif n_otras:
        extra.append("monedas no CRC sin convertir (fallo consultar el TC del dia)")
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


# ---- FASE C: busqueda semantica (embeddings) ----

def _embed(texto):
    """Embed del texto via el servicio local (con prefijo 'query:' de e5-base)."""
    import os

    import requests

    url = os.environ.get("EMBEDDER_URL", "http://sicop_mcp-embedder-1:8500")
    try:
        r = requests.post(f"{url}/embed", json={"textos": [texto], "tipo": "query"}, timeout=30)
        r.raise_for_status()
        return r.json()["embeddings"][0]
    except Exception:  # noqa: BLE001
        return None


def buscar_productos_semantico(texto, limit=10):
    """FASE C: productos por similitud semantica + boost lexico (hybrid search).
    e5-base da similitudes planas; el boost por coincidencia trigram de los
    tokens del query sobre el texto embebido hace que el producto especifico
    (BATERIA PARA EQUIPO UPS) rankee por encima de los genericos (RESIDUO...)."""
    from django.db import connection

    vec = _embed(texto)
    if not vec:
        return {"error": "no se pudo embeber el texto (embedder caido)", "resultados": []}
    vec_str = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

    # candidate pool: top-120 por coseno (pool amplio para re-rank)
    pool_sql = """
        SELECT e.ref_id AS codigo_cl, e.texto,
               1 - (e.embedding <=> %s::vector) AS sim
        FROM emb_doc e
        WHERE e.coleccion='PRODUCTO' AND e.embedding IS NOT NULL
        ORDER BY e.embedding <=> %s::vector
        LIMIT 120
    """
    tokens = [w for w in f_norm_py(texto).split()
              if len(w) > 4 and w not in {"para", "sobre", "con", "para", "como",
                                          "donde", "cuando", "cuanto", "entre"}]
    with connection.cursor() as cur:
        # pool: (a) semantico top-120 + (b) TODOS los que matchean tokens lexicos
        # (via trigram f_norm, indexado) -> el UPS "BATERIA PARA EQUIPO UPS" entra
        # aunque su sim coseno no llegue al top-120.
        cur.execute(pool_sql, [vec_str, vec_str])
        pool = {r[0]: (r[1], float(r[2])) for r in cur.fetchall()}
        if tokens:
            for tok in tokens:
                cur.execute(
                    "SELECT e.ref_id, e.texto, 1-(e.embedding <=> %s::vector) AS sim "
                    "FROM emb_doc e WHERE e.coleccion='PRODUCTO' AND e.embedding IS NOT NULL "
                    "AND f_norm(e.texto) LIKE %s ORDER BY e.embedding <=> %s::vector LIMIT 40",
                    [vec_str, f"%{tok}%", vec_str])
                for cod, txt, sim in cur.fetchall():
                    pool.setdefault(cod, (txt, float(sim)))
        # score por especificidad: matchear el token mas largo (bateria=7) vale mas
        # que el corto (para=4). score = sim + 0.25 * len(token_mas_largo_match).
        def _score(txt, sim):
            tn = f_norm_py(txt)
            best = max((len(tok) for tok in tokens if f" {tok} " in f" {tn} "), default=0)
            return float(sim) + 0.25 * best / 10.0  # hasta +0.175
        ranked = [{"codigo_cl": c, "texto": t, "sim": s,
                   "score": round(_score(t, s), 3)} for c, (t, s) in pool.items()]
        ranked.sort(key=lambda r: -r["score"])
        return to_plain({"texto": texto, "resultados": ranked[:limit]})


def kb_buscar(pregunta, limit=5):
    """FASE C: busca en los documentos de conocimiento (08_kb) por similitud."""
    from django.db import connection

    vec = _embed(pregunta)
    if not vec:
        return {"error": "no se pudo embeber (embedder caido)", "resultados": []}
    vec_str = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
    sql = """
        SELECT e.ref_id, e.texto, 1 - (e.embedding <=> %s::vector) AS sim
        FROM emb_doc e
        WHERE e.coleccion IN ('KB','NORMATIVA') AND e.embedding IS NOT NULL
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s
    """
    with connection.cursor() as cur:
        cur.execute(sql, [vec_str, vec_str, limit])
        cols = [c[0] for c in cur.description]
        return to_plain({"pregunta": pregunta, "resultados": [dict(zip(cols, r)) for r in cur.fetchall()]})


# ---- FASE D: grafo (Apache AGE) ----

def _cypher(q):
    """Ejecuta una query Cypher contra el grafo 'sicop' via AGE. Devuelve lista
    de filas (cada celda es texto agtype)."""
    from django.db import connection

    with connection.cursor() as cur:
        try:
            cur.execute("LOAD 'age'")
            cur.execute("SET search_path = ag_catalog, public")
            cur.execute(f"SELECT * FROM cypher('sicop', $SICOP$ {q} $SICOP$) AS (x agtype)")
            return [r[0] for r in cur.fetchall()]
        finally:
            # no dejar search_path=ag_catalog,public en la conexion pooled: las
            # queries siguientes (p.ej. tools de invitaciones) resolverian mal.
            try:
                cur.execute("RESET search_path")
            except Exception:  # noqa: BLE001
                pass


def _ag_to_py(v):
    """Convierte un valor agtype (JSON-ish string) a Python."""
    import json

    s = str(v)
    if s.endswith("::vertex") or s.endswith("::edge"):
        s = s.split("::", 1)[0]
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        return s


def grafo_competidores(cedula, familia=None, limit=30):
    """FASE D: competidores de un proveedor en el grafo (aristas COMPITIO_CON).
    Con `familia` (6 digitos UNSPSC), filtra a los que compiten en esa familia
    (aristas COMPITE_EN) y devuelve quien gana mas."""
    ced, _ = _resolver_cedula(cedula, tipos=["PROVEEDOR"])
    if not ced:
        return {"error": f"no se pudo resolver '{cedula}'", "competidores": []}
    if familia:
        fam = str(familia)[:6]
        q = (
            f"MATCH (p:Proveedor {{cedula: '{ced}'}})-[:COMPITE_EN]->(f:Familia {{familia: '{fam}'}}) "
            f"MATCH (o:Proveedor)-[r:COMPITE_EN]->(f) "
            f"WHERE o <> p "
            f"RETURN {{competidor: o.cedula, n_lineas: r.n_lineas, wins: r.wins, monto_crc: r.monto_crc}} "
            f"ORDER BY r.wins DESC LIMIT {int(limit)}"
        )
        return {"cedula": ced, "familia": fam, "competidores": [_ag_to_py(r) for r in _cypher(q)]}
    rows = _cypher(
        f"MATCH (p:Proveedor {{cedula: '{ced}'}})-[r:COMPITIO_CON]-(o) "
        f"RETURN {{competidor: o.cedula, n_lineas: r.n_lineas, wins_a: r.wins_a, wins_b: r.wins_b}} "
        f"ORDER BY r.n_lineas DESC LIMIT {int(limit)}"
    )
    return {"cedula": ced, "competidores": [_ag_to_py(r) for r in rows]}


# ---- FASE E: router en lenguaje natural ----

_STOP_QUERY_WORDS = {
    "cuantas", "cuantos", "cuanto", "cuanta", "quien", "quienes", "que",
    "como", "por", "para", "las", "los", "la", "el", "una", "un", "una",
    "con", "del", "en", "de", "y", "o", "a", "al", "ha", "han", "hace",
    "hecho", "hizo", "mas", "menos", "gana", "ganar", "compite", "compiten",
    "contra", "ficha", "perfil", "licitacion", "licitaciones", "sobre",
    "cual", "cuales", "donde", "cuando", "es", "son", "esta", "estan",
    "tiene", "tienen", "ver", "mira", "dame", "busca", "bueno", "todos",
    "todas", "este", "esta", "estos", "estas", "anio", "ano", "saco",
    "saca", "publico", "publica", "publicado", "publicada", "publicados",
    "publicadas", "publicar", "adjudico", "adjudica", "adjudicado",
    "adjudicada", "participo", "participa", "participado", "participar",
    "participacion", "participaciones", "oferto", "oferta", "ofrecio",
    "compro", "compra", "compro", "adquirio", "convocado", "convoco",
    "convocada", "saco", "sacado", "buscar", "que", "bien", "servicio",
    "tipo", "cualquier", "cartel", "carteles", "concurso", "convocatoria",
    "expediente", "procedimiento", "procedimientos", "publicada",
    "hay", "haber", "habia", "habra", "esas", "esos", "esa", "eso", "este",
    "esta", "estas", "estos", "vende", "venden", "vendo", "compra", "compran",
    "compro", "muchachos", "muchacho", "anduvo", "anda", "andar", "hacer",
    "hizo", "hacen", "hace", "ganaron", "ganan", "ganar", "ganado", "gano",
    "mira", "mire", "buscar", "busca", "busquen", "decime", "dame", "mostra",
    "aver", "chequea", "chequee", "revisa", "revisar", "cuentame", "dime",
    "cosas", "tema", "temas", "toda", "todo", "todos", "todas", "algo",
    "algunas", "algunos", "asi", "entonces", "pues", "tambien", "igual",
    "ahora", "recien", "hoy", "ayer", "pasado", "proximo", "siguiente",
    "mismo", "misma", "cualquier", "ninguna", "ninguno", "varias", "varios",
}

_INTENCIONES = [
    ("FICHA_PROVEEDOR", ["ficha", "quien es", "perfil de", "proveedor", "empresa", "adjudicaciones de", "cuantas licitaciones", "cuanto ha ganado", "cuanto gana", "negocio de", "captacion", "ejecucion"]),
    ("MERCADO", ["mercado", "familia", "producto mas", "quienes proveen", "quien compra", "estructura de mercado"]),
    ("COMPETENCIA", ["compiten", "competencia", "rival", "contra quien", "cara a cara", "vs ", "versus", "quien gana", "compite"]),
    ("PROCEDIMIENTO", ["procedimiento", "expediente", "trazabilidad", "num sicop", "nro sicop", "como va", "en que etapa"]),
    ("BUSCAR_LICITACION", ["licitacion", "licitaciones", "cartel", "concurso", "saco", "publico", "adjudico", "participo", "participed", "oferto", "compro", "adquirio", "donde participa", "ha participado"]),
    ("PRECIO", ["precio", "cuanto cuesta", "paga de mas", "barato", "caro", "costo", "presupuesto"]),
    ("SPECS", ["especificacion", "spec", "atributo", "voltaje", "dimension", "capacidad", "tecnico"]),
    ("KB", ["por que", "como se", "que significa", "regla", "trampa", "dato", "conocimiento", "explicame"]),
    ("GRAFO", ["relacionado", "red de", "representante", "vinculos", "conecta", "cual es la relacion"]),
]

_TRAMPAS_NIVEL = {
    "adjudicaciones": "captacion (adjudicaciones)",
    "fact_oferta": "oferta",
    "ordenes_pedido": "ejecucion (ordenes de pedido)",
    "recepciones": "entrega (recepciones)",
}


# Ejemplos canonicos por intencion para el clasificador SEMANTICO (embeddings).
# Cubren el lenguaje natural ambiguo que las keywords no capturan. Se embeben una
# vez (cache en Redis) y la pregunta se clasifica contra el ejemplo mas cercano.
_EJEMPLOS_INTENCION = {
    "FICHA_PROVEEDOR": [
        "cuantas licitaciones ha ganado marluvas",
        "cuanto ha facturado sondel en total",
        "perfil de la empresa electro tecnica",
        "que tan grande es el negocio de sondel con el estado",
        "cuanto gana al anio la empresa 3101095926",
        "cartera de negocio de esosa",
    ],
    "BUSCAR_LICITACION": [
        "que licitaciones saco el ice este anio",
        "busca la licitacion de calzado del ice",
        "donde oferto sondel en la caja este anio",
        "que compro el ice en botas de seguridad",
        "en que concursos participo marluvas",
        "carteles de equipos de proteccion personal de este anio",
        "que hay de calzado con el ice",
        "las botas esas de la electrica",
        "quien le vende zapatos de seguridad al ice",
        "que licitaciones publico la junta de salud",
    ],
    "MERCADO": [
        "como es el mercado de equipos de seguridad",
        "quienes proveen calzado de seguridad en el pais",
        "estructura de mercado de la familia 461816",
        "que familias de productos son las mas grandes",
    ],
    "COMPETENCIA": [
        "contra quien compite sondel en equipo contra incendios",
        "cara a cara entre sondel y esosa",
        "quien le gana mas a marluvas en licitaciones",
        "competidores de la empresa 3101095926 en 461816",
    ],
    "PROCEDIMIENTO": [
        "como va la licitacion 2026XE-000001",
        "en que etapa esta el expediente 20251201265",
        "trazabilidad del procedimiento 20240317151",
        "verificar la licitacion 2026XE-000653",
    ],
    "PRECIO": [
        "cuanto cuesta una bota de seguridad",
        "quien paga de mas por el mismo producto",
        "precios de ups en distintas instituciones",
        "cuanto se pago por extintores el anio pasado",
    ],
    "SPECS": [
        "que especificaciones tiene la bota dielectrica",
        "voltaje y potencia de la ups modelo x",
        "atributos tecnicos del calzado de seguridad",
        "caracteristicas del producto 4618160492",
    ],
    "KB": [
        "por que el cartel habla en 16 digitos",
        "que significa mes de publicacion",
        "como se calcula el tipo de cambio",
        "que es la captacion versus la ejecucion",
    ],
    "GRAFO": [
        "cual es la relacion entre sondel y esosa",
        "representantes legales en comun entre proveedores",
        "red de empresas del representante x",
        "vinculos entre contratistas",
    ],
}

_CACHE_SEM = None  # cache en memoria del proceso: (lista_ejemplos_embebidos, labels)


def _clasificar_semantico(texto, top=3):
    """Clasifica la intencion por SIMILITUD SEMANTICA: embebe la pregunta y la
    compara (coseno) contra ejemplos canonicos de cada intencion (embebidos una
    vez, cache en memoria). Devuelve [(intencion, score), ...] ordenado. Si el
    embedder no responde, devuelve [] (el caller usa keywords como fallback)."""
    global _CACHE_SEM
    import math

    vec = _embed(texto)
    if not vec:
        return []

    # construir/cargar cache: ejemplos embebidos por intencion
    if _CACHE_SEM is None:
        ejemplos = []
        labels = []
        for intencion, frases in _EJEMPLOS_INTENCION.items():
            for fr in frases:
                ev = _embed("intencion: " + fr)
                if ev:
                    ejemplos.append(ev)
                    labels.append(intencion)
        if not ejemplos:
            return []
        _CACHE_SEM = (ejemplos, labels)

    ejemplos, labels = _CACHE_SEM
    # similitud coseno manual (evita numpy; 768-dim * ~50 ejemplos = trivial)
    def _cos(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na and nb else 0.0

    scored = {}
    for ev, lab in zip(ejemplos, labels):
        s = _cos(vec, ev)
        if lab not in scored or s > scored[lab]:
            scored[lab] = s
    ranked = sorted(scored.items(), key=lambda kv: -kv[1])
    return ranked[:top]


def _clasificar_intencion(texto, ner=None):
    """Clasifica la intencion: primero por keywords (rapido, determinista) y si
    queda GENERAL/KB ambiguo, refina por SEMANTICA (embeddings) para entender
    lenguaje natural coloquial sin necesidad de ser especifico."""
    t = f_norm_py(texto)
    mejor = ("GENERAL", 0)
    for nombre, kw in _INTENCIONES:
        score = sum(1 for k in kw if k in t)
        if score > mejor[1]:
            mejor = (nombre, score)
    nombre, score = mejor

    ner = ner or {}
    # un nro_sicop puntual en el texto -> expediente/trazabilidad, no busqueda libre
    if ner.get("nro_sicop"):
        return "PROCEDIMIENTO"
    # preguntas de conteo/negocio de un proveedor ('cuantas licitaciones ha hecho
    # X', 'cuanto ha ganado X') -> FICHA, no busqueda de carteles sueltos.
    es_conteo = any(k in t for k in ("cuantas", "cuantos", "cuanto", "cuanta",
                                     "ha hecho", "ha ganado", "ha ganan", "negocio de"))
    if es_conteo and (ner.get("entidad") or ner.get("cedulas")):
        return "FICHA_PROVEEDOR"
    # 'busca/la licitacion de X' sin entidad de procedimiento puntual -> busqueda
    # por producto/institucion, salvo que sea 'cuantas licitaciones' (ficha).
    if score >= 1 and nombre == "BUSCAR_LICITACION":
        return "BUSCAR_LICITACION"
    # Si se resolvio un PROVEEDOR en el texto, es una pregunta de negocio sobre
    # donde participo/oferto/gano -> BUSCAR_LICITACION, aunque el clasificador de
    # keywords falle por typos ('licitaaciones', 'haaya', 'participed').
    if ner.get("proveedor") and nombre in ("GENERAL", "KB", "FICHA_PROVEEDOR"):
        return "BUSCAR_LICITACION"
    # si las keywords no decidieron (GENERAL o empate debil) -> SEMANTICA: entender
    # lenguaje coloquial ('las botas esas de la electrica', 'que hay de calzado
    # con el ice'). Solo refina si la semantica tiene confianza razonable.
    if nombre in ("GENERAL", "KB"):
        sem = _clasificar_semantico(texto)
        if sem and sem[0][1] >= 0.35:
            # regla de negocio: si el texto menciona proveedor/institucion y la
            # semantica dice BUSCAR/FICHA, respetar la entidad
            return sem[0][0]
    return nombre


def _ner(texto):
    """Extrae entidades del texto: cedulas, nros sicop, familias y entidades por
    resolver (instituciones/proveedores). Estrategia por prioridad:
      1) tokens que son acronimos conocidos (ICE, CCSS, CNFL, etc.) -> alias exacto;
      2) fragmentos capitalizados (nombres propios de 1-2 palabras);
      3) n-gramas del resto, con tope de intentos baratos.
    Devuelve dict con cedulas, nro_sicop, familia, institucion, proveedor y entidad
    (la mejor). Evita resolver ruido de pregunta ('cuantas', 'licitacion')."""
    import re

    t = texto or ""
    out = {"cedulas": [], "nro_sicop": None, "familia": None,
           "institucion": None, "proveedor": None, "entidad": None}

    # --- cedulas explicitas ---
    for c in re.findall(r"\b\d{9,12}\b", t):
        out["cedulas"].append(c)
    # nro sicop: 11-12 digitos que empiezan con 20xx y suelen ser 2025XXXXXXXX
    m = re.search(r"\b(20\d{2}\d{5,8})\b", t)
    if m:
        out["nro_sicop"] = m.group(1)
    # familia unspsc: 6 u 8 digitos
    m = re.search(r"\b(\d{6,8})\b", t)
    if m and not any(m.group(1) == c for c in out["cedulas"]):
        out["familia"] = m.group(1)

    # --- tokenizacion original (con mayusculas) y normalizada ---
    orig_tokens = re.findall(r"[\wÁÉÍÓÚáéíóúÑñ.]+", t)
    tokens_norm = [f_norm_py(w) for w in orig_tokens]

    _STOP = {
        "cuantas", "cuantos", "cuanto", "cuanta", "quien", "quienes", "que",
        "como", "por", "para", "las", "los", "la", "el", "una", "un", "con",
        "del", "en", "de", "y", "o", "ha", "han", "hace", "hecho", "hizo",
        "mas", "menos", "gana", "ganar", "compite", "compiten", "contra",
        "ficha", "perfil", "licitacion", "licitaciones", "sobre", "cual",
        "cuales", "donde", "cuando", "es", "son", "esta", "estan", "tiene",
        "tienen", "ver", "mira", "dame", "busca", "bueno", "todos", "todas",
        "este", "esta", "estos", "estas", "anio", "ano", "saco", "saca",
        "publico", "publica", "publicado", "publicada", "publicados",
        "publicadas", "cartel", "carteles", "adjudico", "adjudica",
        "adjudicado", "participo", "participa", "participado", "oferto",
        "oferta", "compro", "compra", "adquirio", "buscar", "concurso",
        "convocatoria", "procedimiento",
    }

    def _intentar(fragmento, tipos=None, minimo=0.5):
        """Resolver un fragmento; devuelve el mejor match o None."""
        frag = f_norm_py(fragmento)
        if len(frag) < 2 or frag in _STOP:
            return None
        try:
            r = resolver(frag, limit=1, tipos=tipos)
        except Exception:  # noqa: BLE001
            return None
        if r and r[0]["score"] >= minimo:
            return r[0]
        return None

    candidatos = []

    # 1) acronimos en MAYUSCULAS (2-6 letras): ICE, CCSS, CNFL, RECOPE, JASEC...
    for w in orig_tokens:
        w_clean = re.sub(r"[.]", "", w)
        if w_clean.isupper() and 2 <= len(w_clean) <= 6 and w_clean.isalpha():
            candidatos.append(("acronimo", w_clean, 0.95))

    # 2) nombres propios: secuencias de 1-6 palabras que empiezan con mayuscula,
    #    permitiendo conectores 'de/del/de la' entre palabras capitalizadas
    #    (captura 'Instituto Costarricense de Electricidad', 'Caja Costarricense
    #    de Seguro Social', 'Municipalidad de San Jose', etc.).
    _CONEC = {"de", "del", "de", "la", "el", "los", "las"}
    i = 0
    while i < len(orig_tokens):
        w = orig_tokens[i]
        if w[:1].isupper() and len(w) > 1 and w not in _STOP:
            # extender mientras haya mayusculas o conectores entre mayusculas
            seq = [w]
            j = i + 1
            while j < len(orig_tokens):
                nw = orig_tokens[j]
                if nw[:1].isupper() and nw not in _STOP:
                    seq.append(nw)
                    j += 1
                elif nw in _CONEC and j + 1 < len(orig_tokens) and \
                        orig_tokens[j + 1][:1].isupper():
                    seq.append(nw)
                    seq.append(orig_tokens[j + 1])
                    j += 2
                else:
                    break
            # candidatos: la secuencia completa y prefijos de 2+ (para no perder
            # si el nombre real es mas corto que lo que capitalizo el usuario).
            # NUNCA emitir prefijos que terminen en conector ('...de'): son
            # fragmentos invalidos que resuelven a la institucion equivocada.
            for n in range(len(seq), 1, -1):
                if seq[n - 1] in _CONEC:
                    continue
                frag = " ".join(seq[:n])
                candidatos.append(("nombre", frag, 0.6))
            # la primera palabra sola como fallback
            candidatos.append(("nombre", w, 0.5))
            i = j
        else:
            i += 1

    # 3) palabras sueltas en minuscula que pueden ser alias/proveedor:
    #    'sondel', 'marluvas', 'esosa', 'electrica', 'ice' suelto, etc.
    #    Solo palabras "significativas" (>=3 letras, alfa, no stopword, no
    #    numeros). El resolver matchea por trigram contra alias_norm/nombre_norm
    #    asi que los alias coloquiales ('electrica') y marcas de proveedor
    #    ('sondel', 'marluvas') resuelven aunque esten en minuscula.
    #    NOTA: umbral minimo alto (0.75) para que verbos comunes ('vende',
    #    'anda', 'ganaron') NO resuelvan como proveedor por similitud casual.
    for i, w in enumerate(tokens_norm):
        if 3 <= len(w) <= 12 and w.isalpha() and w not in _STOP and \
           w not in {"con", "que", "para", "este", "esta", "una", "sus",
                     "sobre", "contra", "como", "mas", "menos", "pero",
                     "tambien", "para", "vende", "venden", "vender", "anda",
                     "andar", "anduvo", "ganaron", "ganar", "gano", "hace",
                     "hizo", "hacen", "mira", "dame", "aver"}:
            candidatos.append(("alias_corto", w, 0.75))
    # bigrama minuscula: 'la electrica' -> probar tambien el par
    for i in range(len(tokens_norm) - 1):
        a, b = tokens_norm[i], tokens_norm[i + 1]
        if b not in _STOP and 3 <= len(b) <= 12 and b.isalpha() and \
                a in {"la", "el", "los", "las", "don"}:
            candidatos.append(("alias_corto", f"{a} {b}", 0.72))

    # desempatar: probar en orden (acronimo, nombre 2pal, nombre 1pal, corto)
    visto = set()
    orden_prioridad = {"acronimo": 0, "alias_corto": 1, "nombre": 2}
    candidatos.sort(key=lambda c: (orden_prioridad[c[0]], -c[2]))
    mejores = {}          # tipo -> mejor entidad
    mejores_frag = {}     # tipo -> fragmento original
    intentos = 0
    for kind, frag, _min in candidatos:
        if frag in visto:
            continue
        visto.add(frag)
        if intentos >= 20:
            break
        intentos += 1
        # los acronimos en mayuscula y los alias cortos tipicos son de
        # instituciones: resolver primero como INSTITUCION. Tambien los nombres
        # que EMPIEZAN con palabra de institucion (instituto/caja/municipalidad/
        # ministerio/banco/caja/universidad/junta/consejo/ccss/mideplan/etc.)
        palabra0 = f_norm_py(frag.split()[0]) if frag else ""
        suena_inst = (palabra0 in {
            "instituto", "institucion", "caja", "municipalidad", "ministerio",
            "banco", "universidad", "junta", "consejo", "ccss", "poder",
            "superintendencia", "direccion", "secretaria", "hospital",
            "patronato", "colegio", "servicio", "recope", "aya",
        } or (kind == "acronimo")
                     or (kind == "alias_corto" and palabra0 in
                         {"ice", "ccss", "cnfl", "recope", "aya", "ina", "ins",
                          "ict", "mideplan", "mag", "poder", "aya", "aya"}))
        tipos = ["INSTITUCION"] if suena_inst else None
        r = _intentar(frag, tipos=tipos, minimo=_min)
        # si no matcheo como institucion, reintentar libre (p.ej. proveedor)
        if not r and tipos:
            r = _intentar(frag, minimo=_min)
        if r:
            t = r["tipo"]
            # quedarse con el mejor por tipo (institucion Y proveedor)
            if t not in mejores or r["score"] > mejores[t]["score"]:
                mejores[t] = r
                mejores_frag[t] = frag
            # si ya tenemos institucion y proveedor con buen score, cortar
            if ("INSTITUCION" in mejores and mejores["INSTITUCION"]["score"] >= 0.8
                    and "PROVEEDOR" in mejores and mejores["PROVEEDOR"]["score"] >= 0.8):
                break
    if mejores:
        # el "entidad" principal: preferir proveedor si hay ambos (ficha/competencia
        # se resuelve sobre el proveedor), sino la institucion.
        ent = mejores.get("PROVEEDOR") or mejores.get("INSTITUCION")
        out["entidad"] = ent
        out["entidad_match"] = mejores_frag.get(ent["tipo"])
        if "INSTITUCION" in mejores:
            out["institucion"] = mejores["INSTITUCION"]
            out.setdefault("institucion_match", mejores_frag.get("INSTITUCION"))
        if "PROVEEDOR" in mejores:
            out["proveedor"] = mejores["PROVEEDOR"]
    return out


def _termino_producto(texto, ner):
    """Deriva el termino de producto de la pregunta, quitando palabras de las
    entidades resueltas (institucion/proveedor) y verbos de busqueda.
    Ej: 'licitacion de calzado de seguridad que saco el ICE' -> 'calzado seguridad';
        'licitaciones donde Sondel oferto en el ICE' -> '' (solo entidades)."""
    import re

    t = f_norm_py(texto)
    stop = set(_STOP_QUERY_WORDS)
    for k in ("institucion_match", "proveedor_match", "entidad_match"):
        frag = ner.get(k)
        if frag:
            for w in f_norm_py(frag).split():
                if len(w) > 1:
                    stop.add(w)
    # tambien el nombre canonico de cada entidad (p.ej. 'instituto costarricense')
    for k in ("institucion", "proveedor", "entidad"):
        ent = ner.get(k)
        if isinstance(ent, dict):
            for w in f_norm_py(ent.get("nombre", "")).split():
                if len(w) > 2:
                    stop.add(w)
    palabras = [w for w in re.findall(r"[\w]+", t) if len(w) > 2 and w not in stop
                and not w.isdigit()]
    return " ".join(palabras)


def _anio_consulta(texto, ner):
    """Detecta el anio de la consulta: un 20XX explicito o 'este anio' -> anio
    actual (derivado de la maxima MES_PUBLICACION)."""
    import re

    m = re.search(r"\b(20\d{2})\b", texto or "")
    if m:
        return m.group(1)
    t = f_norm_py(texto)
    if any(w in t for w in ("este anio", "este ano", "el anio", "actual")):
        try:
            from .models import SicopCarteles
            from django.db.models import Max
            top = SicopCarteles.objects.aggregate(m=Max("MES_PUBLICACION"))["m"]
            if top and len(top) >= 4:
                return top[:4]
        except Exception:  # noqa: BLE001
            pass
    return None


def procedimientos_buscar(institucion=None, proveedor=None, termino=None,
                          anio=None, limit=10):
    """Busca licitaciones/procedimientos por institucion + termino de producto
    (calzado, UPS, etc.) y/o por proveedor participante. Cruza sicop_carteles
    (quien compro) con fact_requerimiento (lo que se pidio, DESC_LINEA) y con
    fact_oferta (quien oferto). Nivel: captacion (cartel) - ver trampa de
    subregistro si no hay adjudicacion."""
    from django.db import connection

    out = {"procedimientos": [], "sobre": sobre("captacion (cartel: lo que se pidio)",
           None, extra=["un cartel puede estar publicado sin adjudicacion aun",
                        "el termino se matchea sobre DESC_LINEA del requerimiento"])}
    try:
        if institucion:
            inst_ced = institucion.get("cedula") if isinstance(institucion, dict) else str(institucion)
        else:
            inst_ced = None
        if proveedor:
            prov_ced = proveedor.get("cedula") if isinstance(proveedor, dict) else str(proveedor)
        else:
            prov_ced = None
        termino = f_norm_py(termino or "").strip() or None
        anio = anio or None
        if anio and not anio.isdigit():
            anio = None

        # ---- sinonimos por palabra de producto (calzado -> zapato/bota/...) ----
        # Agrupamos por "familia de palabra" para que un cartel que dice
        # "BOTA DE SEGURIDAD" matchee una consulta por "calzado de seguridad".
        _SINONIMOS = {
            "calzado": {"calzado", "zapato", "zapatos", "bota", "botas", "botin",
                        "zapatillas", "calzado"},
            "zapato": {"calzado", "zapato", "zapatos", "botas", "bota", "calzado"},
            "bota": {"calzado", "zapato", "bota", "botas", "botin", "calzado"},
            "zapatos": {"calzado", "zapato", "zapatos", "bota", "botas", "botin"},
            "botas": {"calzado", "zapato", "bota", "botas", "botin"},
            "computadora": {"computadora", "computador", "computo", "pc", "laptop", "portatil"},
            "laptop": {"computadora", "computador", "laptop", "portatil", "notebook"},
            "impresora": {"impresora", "impresion"},
            "papel": {"papel", "papeleria", "resma"},
            "seguridad": {"seguridad"},
            "uniforme": {"uniforme", "uniforme", "vestimenta"},
            "medicamento": {"medicamento", "medicina", "farmaco", "farmaco", "droga"},
            "combustible": {"combustible", "gasolina", "diesel", "gasoil", "bunker", "carburante"},
            "llanta": {"llanta", "neumatico", "caucho", "cubierta"},
            "aceite": {"aceite", "lubricante", "lubricacion"},
            "alimento": {"alimento", "alimentacion", "comida", "viveres", "comestible"},
            "leche": {"leche", "lacteo"},
            "huevo": {"huevo", "huevos"},
            "carne": {"carne", "carnicos", "res", "pollo", "cerdo"},
            "desinfectante": {"desinfectante", "limpieza", "jabon", "desinfeccion"},
        }

        def _grupos_termino(txt):
            """Divide el termino en grupos de sinonimos (uno por palabra).
            Devuelve lista de set de palabras: cada grupo debe matchear en el
            DESC_LINEA para que el cartel cuente."""
            palabras = [w for w in txt.split() if len(w) >= 4 and w not in
                        {"para", "tipo", "de", "con", "y", "del", "material"}]
            grupos = []
            for p in palabras:
                sinon = _SINONIMOS.get(p) or {p}
                grupos.append(sinon)
            return grupos

        grupos = _grupos_termino(termino) if termino else []

        def _cond_linea(alias, grupo_i):
            """Condicion SQL: el DESC_LINEA matchea el grupo de sinonimos.
            Devuelve (cond_sql_con_%s, lista_de_palabras) donde cada palabra se
            pasa como parametro ya con comodines (%%palabra%%)."""
            g = sorted(grupos[grupo_i])
            cond = " OR ".join(
                f"f_norm({alias}.\"DESC_LINEA\") LIKE %s"
                for _ in g)
            return f"({cond})", [f"%{w}%" for w in g]

        if grupos:
            cond_rm, params_rm = [], []
            for i in range(len(grupos)):
                c, pal = _cond_linea("rm", i)
                cond_rm.append(c)
                params_rm.extend(pal)
            cond_lineas_match = " AND ".join(cond_rm)          # alias rm
            cond_r2 = cond_lineas_match.replace("rm.", "r2.")  # alias r2
        else:
            cond_lineas_match = cond_r2 = "true"
            params_rm = []

        sql_final = """
            WITH sel AS (
                SELECT c."NRO_SICOP" AS nro_sicop,
                       c."NRO_PROCEDIMIENTO" AS nro_proc,
                       c."TIPO_PROCEDIMIENTO" AS tipo,
                       c."MES_PUBLICACION" AS mes,
                       c."CEDULA_INSTITUCION" AS ced_inst,
                       c."FECHA_PUBLICACION" AS fecha_pub,
                       c."MONTO_EST" AS monto_est
                FROM sicop_carteles c
                WHERE (%s::text IS NULL OR c."CEDULA_INSTITUCION" = %s)
                  AND (%s::text IS NULL OR left(c."MES_PUBLICACION", 4) = %s)
                  {sel_prov}
                ORDER BY c."MES_PUBLICACION" DESC, c."NRO_SICOP" DESC
                LIMIT 2500
            ),
            dedup AS (
                SELECT DISTINCT ON (nro_sicop) *
                FROM sel
                ORDER BY nro_sicop
            )
            {cte_match}, proc AS (
                SELECT s.*,
                       i."NOMBRE_INSTITUCION" AS institucion_nombre,
                       {sub_lineas_hit} AS lineas_hit,
                       (SELECT count(*) FROM fact_oferta o
                         WHERE o."NRO_SICOP" = s.nro_sicop) AS n_ofertas,
                       (SELECT count(*) FROM fact_adjudicacion a
                         WHERE a."NRO_SICOP" = s.nro_sicop) AS n_adjudicadas
                FROM dedup s
                LEFT JOIN (
                    SELECT DISTINCT ON ("CEDULA") "CEDULA", "NOMBRE_INSTITUCION"
                    FROM sicop_instituciones
                ) i ON i."CEDULA" = s.ced_inst
                WHERE (true)
                  {where_term}
                  AND (%s::text IS NULL OR EXISTS (SELECT 1 FROM fact_oferta o2
                         WHERE o2."NRO_SICOP" = s.nro_sicop AND o2."CEDULA_PROVEEDOR" = %s))
            )
            SELECT p.*,
                   {sub_ejemplo} AS lineas_ejemplo
            FROM proc p
            ORDER BY p.mes DESC, p.nro_sicop DESC
            LIMIT %s
        """.format(
            sel_prov=(
                f"AND EXISTS (SELECT 1 FROM fact_oferta ofv\n"
                f"            WHERE ofv.\"NRO_SICOP\" = c.\"NRO_SICOP\"\n"
                f"              AND ofv.\"CEDULA_PROVEEDOR\" = %s)"
            ) if prov_ced else "",
            cte_match=(
                ", match_lineas AS (\n"
                "    SELECT DISTINCT rm.\"NRO_SICOP\", rm.\"NUMERO_LINEA\", rm.\"DESC_LINEA\"\n"
                "    FROM fact_requerimiento rm\n"
                f"    WHERE {cond_lineas_match}\n)"
            ) if grupos else "",
            sub_lineas_hit=(
                "(SELECT count(DISTINCT ml.\"NUMERO_LINEA\") FROM match_lineas ml\n"
                "   WHERE ml.\"NRO_SICOP\" = s.nro_sicop)"
            ) if grupos else "0",
            where_term=(
                f"AND (%s::text IS NULL OR EXISTS (SELECT 1 FROM fact_requerimiento r2\n"
                f"       WHERE r2.\"NRO_SICOP\" = s.nro_sicop AND {cond_r2}))"
            ) if grupos else "",
            sub_ejemplo=(
                "(SELECT string_agg(DISTINCT left(ml2.\"DESC_LINEA\", 140), ' | ')\n"
                "  FROM (SELECT \"DESC_LINEA\", \"NUMERO_LINEA\" FROM match_lineas\n"
                "        WHERE \"NRO_SICOP\" = p.nro_sicop ORDER BY \"NUMERO_LINEA\" LIMIT 6) ml2)"
            ) if grupos else "NULL",
        )
        # orden de parametros (textual en sql_final):
        #   sel CTE:            inst, inst, anio, anio, [prov si sel_prov]
        #   match_lineas CTE:   params_rm (palabras con comodines)  [si grupos]
        #   proc where_term:    termino, luego params_rm otra vez (cond_r2)  [si grupos]
        #   proc where_prov:    prov, prov
        #   limit
        params = [inst_ced, inst_ced, anio, anio]
        if prov_ced:
            params += [prov_ced]
        if grupos:
            params += params_rm
        if grupos:
            params += [termino]
            params += params_rm
        params += [prov_ced, prov_ced, limit]
        with connection.cursor() as cur:
            cur.execute(sql_final, params)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]

        # resolver labels humanos de nro_sicop (procedimiento + institucion)
        labels = resolver_procedimientos([r["nro_sicop"] for r in rows])
        seen = set()
        uniq = []
        for r in rows:
            if r["nro_sicop"] in seen:
                continue
            seen.add(r["nro_sicop"])
            lab = labels.get(r["nro_sicop"]) or {}
            r["NRO_SICOP"] = r["nro_sicop"]
            r["NRO_PROCEDIMIENTO"] = r["nro_proc"]
            r["PROCEDIMIENTO_LABEL"] = lab.get("PROCEDIMIENTO_LABEL") or r["nro_proc"]
            r["tipo_procedimiento"] = r["tipo"]
            r["mes_publicacion"] = r["mes"]
            r["institucion"] = r["institucion_nombre"]
            r.pop("nro_proc", None)
            uniq.append(r)
        out["procedimientos"] = to_plain(uniq)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def preguntar(pregunta):
    """FASE E: router de lenguaje natural. Clasifica la intencion, extrae
    entidades y responde con la tool gold correcta, declarando nivel de medicion
    y trampas aplicables. Sin LLM en el VPS."""
    texto = (pregunta or "").strip()
    if not texto:
        return {"error": "pregunta vacia"}

    ner = _ner(texto)
    intencion = _clasificar_intencion(texto, ner)

    # --- resolver segun intencion ---
    respuesta = {"intencion": intencion, "entidades": ner}
    trampas = _trampas_aplicables(texto, ner)
    nivel = _nivel_medicion(intencion)

    try:
        if intencion == "FICHA_PROVEEDOR" and (ner["cedulas"] or ner["entidad"]):
            ced = ner["cedulas"][0] if ner["cedulas"] else ner["entidad"]["cedula"]
            respuesta["datos"] = ficha_proveedor(ced)
        elif intencion == "COMPETENCIA" and (ner["cedulas"] or ner["entidad"]):
            ced = ner["cedulas"][0] if ner["cedulas"] else ner["entidad"]["cedula"]
            respuesta["datos"] = grafo_competidores(ced, ner["familia"], limit=15)
        elif intencion == "MERCADO" and ner["familia"]:
            respuesta["datos"] = mercado_familia(ner["familia"])
        elif intencion == "PROCEDIMIENTO" and ner["nro_sicop"]:
            respuesta["datos"] = expediente(ner["nro_sicop"])
        elif intencion == "PRECIO" and ner["familia"]:
            respuesta["datos"] = precios_institucion(ner["familia"], limit=10)
        elif intencion == "BUSCAR_LICITACION":
            # busqueda de licitaciones por institucion + producto y/o proveedor.
            # Si hay PROVEEDOR (ej 'donde ofertó Sondel'), el termino de producto
            # sobra: sicop busca por las ofertas del proveedor (EXISTS fact_oferta).
            # Pasar el termino ruidoso (typos de 'licitaciones/participado') aqui
            # rompe la busqueda (0 resultados) -> se descarta.
            termino = _termino_producto(texto, ner)
            if ner.get("proveedor"):
                termino = None
            respuesta["datos"] = procedimientos_buscar(
                institucion=ner.get("institucion"),
                proveedor=ner.get("proveedor"),
                termino=termino,
                anio=_anio_consulta(texto, ner),
                limit=10,
            )
        elif intencion in ("KB", "GENERAL"):
            respuesta["datos"] = kb_buscar(texto, limit=3)
        elif intencion == "SPECS":
            # specs via busqueda semantica de producto
            respuesta["datos"] = buscar_productos_semantico(texto, limit=5)
        else:
            # fallback: busqueda semantica + kb
            respuesta["datos"] = kb_buscar(texto, limit=3)
    except Exception as exc:  # noqa: BLE001
        respuesta["error"] = f"{type(exc).__name__}: {exc}"

    respuesta["nivel_medicion"] = nivel
    respuesta["trampas"] = trampas
    respuesta["sobre"] = sobre(nivel, None, extra=["respuesta del router FASE E; verificar con la tool especifica"])
    return to_plain(respuesta)


def _nivel_medicion(intencion):
    """Nivel de medicion por intencion (regla de la casa)."""
    if intencion in ("FICHA_PROVEEDOR",):
        return "mixto: captacion (adjudicaciones) + ejecucion (ordenes) segun el bloque"
    if intencion == "COMPETENCIA":
        return "captacion (adjudicaciones) por linea"
    if intencion == "MERCADO":
        return "captacion (adjudicaciones)"
    if intencion == "BUSCAR_LICITACION":
        return "captacion (cartel: lo que se pidio, MES_PUBLICACION)"
    if intencion in ("PRECIO", "SPECS"):
        return "oferta (precios ofertados)"
    return "no aplica (conocimiento/regla)"


def _trampas_aplicables(texto, ner):
    """Consulta ctl_trampa para las trampas relevantes a la intencion/entidades."""
    try:
        from .models import CtlTrampa

        t = f_norm_py(texto)
        rows = list(CtlTrampa.objects.all().values("conjunto", "campo", "trampa")[:8])
        hits = []
        for r in rows:
            rt = f_norm_py(r["trampa"])
            if any(k in rt for k in t.split() if len(k) > 3):
                hits.append(r)
        return hits[:3]
    except Exception:  # noqa: BLE001
        return []


# ---- FASE §3.8: specs tecnicas + integridad (meta) ----

def producto_specs(codigo_cl, descripcion=None, limit=50):
    """Especificaciones tecnicas de un producto desde gold_atributos_producto.
    Acepta CODIGO_PRODUCTO_CL (16 dig) o una descripcion/marca para buscar."""
    from django.db.models import Count

    from .models import GoldAtributosProducto, GoldCatalogoProductos

    cod = (codigo_cl or "").strip()
    if not cod and descripcion:
        # resolver a codigo via el catalogo (trigram / semantica)
        try:
            qs = GoldCatalogoProductos.objects.filter(f_norm__contains=f_norm_py(descripcion))
            r = qs.values("CODIGO_PRODUCTO_CL", "DESCRIPCION").first()
            cod = r["CODIGO_PRODUCTO_CL"] if r else None
        except Exception:  # noqa: BLE001
            cod = None
    if not cod:
        return {"error": "no se pudo resolver el producto", "resultados": []}

    specs = list(
        GoldAtributosProducto.objects.filter(CODIGO_PRODUCTO_CL=cod)
        .order_by("-N_LINEAS")
        .values("TIPO_ATRIBUTO", "VALOR", "UNIDAD", "N_LINEAS", "CANTIDAD_ADJUDICADA", "MARCA")
    )
    catalogo = GoldCatalogoProductos.objects.filter(CODIGO_PRODUCTO_CL=cod).values(
        "DESCRIPCION", "MARCA", "MODELO", "FAMILIA_UNSPSC").first()
    # agrupar por atributo
    agrupado = {}
    for s in specs:
        k = s["TIPO_ATRIBUTO"]
        agrupado.setdefault(k, []).append(
            {"valor": s["VALOR"], "unidad": s["UNIDAD"], "n_lineas": s["N_LINEAS"],
             "cantidad_adjudicada": s["CANTIDAD_ADJUDICADA"], "marca": s["MARCA"]}
        )
    return to_plain({
        "codigo_cl": cod,
        "producto": catalogo,
        "n_atributos": len(specs),
        "specs": agrupado,
        "resumen": {k: len(v) for k, v in agrupado.items()},
        "sobre": sobre("specs del catalogo (adjudicaciones+ejecucion)", None,
                       extra=["cobertura solo sobre productos adjudicados"]),
    })


def integridad(tabla=None, mes=None, moneda=False):
    """FASE §3.8: consulta el esquema meta (auditoria del paquete COMPLETO):
    claves canonicas, censo mes-tabla, huecos por mes, subregistro de monedas."""
    from django.db import connection

    out = {"sobre": "esquema meta: auditoria de integridad (paquete Alejandro COMPLETO)"}
    with connection.cursor() as cur:
        if tabla:
            cur.execute("SELECT * FROM meta.claves_canonicas WHERE tabla=%s", [tabla])
            cols = [c[0] for c in cur.description]
            out["claves_canonicas"] = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.execute(
                "SELECT aaaamm, filas_zip, filas_base, pct_cargado, veredicto, nota "
                "FROM meta.censo_mes_tabla WHERE tabla=%s ORDER BY aaaamm LIMIT 60", [tabla])
            cols = [c[0] for c in cur.description]
            out["censo"] = [dict(zip(cols, r)) for r in cur.fetchall()]
        elif mes:
            cur.execute(
                "SELECT tabla, filas FROM meta.mapa_huecos_mes WHERE mes=%s", [mes])
            cols = [c[0] for c in cur.description]
            out["huecos_mes"] = [dict(zip(cols, r)) for r in cur.fetchall()]
        else:
            cur.execute("SELECT tabla, count(*) n FROM meta.claves_canonicas GROUP BY 1")
            out["tablas_auditadas"] = [{"tabla": r[0], "n": r[1]} for r in cur.fetchall()]
            cur.execute("SELECT veredicto, count(*) n FROM meta.censo_mes_tabla GROUP BY 1 ORDER BY 2 DESC")
            out["veredictos_censo"] = [{"veredicto": r[0], "n": r[1]} for r in cur.fetchall()]
            cur.execute("SELECT mes, count(*) n FROM meta.mapa_huecos_mes GROUP BY 1 ORDER BY 1 LIMIT 12")
            out["huecos_por_mes_top"] = [{"mes": r[0], "n": r[1]} for r in cur.fetchall()]
        if moneda:
            cur.execute("SELECT clase, anio, moneda, n_ordenes, monto_original FROM meta.moneda_subregistro")
            cols = [c[0] for c in cur.description]
            out["subregistro_moneda"] = [dict(zip(cols, r)) for r in cur.fetchall()]
    return to_plain(out)
