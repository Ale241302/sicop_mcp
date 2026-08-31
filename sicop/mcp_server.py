"""Servidor MCP de datos SICOP (mcp 2.x / MCPServer).

Correr:
    python -m sicop.mcp_server                 # stdio
    python -m sicop.mcp_server streamable-http --port 9010
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from mcp.server.mcpserver import MCPServer

from . import queries


def wrap(value):
    """Serializa (Decimal/date/modelos Django -> JSON) y envuelve listas en un
    dict: el framework MCP 2.x serializa mal una lista top-level."""
    from .queries import to_plain

    value = to_plain(value)
    if isinstance(value, list):
        value = {"resultados": value, "total": len(value)}
    _etiquetar_labels(value)
    return value


def _etiquetar_labels(value):
    """Inyecta labels humanos a las filas con NRO_SICOP / CEDULA_PROVEEDOR:
    NRO_PROCEDIMIENTO, TIPO_PROCEDIMIENTO, INSTITUCION, PROCEDIMIENTO_LABEL y
    NOMBRE_PROVEEDOR. Aplica a TODAS las respuestas (chokepoint wrap)."""
    rows = []

    def _walk(obj):
        if isinstance(obj, dict):
            if obj.get("NRO_SICOP") or obj.get("CEDULA_PROVEEDOR"):
                rows.append(obj)
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for it in obj:
                _walk(it)

    _walk(value)
    if not rows:
        return value
    from .queries import resolver_procedimientos, resolver_proveedores

    nros = list({str(r["NRO_SICOP"]) for r in rows if r.get("NRO_SICOP")})
    ceds = list({str(r["CEDULA_PROVEEDOR"]) for r in rows if r.get("CEDULA_PROVEEDOR")})
    labs = resolver_procedimientos(nros)
    names = resolver_proveedores(ceds)
    for r in rows:
        n = str(r.get("NRO_SICOP")) if r.get("NRO_SICOP") else None
        if n and n in labs:
            for k, v in labs[n].items():
                r.setdefault(k, v)
        c = str(r.get("CEDULA_PROVEEDOR")) if r.get("CEDULA_PROVEEDOR") else None
        if c and c in names:
            r.setdefault("NOMBRE_PROVEEDOR", names[c])
    return value


mcp = MCPServer(
    "sicop",
    instructions=(
        "Sistema de inteligencia sobre datos abiertos de contratacion publica de Costa Rica (SICOP, 2020-2026). "
        "NIVEL DE MEDICION: toda cifra de negocio de un proveedor debe declarar si mide captacion "
        "(adjudicaciones), ejecucion (ordenes de pedido) o entrega (recepciones). Consultar un proveedor "
        "por captacion lo subestima hasta 59x frente a su ejecucion real. "
        "GESTION DEL SISTEMA: podes AUTO-GESTIONAR la base (diagnosticar, reparar, reconciliar). "
        "Usa sicop_diagnostico para saber que necesita atencion, sicop_verificar_procedimiento para "
        "revisar una licitacion especifica, sicop_reconciliar para hallar meses con huecos, y "
        "sicop_reparar_mes para reparar un mes (re-extrae de la fuente, recarga Postgres, broncea, "
        "reconstruye silver+gold y corre el gate). La ingesta es DETERMINISTA (el extractor lee los "
        "ZIP oficiales); tu rol es diagnosticar y disparar reparaciones, NO editar datos crudos a mano "
        "(el SQL libre esta bloqueado por enforcement). El ciclo diario 06:00/18:00 ya detecta y "
        "reprocesa reescrituras de la fuente automaticamente."
    ),
)


@mcp.tool()
def sicop_ficha_proveedor(cedula: str) -> dict:
    """Ficha completa de un proveedor (por cedula, ej 3101029593): adjudicaciones por anio, cartera ejecucion vs captacion, desempeno de entrega y familias top."""
    return wrap(queries.ficha_proveedor(cedula))


@mcp.tool()
def sicop_mercado_familia(familia_unspsc: str) -> dict:
    """Estructura de mercado de una familia UNSPSC (8 digitos, ej 461816 o 81112399): adjudicatarios top, productos del catalogo y desempeno."""
    return wrap(queries.mercado_familia(familia_unspsc))


@mcp.tool()
def sicop_competencia_procedimiento(nro_sicop: str) -> dict:
    """Oferentes por linea de un procedimiento (nro_sicop): quien oferto, a que precio, quien gano y el delta contra el ganador."""
    return wrap(queries.competencia_procedimiento(nro_sicop))


@mcp.tool()
def sicop_producto(codigo_cl: str) -> list:
    """Ficha de un producto del catalogo por CODIGO_PRODUCTO_CL (16 digitos): descripcion, marca, modelo, quienes lo proveen y compran."""
    return wrap(queries.producto(codigo_cl))


@mcp.tool()
def sicop_expediente(nro_sicop: str) -> dict:
    """Trazabilidad de un procedimiento (nro_sicop): que tramos tiene completos (cartel, ofertas, acto firme, adjudicado, contrato, garantia, recibido)."""
    return wrap(queries.expediente(nro_sicop))


@mcp.tool()
def sicop_adjudicaciones(cedula: str = "", institucion: str = "", anio: str = "", nro_sicop: str = "", objeto_gasto: str = "", limit: int = 50) -> list:
    """Lineas adjudicadas. Filtros opcionales por cedula de proveedor, cedula de institucion, anio (2020-2026), nro_sicop u objeto de gasto. Nivel: captacion."""
    return wrap(queries.adjudicaciones(cedula, institucion, anio, nro_sicop, objeto_gasto, limit))


@mcp.tool()
def sicop_carteles_objetados(institucion: str = "", limit: int = 100) -> list:
    """Carteles objetados (cola de revision): monto estimado, institucion, si se adjudico despues."""
    return wrap(queries.carteles_objetados(institucion, limit))


@mcp.tool()
def sicop_representantes(limit: int = 50) -> list:
    """Representantes legales con 2+ empresas adjudicatarias, monto total y familias."""
    return wrap(queries.representantes(limit))


@mcp.tool()
def sicop_representante_competencia(cedula_representante: str = "", limit: int = 100) -> list:
    """Lineas donde 2+ oferentes comparten representante legal (cola de revision, no conclusion)."""
    return wrap(queries.representante_competencia(cedula_representante, limit))


@mcp.tool()
def sicop_excepciones(cedula: str = "", limit: int = 100) -> list:
    """Procedimientos por excepcion (proveedor unico, emergencia, capacitacion) agrupados por adjudicatario."""
    return wrap(queries.excepciones(cedula, limit))


@mcp.tool()
def sicop_sanciones(cedula: str = "") -> list:
    """Sanciones a proveedores (inhabilitaciones/multas de procedimientos administrativos)."""
    return wrap(queries.sanciones(cedula))


@mcp.tool()
def sicop_precios_institucion(familia_unspsc: str = "", marca: str = "", anio: str = "", limit: int = 100) -> list:
    """Quien paga de mas por el mismo producto (marca+modelo+firma+anio): ratio max/min entre instituciones."""
    return wrap(queries.precios_institucion(familia_unspsc, marca, anio, limit))


@mcp.tool()
def sicop_resumen() -> dict:
    """Estado de la base: tablas cargadas y filas (diagnostico)."""
    return wrap(queries.resumen())


@mcp.tool()
def sicop_cara_a_cara(cedula_a: str, cedula_b: str, familia_unspsc: str = "") -> dict:
    """Cara a cara de dos proveedores (plan: cara_a_cara): lineas donde ambos ofertaron, victorias, veces mas barato cada uno, familias compartidas y perfiles captacion/ejecucion."""
    return wrap(queries.cara_a_cara(cedula_a, cedula_b, familia_unspsc or None))


@mcp.tool()
def sicop_producto_historia(codigo_cl: str) -> dict:
    """Historia de un producto (CODIGO_PRODUCTO_CL de 16 digitos): catalogo, secuencia de precios ofertados por anio (mediana/min/max), adjudicaciones, proveedores top y quien paga de mas por institucion."""
    return wrap(queries.producto_historia(codigo_cl))


@mcp.tool()
def sicop_campo_buscar(termino: str, limit: int = 20) -> dict:
    """Busqueda por termino en el catalogo de productos (descripcion/marca/modelo), proveedores e instituciones (plan: campo_buscar)."""
    return wrap(queries.campo_buscar(termino, limit))


@mcp.tool()
def sicop_buscar_procedimiento(numero_procedimiento: str, limit: int = 20) -> dict:
    """Traduce el numero humano del procedimiento (ej '2023LE-000016-0000200001', el que sale en carteles y correos) al NRO_SICOP canonico."""
    from sicop.models import SicopCarteles

    q = (numero_procedimiento or "").strip()
    if not q:
        return {"resultados": [], "total": 0}
    qs = SicopCarteles.objects.filter(NRO_PROCEDIMIENTO__icontains=q)
    rows = list(qs.values("NRO_SICOP", "NRO_PROCEDIMIENTO", "CEDULA_INSTITUCION",
                          "TIPO_PROCEDIMIENTO", "FECHA_PUBLICACION", "MONTO_EST")[:limit])
    return {"resultados": rows, "total": len(rows),
            "nota": "una vez tengas el NRO_SICOP, usalo con sicop_verificar_procedimiento / sicop_expediente / sicop_competencia_procedimiento"}


@mcp.tool()
def sicop_perdidas_baratas(cedula: str = "", familia_unspsc: str = "", limit: int = 200) -> dict:
    """Lineas donde un proveedor oferto MAS BARATO que el ganador y aun asi perdio (cola de revision, no conclusion)."""
    return wrap(queries.perdidas_baratas(cedula, familia_unspsc or None, limit))


@mcp.tool()
def sicop_regimen_evaluacion(nro_sicop: str) -> dict:
    """Regimen de evaluacion de un procedimiento (factores y pesos de evaluacion_ofertas)."""
    return wrap(queries.regimen_evaluacion(nro_sicop))


@mcp.tool()
def sicop_invitaciones_procedimiento(nro_sicop: str, limit: int = 500) -> dict:
    """Quien fue invitado a un procedimiento (contratacion directa). Direccionamiento ex-ante."""
    return wrap(queries.invitaciones_procedimiento(nro_sicop, limit))


@mcp.tool()
def sicop_invitaciones_proveedor(cedula: str, limit: int = 200) -> dict:
    """Procedimientos donde un proveedor fue invitado (plan: invitaciones_pendientes)."""
    return wrap(queries.invitaciones_proveedor(cedula, limit))


@mcp.tool()
def sicop_invitados_vs_ofertantes(nro_sicop: str) -> dict:
    """Cuantos invitados vs cuantos ofertaron en un procedimiento (tasa de respuesta)."""
    return wrap(queries.invitados_vs_ofertantes(nro_sicop))


@mcp.tool()
def sicop_lineas_procedimiento(nro_sicop: str) -> dict:
    """Cadena de linea completa: cartel (pidio), ofertadas, adjudicadas, contratadas, recibidas."""
    return wrap(queries.lineas_procedimiento(nro_sicop))


@mcp.tool()
def sicop_proveedor_dim(cedula: str) -> dict:
    """Registro del proveedor: tipo, tamano, zona, fechas de constitucion/expira."""
    return wrap(queries.proveedor_dim(cedula))


@mcp.tool()
def sicop_ordenes_proveedor(cedula: str, anio: str = "", limit: int = 1000) -> dict:
    """Ordenes de pedido de un proveedor (nivel EJECUCION, solo CRC sumable)."""
    return wrap(queries.ordenes_proveedor(cedula, anio or None, limit))


@mcp.tool()
def sicop_recursos_procedimiento(nro_sicop: str) -> dict:
    """Recursos de objecion de un procedimiento con su desenlace."""
    return wrap(queries.recursos_procedimiento(nro_sicop))


@mcp.tool()
def sicop_recursos_desenlace(nro_sicop: str = "", cedula: str = "", limit: int = 200) -> dict:
    """Recursos de objecion con desenlace (recurrente, resultado, PROSPERO, institucion)."""
    from sicop.models import GoldRecursosDesenlace as M

    qs = M.objects.all()
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    if cedula:
        qs = qs.filter(CEDULA_PROVEEDOR=cedula)
    return wrap(list(qs.order_by("-FECHA_PRESENTACION_RECURSO")[:limit]))


@mcp.tool()
def sicop_tiempos_por_etapa(nro_sicop: str = "", limit: int = 200) -> dict:
    """Plazos reales entre etapas por procedimiento (dias). Una fila por procedimiento (deduplicada)."""
    from sicop.models import GoldTiemposPorEtapa as M

    qs = M.objects.all()
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    # la tabla gold trae una fila por linea (duplicada); dedupe a nivel procedimiento
    rows = list(qs.order_by("NRO_SICOP")[: max(limit * 8, 1000)])
    vistos, out = set(), []
    for r in rows:
        k = (r.NRO_SICOP, r.FECHA_PUBLICACION, r.FECHA_APERTURA, r.FECHA_ADJUDICACION,
             r.FECHA_CONTRATO, r.FECHA_RECEPCION)
        if k in vistos:
            continue
        vistos.add(k)
        out.append(r)
        if len(out) >= limit:
            break
    return wrap(out)


@mcp.tool()
def sicop_precios_identicos(nro_sicop: str = "", limit: int = 200) -> dict:
    """Lineas con 2+ oferentes al mismo precio exacto (cola de revision, no conclusion)."""
    from sicop.models import GoldPreciosIdenticos as M

    qs = M.objects.all()
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    return wrap(list(qs.order_by("-REPETICION_PAR")[:limit]))


@mcp.tool()
def sicop_producto_firma(codigo_cl: str = "", marca: str = "", limit: int = 100) -> dict:
    """Firma de SKU (CL + marca + modelo + atributos) de un producto del catalogo."""
    from sicop.models import GoldProductoFirma as M

    qs = M.objects.all()
    if codigo_cl:
        qs = qs.filter(CODIGO_PRODUCTO_CL=codigo_cl)
    if marca:
        qs = qs.filter(MARCA__icontains=marca)
    return wrap(list(qs[:limit]))


@mcp.tool()
def sicop_invitados_vs_ofertantes(nro_sicop: str = "", limit: int = 200) -> dict:
    """Direccionamiento ex-ante: invitados vs ofertantes por procedimiento (tasa de respuesta)."""
    from sicop.models import GoldInvitadosVsOfertantes as M

    qs = M.objects.all()
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    return wrap(list(qs.order_by("NRO_SICOP")[:limit]))


@mcp.tool()
def sicop_regimen(nro_sicop: str = "", limit: int = 200) -> dict:
    """Regimen de evaluacion normalizado por procedimiento (PRECIO_PURO / MIXTO / SIN_PRECIO) con factores y pesos."""
    from sicop.models import GoldRegimenEvaluacion as M

    qs = M.objects.all()
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    return wrap(list(qs.order_by("NRO_SICOP")[:limit]))


@mcp.tool()
def sicop_competencia_por_regimen() -> dict:
    """Metricas de competencia re-estratificadas por regimen de evaluacion (plan Fase 0.3): gana el mas barato por regimen."""
    from sicop.models import GoldCompetenciaPorRegimen as M

    return wrap(list(M.objects.order_by("REGIMEN")))


@mcp.tool()
def sicop_ctl_deriva(conjunto: str = "", campo: str = "", anio: str = "", limit: int = 500) -> dict:
    """Mapa de deriva de esquema por anio: presente y llenado de cada campo (plan Fase 0.2). Regla: ninguna serie multianual se publica sin declarar sus huecos."""
    from sicop.models import CtlDeriva as M

    qs = M.objects.all()
    if conjunto:
        qs = qs.filter(CONJUNTO=conjunto)
    if campo:
        qs = qs.filter(CAMPO=campo)
    if anio:
        qs = qs.filter(ANIO=anio)
    return wrap(list(qs.order_by("CONJUNTO", "ANIO", "CAMPO")[:limit]))


@mcp.tool()
def sicop_catalogo_campo(tabla: str = "", campo: str = "", limit: int = 500) -> dict:
    """Diccionario de datos navegable: tipo, llenado, clave, trampa, unidad y regla de join por campo (FASE 1)."""
    from sicop.models import CatalogoCampo as M

    qs = M.objects.all()
    if tabla:
        qs = qs.filter(TABLA__icontains=tabla)
    if campo:
        qs = qs.filter(CAMPO__icontains=campo)
    return wrap(list(qs.order_by("TABLA", "CAMPO")[:limit]))


@mcp.tool()
def sicop_mes_publicacion(mes: str = "", nro_sicop: str = "", desfasados: bool = False, limit: int = 100) -> dict:
    """Mes de publicacion REAL por procedimiento (derivado de FECHA_PUBLICACION del cartel).
    MES_PUBLICACION de las tablas crudas es el primer zip donde el extractor vio la fila (trampa:
    ~21% desfasados). Con mes='YYYYMM' devuelve los procedimientos publicados ESE mes (serie temporal
    correcta); con nro_sicop devuelve el caso; con desfasados=True lista los que no coinciden."""
    from sicop.models import GoldMesPublicacion as M

    qs = M.objects.all()
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    if mes:
        qs = qs.filter(MES_REAL=mes)
    if desfasados:
        qs = qs.filter(DESFASADO="S")
    return wrap(list(qs.order_by("NRO_SICOP")[:limit]))


@mcp.tool()
def sicop_fact_requerimiento(nro_sicop: str = "", limit: int = 500) -> dict:
    """Hecho de requerimiento (cartel): lo que se pidio por linea (grano procedimiento x linea x partida)."""
    from sicop.models import FactRequerimiento as M

    qs = M.objects.all()
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    return wrap(list(qs.order_by("NRO_SICOP", "NUMERO_LINEA")[:limit]))


@mcp.tool()
def sicop_fact_oferta(nro_sicop: str = "", cedula: str = "", limit: int = 500) -> dict:
    """Hecho de oferta: quien oferto, a que precio (crc) y en que linea. Monedas no-CRC convertidas con el TC de la propia fila."""
    from sicop.models import FactOferta as M
    from sicop.queries import to_plain

    qs = M.objects.all()
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    if cedula:
        qs = qs.filter(CEDULA_PROVEEDOR=cedula)
    rows = list(qs.order_by("NRO_SICOP", "NRO_OFERTA")[:limit])
    out = []
    for r in rows:
        d = to_plain(r)
        if d.get("PU_OFERTADO_CRC") is None and (d.get("MONEDA_OFERTA") or "CRC") != "CRC":
            if d.get("TC_OFERTA") and d.get("PU_OFERTADO_ORIG") is not None:
                d["PU_OFERTADO_CRC"] = round(float(d["PU_OFERTADO_ORIG"]) * float(d["TC_OFERTA"]), 4)
                d["CRC_CONVERTIDO_EN_RESPUESTA"] = True
        out.append(d)
    return {"resultados": out, "total": len(out)}


@mcp.tool()
def sicop_fact_adjudicacion(nro_sicop: str = "", cedula: str = "", objeto_gasto: str = "", limit: int = 500) -> dict:
    """Hecho de adjudicacion: quien gano, por cuanto (crc), en que linea. Nivel: captacion."""
    from sicop.models import FactAdjudicacion as M

    qs = M.objects.all()
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    if cedula:
        qs = qs.filter(CEDULA_PROVEEDOR=cedula)
    if objeto_gasto:
        qs = qs.filter(OBJETO_GASTO=objeto_gasto)
    return wrap(list(qs.order_by("-MONTO_ADJUDICADO_CRC")[:limit]))


@mcp.tool()
def sicop_fact_contrato(nro_contrato: str = "", nro_sicop: str = "", limit: int = 500) -> dict:
    """Hecho de contrato por linea: precio contratado (crc) y descripcion (marca/modelo). Monedas no-CRC convertidas con el TC de la fila."""
    from sicop.models import FactContratoLinea as M
    from sicop.queries import to_plain

    qs = M.objects.all()
    if nro_contrato:
        qs = qs.filter(NRO_CONTRATO=nro_contrato)
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    rows = list(qs.order_by("NRO_CONTRATO", "SECUENCIA")[:limit])
    out = []
    for r in rows:
        d = to_plain(r)
        if d.get("PU_CONTRATADO_CRC") is None and (d.get("MONEDA_CONTRATO") or "CRC") != "CRC":
            if d.get("TC_CONTRATO") and d.get("PU_CONTRATADO_ORIG") is not None:
                d["PU_CONTRATADO_CRC"] = round(float(d["PU_CONTRATADO_ORIG"]) * float(d["TC_CONTRATO"]), 4)
                d["CRC_CONVERTIDO_EN_RESPUESTA"] = True
        out.append(d)
    return {"resultados": out, "total": len(out)}


@mcp.tool()
def sicop_fact_orden(nro_orden: str = "", cedula: str = "", anio: str = "", nro_sicop: str = "", limit: int = 500) -> dict:
    """Hecho de ejecucion: UNA fila por orden con TOTAL_ORDEN (solo CRC sumable). Nivel: EJECUCION. Filtra por nro_sicop si se pasa."""
    from sicop.models import FactOrden as M, SicopOrdenesPedido
    from sicop.queries import to_plain

    qs = M.objects.all()
    if nro_sicop:
        nros = list(SicopOrdenesPedido.objects.filter(NRO_SICOP=nro_sicop)
                    .values_list("NRO_ORDEN", flat=True).distinct()[:10000])
        if not nros:
            return {"resultados": [], "total": 0, "nota": f"sin ordenes para nro_sicop {nro_sicop}"}
        qs = qs.filter(NRO_ORDEN__in=nros)
    if nro_orden:
        qs = qs.filter(NRO_ORDEN=nro_orden)
    if cedula:
        qs = qs.filter(CEDULA_PROVEEDOR=cedula)
    if anio:
        qs = qs.filter(FECHA_ELABORACION__year=anio)
    rows = list(qs.order_by("-FECHA_ELABORACION")[:limit])
    out = []
    for r in rows:
        d = to_plain(r)
        if nro_sicop:
            d["NRO_SICOP"] = nro_sicop
        out.append(d)
    return {"resultados": out, "total": len(out)}


@mcp.tool()
def sicop_fact_recepcion(nro_contrato: str = "", nro_sicop: str = "", limit: int = 500) -> dict:
    """Hecho de recepcion por linea: cantidad recibida, estado y dias de adelanto/atraso."""
    from sicop.models import FactRecepcion as M

    qs = M.objects.all()
    if nro_contrato:
        qs = qs.filter(NRO_CONTRATO=nro_contrato)
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    return wrap(list(qs.order_by("NRO_CONTRATO", "SECUENCIA")[:limit]))


@mcp.tool()
def sicop_gold_status(corrida: str = "") -> dict:
    """Estado del gold: corridas, tests como gate y ctl_deriva (FASE 1 publicacion atomica)."""
    from sicop.models import CtlCorrida, CtlTest

    corridas = list(CtlCorrida.objects.order_by("-INICIADO_EN")[:10])
    tests = list(CtlTest.objects.order_by("-id")[:50])
    return {
        "corridas": wrap(corridas),
        "tests": wrap(tests),
    }


# ---- FASE 2: ciclo diario, resultado_decision, senales, vigilancia ----

@mcp.tool()
def sicop_resultado(nro_sicop: str = "", estado: str = "", limit: int = 100) -> dict:
    """Decisiones registradas (SCH_RESULTADO): grano (nro_sicop, nro_linea, decision_id)."""
    from sicop.models import ResultadoDecision as M

    qs = M.objects.filter(es_vigente=True)
    if nro_sicop:
        qs = qs.filter(nro_sicop=nro_sicop)
    if estado:
        qs = qs.filter(estado_resultado=estado)
    return wrap(list(qs.order_by("-fecha_decision")[:limit]))


@mcp.tool()
def sicop_registrar_resultado(nro_sicop: str, nro_linea: str, decision: str,
                              build_id: str, modelo_version: str, features_hash: str,
                              snapshot_ts: str = "", precio_recomendado: float = None,
                              prob_exito_estimada: float = None, motivo_no_ofertar: str = "",
                              canal_entrada: str = "MONITOREO", moneda_recomendada: str = "CRC",
                              override: bool = False, override_motivo: str = "",
                              decidido_por: str = "AGENTE:assistant", corrida_id: str = "") -> dict:
    """REGISTRA una decision de oferta/participacion (append-only, contexto congelado obligatorio)."""
    from datetime import datetime
    from django.utils import timezone
    from sicop import resultado

    try:
        obj = resultado.registrar_resultado(
            nro_sicop=nro_sicop, nro_linea=nro_linea, decision=decision,
            build_id=build_id, snapshot_ts=timezone.now(), modelo_version=modelo_version,
            features_hash=features_hash, canal_entrada=canal_entrada,
            precio_recomendado=precio_recomendado, prob_exito_estimada=prob_exito_estimada,
            motivo_no_ofertar=motivo_no_ofertar or None, moneda_recomendada=moneda_recomendada,
            override=override, override_motivo=override_motivo or None,
            decidido_por=decidido_por, corrida_id=corrida_id or None,
        )
    except (ValueError, TypeError) as e:
        return {"error": str(e)}
    return {"resultado_id": str(obj.resultado_id), "estado": "PENDIENTE"}


@mcp.tool()
def sicop_senales(estado: str = "", limit: int = 100) -> dict:
    """Cola de senales del dia (watchlist): tipo, prioridad, nro_sicop, evidencia."""
    from sicop.models import Senal as M

    qs = M.objects.all()
    if estado:
        qs = qs.filter(estado=estado)
    return wrap(list(qs.order_by("-fecha")[:limit]))


@mcp.tool()
def sicop_vigilancia(limit: int = 50) -> dict:
    """Ultimos chequeos de reescritura de la fuente (meses objetivo)."""
    from sicop.models import VigilanciaCheck as M

    return wrap(list(M.objects.order_by("-fecha")[:limit]))


@mcp.tool()
def sicop_corrida_pasos(corrida: str = "", limit: int = 100) -> dict:
    """Log estructurado del pipeline por corrida (tc_dia, vigilancia, extractor,
    recarga, silver, gold, tests) con estado, detalle, filas y duracion. Sin
    corrida devuelve los ultimos pasos de todas las corridas."""
    from sicop.models import CorridaPaso as M

    qs = M.objects.all()
    if corrida:
        qs = qs.filter(corrida=corrida)
    return wrap(list(qs.order_by("-id")[:limit]))


@mcp.tool()
def sicop_verificar_procedimiento(nro_sicop: str) -> dict:
    """Verifica si una licitacion (nro_sicop) esta COMPLETA en nuestra base:
    cartel, lineas del cartel, ofertas, adjudicaciones, adjudicacion firme,
    contratos, ordenes y recepciones. Si algo da 0, la licitacion puede existir
    en SICOP pero faltar aca -> usar sicop_reparar_mes para el mes."""
    from sicop.models import (SicopAdjudicaciones, SicopAdjudicacionesFirme,
                              SicopCarteles, SicopContratos, SicopLineasCartel,
                              SicopOfertas, SicopOrdenesPedido, SicopRecepciones)

    tabs = {
        "cartel": SicopCarteles,
        "lineas_cartel": SicopLineasCartel,
        "ofertas": SicopOfertas,
        "adjudicaciones": SicopAdjudicaciones,
        "adjudicacion_firme": SicopAdjudicacionesFirme,
        "contratos": SicopContratos,
        "ordenes_pedido": SicopOrdenesPedido,
        "recepciones": SicopRecepciones,
    }
    conteos = {n: M.objects.filter(NRO_SICOP=nro_sicop).count() for n, M in tabs.items()}
    completo = conteos["cartel"] > 0 and conteos["lineas_cartel"] > 0 and conteos["adjudicaciones"] > 0
    return {
        "nro_sicop": nro_sicop,
        "conteos": conteos,
        "completo": completo,
        "nota": "si el cartel/lineas da 0 pero sabes que existe en SICOP, el mes no se extrajo -> sicop_reparar_mes",
    }


@mcp.tool()
def sicop_reparar_mes(aaaamm: str, reextraer: bool = False) -> dict:
    """REPARA un mes (AAAAMM, ej 202608): modo liviano por defecto (NO re-descarga:
    reutiliza la extraccion del anio ya en SICOP_RECOVERY_DIR; las reescrituras reales
    de la fuente las detecta el ciclo diario), broncea el mes, reconstruye silver+gold
    y corre el gate. Con reextraer=True fuerza re-descarga completa del anio desde la
    fuente (lento y usa ~200 GB de disco transitorio; solo si sabes que cambio de verdad).
    Es async: devuelve la corrida; consulta sicop_corrida_pasos para el resultado."""
    from sicop.tasks import reparar_mes as t

    aaaamm = aaaamm.strip()
    if not (len(aaaamm) == 6 and aaaamm.isdigit()):
        return {"error": "aaaamm debe ser YYYYMM (ej 202608)"}
    res = t.delay(aaaamm, reextraer=reextraer)
    return {"aaaamm": aaaamm, "corrida": f"reparar-{aaaamm}", "estado": "ENCOLADO",
            "reextraer": reextraer,
            "nota": "modo liviano (sin re-descarga) por defecto; monitorear con sicop_corrida_pasos"}


@mcp.tool()
def sicop_reconciliar(anio: str = "", solo_reporte: bool = True) -> dict:
    """Reconciliacion: revisa mes por mes si la fuente publico un ZIP pero nuestra
    base esta VACIA (hueco real). Usa lineas_cartel como senal de presencia (la
    mas consistente; carteles/ofertas varian por mes de publicacion). Con
    solo_reporte=True devuelve los meses con hueco; con False, encola
    sicop_reparar_mes para cada uno."""
    from django.db.models import Count

    from sicop import vigilancia
    from sicop.models import SicopLineasCartel

    hoy = __import__("datetime").datetime.now()
    actual = int(f"{hoy.year:04d}{hoy.month:02d}")
    meses = [v for v in range(202001, actual + 1) if 1 <= v % 100 <= 12]
    if anio:
        meses = [m for m in meses if str(m)[:4] == anio]

    lc_por_mes = {r["MES_PUBLICACION"]: r["n"] for r in
                  SicopLineasCartel.objects.values("MES_PUBLICACION").annotate(n=Count("id"))}

    from concurrent.futures import ThreadPoolExecutor

    # Quirks de publicacion VERIFICADOS por re-extraccion (2026-08): la fuente
    # publico el mes pero NO taguea lineas_cartel bajo ese aaaamm (los datos de
    # esos procedimientos estan bajo otros meses de publicacion). Re-extraer no
    # agrega nada: NO son huecos reparables y NO hay que re-disparar reparaciones.
    QUIRKS_VERIFICADOS = {"202005", "202008", "202108"}

    def _check(m):
        # I/O-bound (HTTP HEAD a la fuente) -> paralelo; ~10 concurrentes
        h = vigilancia._head(str(m))
        existe = h.get("status") == 200 and not h.get("error")
        return (m, existe, lc_por_mes.get(str(m), 0))

    huecos, quirks = [], []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for m, existe_fuente, n_lc in ex.map(_check, meses):
            if not existe_fuente:
                continue
            if n_lc == 0:
                item = {"aaaamm": str(m), "lineas_cartel": n_lc,
                        "fuente": "zip publicado, base vacia (sin lineas_cartel)"}
                (quirks if str(m) in QUIRKS_VERIFICADOS else huecos).append(item)

    reparados = []
    if not solo_reporte and huecos:
        from sicop.tasks import reparar_mes as t
        for g in huecos:
            t.delay(g["aaaamm"])
            reparados.append(g["aaaamm"])
    return {"total_meses": len(meses), "huecos": huecos, "reparados_encolados": reparados,
            "quirks_verificados": quirks,
            "nota": "hueco real = la fuente publico el mes pero nuestra base no tiene NINGUNA linea del cartel (senal de presencia confiable). quirks_verificados: la fuente publico el mes pero NO taguea lineas_cartel bajo el (verificado por re-extraccion); NO re-extraer."}


@mcp.tool()
def sicop_diagnostico() -> dict:
    """Diagnostico de salud del sistema: que necesita atencion (tests fallidos,
    meses con huecos, ultima corrida, recencia de datos, senales). La base para
    que un agente decida que reparar/gestionar."""
    from django.db.models import Count

    from sicop.models import (CtlCorrida, CtlTest, CorridaPaso, Senal,
                              SicopLineasCartel)

    # 1) tests con FAIL (mas recientes)
    fails = list(CtlTest.objects.filter(RESULTADO="FAIL")
                 .values("CORRIDA_ID", "TEST", "VALOR_OBTENIDO").order_by("-id")[:10])

    # 2) ultima corrida
    ultima = list(CtlCorrida.objects.order_by("-INICIADO_EN")[:3].values(
        "CORRIDA_ID", "ESTADO", "NOTAS", "INICIADO_EN"))

    # 3) meses con 0 lineas_cartel en nuestra base (posible hueco, sin HEAD a fuente)
    con_datos = set(SicopLineasCartel.objects.values_list("MES_PUBLICACION", flat=True).distinct())
    hoy = __import__("datetime").datetime.now()
    actual = int(f"{hoy.year:04d}{hoy.month:02d}")
    meses_vacio = [v for v in range(202001, actual + 1) if 1 <= v % 100 <= 12 and str(v) not in con_datos]

    # 4) recencia por tabla clave
    recencia = {}
    for tabla, campo in [("sicop_adjudicaciones", "MES_PUBLICACION"),
                         ("sicop_ofertas", "MES_PUBLICACION"),
                         ("sicop_ordenes_pedido", "MES_PUBLICACION"),
                         ("sicop_invitaciones", "MES_PUBLICACION")]:
        try:
            from django.apps import apps
            M = apps.get_model("sicop", {  # mapa nombre -> modelo
                "sicop_adjudicaciones": "SicopAdjudicaciones",
                "sicop_ofertas": "SicopOfertas",
                "sicop_ordenes_pedido": "SicopOrdenesPedido",
                "sicop_invitaciones": "SicopInvitaciones",
            }[tabla])
            mx = M.objects.filter(MES_PUBLICACION__isnull=False).order_by("-MES_PUBLICACION").values_list("MES_PUBLICACION", flat=True).first()
            recencia[tabla] = mx
        except Exception:  # noqa: BLE001
            recencia[tabla] = None

    # 5) senales abiertas
    n_senales = Senal.objects.filter(estado="DETECTADA").count()

    return {
        "tests_fallidos": fails,
        "ultima_corrida": ultima,
        "meses_sin_lineas_cartel": meses_vacio,
        "recencia_max_mes": recencia,
        "senales_detectadas": n_senales,
        "recomendacion": "correr sicop_reconciliar(solo_reporte=True) para HEAD a la fuente y confirmar huecos reales; luego sicop_reparar_mes para cada hueco",
    }


@mcp.tool()
def sicop_ciclo_diario(corrida: str = "") -> dict:
    """EJECUTA el ciclo diario de las 06:00: vigilancia + consolidar + senales + cola + gold."""
    from sicop.ciclo import ciclo_diario

    return ciclo_diario(corrida=corrida or None, reprocesar=False, gold=False)


# ---- FASE 3: enforcement, dos carriles, registro ----

CARRIL = os.environ.get("SICOP_CARRIL", "operacion")


@mcp.tool()
def sicop_politica() -> dict:
    """Pruebas de politica (enforcement FASE 3): ruta cruda, SQL libre, mezcla de monedas. Si alguna falla, la entrega falla."""
    from sicop.enforcement import pruebas_politica

    return {"resultados": pruebas_politica("politica")}


@mcp.tool()
def sicop_registro(limit: int = 50) -> dict:
    """Auditoria de respuestas: agente, herramienta, params, build_id, conteo, carril."""
    from sicop.models import RegistroRespuesta as M

    return wrap(list(M.objects.order_by("-timestamp")[:limit]))


@mcp.tool()
def sicop_actividad_mcp(horas: int = 24, herramienta: str = "", limit: int = 30) -> dict:
    """Actividad reciente del MCP: quien pidio que (agente), por hora, tools top y las ultimas llamadas. Para monitorear el uso desde claude.ai u otros clientes MCP."""
    from datetime import timedelta

    from django.db.models import Count
    from django.utils import timezone

    from sicop.models import RegistroRespuesta as M

    horas = max(1, min(horas, 24 * 30))
    desde = timezone.now() - timedelta(hours=horas)
    qs = M.objects.filter(timestamp__gte=desde)
    if herramienta:
        qs = qs.filter(herramienta__iexact=herramienta)

    por_hora = {}
    for ts, in qs.values_list("timestamp"):
        k = ts.strftime("%m-%d %H:00")
        por_hora[k] = por_hora.get(k, 0) + 1
    por_hora = [{"hora": k, "llamadas": v} for k, v in sorted(por_hora.items())]

    return {
        "desde_hace_horas": horas,
        "total_llamadas": qs.count(),
        "por_hora": por_hora,
        "herramientas_top": list(
            qs.values("herramienta").annotate(n=Count("id")).order_by("-n")[:12]
        ),
        "agentes_top": list(qs.values("agente").annotate(n=Count("id")).order_by("-n")[:12]),
        "ultimas": wrap(list(qs.order_by("-timestamp")[:limit])),
    }


@mcp.tool()
def sicop_carril() -> dict:
    """Carril actual del MCP: operacion (canonico) o laboratorio (NO_APTO_PARA_DECISION)."""
    return {
        "carril": CARRIL,
        "decision_eligible": CARRIL == "operacion",
        "etiqueta": "NO_APTO_PARA_DECISION" if CARRIL != "operacion" else "canonica",
        "aviso": "En laboratorio toda respuesta se etiqueta NO_APTO_PARA_DECISION",
    }


if CARRIL == "laboratorio":

    @mcp.tool()
    def sicop_lab_sql(consulta: str) -> dict:
        """[LABORATORIO] SQL read-only sobre la base. SOLO SELECT/WITH, max 200 filas. Salida NO_APTO_PARA_DECISION."""
        from django.db import connection, transaction

        c = consulta.strip().upper()
        if not (c.startswith("SELECT") or c.startswith("WITH")):
            raise ValueError("solo SELECT/WITH en laboratorio")
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(consulta.rstrip().rstrip(";") + " LIMIT 200")
                cols = [d[0] for d in (cur.description or [])]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return {"etiqueta": "NO_APTO_PARA_DECISION", "decision_eligible": False, "filas": len(rows), "datos": rows}


from sicop import registro as _registro_mod

_registro_mod.wrap_mcp_call_tool(mcp)


# ---- FASE 4: prueba + pendientes ----

@mcp.tool()
def sicop_ficha_esosa() -> dict:
    """FASE 4 (prueba del plan): rehace la ficha del competidor ESOSA (3101086562) vs SONDEL (3101095926) desde la capa canonica."""
    from sicop.fase4 import ficha_esosa

    return ficha_esosa()


@mcp.tool()
def sicop_backtest_invitaciones() -> dict:
    """FASE 4: replay de invitaciones pasadas (con cuanto descuento se gana)."""
    from sicop.fase4 import backtest_invitaciones

    return backtest_invitaciones()


@mcp.tool()
def sicop_holdout() -> dict:
    """FASE 4: holdout temporal (<=2024 vs 2025-26) + gate de muerte del modelo."""
    from sicop.fase4 import holdout

    return holdout()


@mcp.tool()
def sicop_pendientes(solo: str = "") -> dict:
    """Pendientes del traspaso: p1_conversion_cartera, p3_catalogo_familias, p5_recurrente_vs_recurrido, p6_sanciones_vigencia, p7_tamano_historico."""
    from sicop.pendientes import run

    names = [n.strip() for n in solo.split(",") if n.strip()] if solo else None
    return run(names)


@mcp.tool()
def sicop_cgr_buscar(termino: str, page: int = 1, limit: int = 15) -> dict:
    """Buscador CGR: PDFs de resoluciones por termino (ej. un NRO_SICOP). USO DIRIGIDO, no barrido; gate legal pendiente."""
    from sicop.cgr import buscar

    return buscar(termino, page, limit)


@mcp.tool()
def sicop_bccr_tc(fecha: str = "") -> dict:
    """Tipo de cambio CRC/USD del dia guardado en ctl_bccr_tc (se consulta UNA vez en la manana en el ciclo diario y se lee de ahi el resto del dia; no golpea la API del BCCR por pregunta). BCCR oficial si hay token, si no el implicito de la fuente, marcado como tal."""
    from datetime import date
    from sicop.bccr import tipo_cambio

    return tipo_cambio(date.fromisoformat(fecha) if fecha else date.today())


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Servidor MCP SICOP")
    ap.add_argument("transport", nargs="?", default="stdio", choices=["stdio", "sse", "streamable-http"])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--path", default="/mcp")
    ap.add_argument("--json", action="store_true", help="Respuestas JSON planas en vez de SSE")
    args = ap.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "streamable-http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port,
                streamable_http_path=args.path, json_response=args.json)
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)
