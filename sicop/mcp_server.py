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
        return {"resultados": value, "total": len(value)}
    return value


mcp = MCPServer(
    "sicop",
    instructions=(
        "Sistema de inteligencia sobre datos abiertos de contratacion publica de Costa Rica (SICOP, 2020-2026). "
        "NIVEL DE MEDICION: toda cifra de negocio de un proveedor debe declarar si mide captacion "
        "(adjudicaciones), ejecucion (ordenes de pedido) o entrega (recepciones). Consultar un proveedor "
        "por captacion lo subestima hasta 59x frente a su ejecucion real."
    ),
)


@mcp.tool()
def sicop_ficha_proveedor(cedula: str) -> dict:
    """Ficha completa de un proveedor (por cedula, ej 3101029593): adjudicaciones por anio, cartera ejecucion vs captacion, desempeno de entrega y familias top."""
    return queries.ficha_proveedor(cedula)


@mcp.tool()
def sicop_mercado_familia(familia_unspsc: str) -> dict:
    """Estructura de mercado de una familia UNSPSC (8 digitos, ej 461816 o 81112399): adjudicatarios top, productos del catalogo y desempeno."""
    return queries.mercado_familia(familia_unspsc)


@mcp.tool()
def sicop_competencia_procedimiento(nro_sicop: str) -> dict:
    """Oferentes por linea de un procedimiento (nro_sicop): quien oferto, a que precio, quien gano y el delta contra el ganador."""
    return queries.competencia_procedimiento(nro_sicop)


@mcp.tool()
def sicop_producto(codigo_cl: str) -> list:
    """Ficha de un producto del catalogo por CODIGO_PRODUCTO_CL (16 digitos): descripcion, marca, modelo, quienes lo proveen y compran."""
    return wrap(queries.producto(codigo_cl))


@mcp.tool()
def sicop_expediente(nro_sicop: str) -> dict:
    """Trazabilidad de un procedimiento (nro_sicop): que tramos tiene completos (cartel, ofertas, acto firme, adjudicado, contrato, garantia, recibido)."""
    return queries.expediente(nro_sicop)


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
    return queries.resumen()


@mcp.tool()
def sicop_cara_a_cara(cedula_a: str, cedula_b: str, familia_unspsc: str = "") -> dict:
    """Cara a cara de dos proveedores (plan: cara_a_cara): lineas donde ambos ofertaron, victorias, veces mas barato cada uno, familias compartidas y perfiles captacion/ejecucion."""
    return queries.cara_a_cara(cedula_a, cedula_b, familia_unspsc or None)


@mcp.tool()
def sicop_producto_historia(codigo_cl: str) -> dict:
    """Historia de un producto (CODIGO_PRODUCTO_CL de 16 digitos): catalogo, secuencia de precios ofertados por anio (mediana/min/max), adjudicaciones, proveedores top y quien paga de mas por institucion."""
    return queries.producto_historia(codigo_cl)


@mcp.tool()
def sicop_campo_buscar(termino: str, limit: int = 20) -> dict:
    """Busqueda por termino en el catalogo de productos (descripcion/marca/modelo), proveedores e instituciones (plan: campo_buscar)."""
    return queries.campo_buscar(termino, limit)


@mcp.tool()
def sicop_perdidas_baratas(cedula: str = "", familia_unspsc: str = "", limit: int = 200) -> dict:
    """Lineas donde un proveedor oferto MAS BARATO que el ganador y aun asi perdio (cola de revision, no conclusion)."""
    return queries.perdidas_baratas(cedula, familia_unspsc or None, limit)


@mcp.tool()
def sicop_regimen_evaluacion(nro_sicop: str) -> dict:
    """Regimen de evaluacion de un procedimiento (factores y pesos de evaluacion_ofertas)."""
    return queries.regimen_evaluacion(nro_sicop)


@mcp.tool()
def sicop_invitaciones_procedimiento(nro_sicop: str, limit: int = 500) -> dict:
    """Quien fue invitado a un procedimiento (contratacion directa). Direccionamiento ex-ante."""
    return queries.invitaciones_procedimiento(nro_sicop, limit)


@mcp.tool()
def sicop_invitaciones_proveedor(cedula: str, limit: int = 200) -> dict:
    """Procedimientos donde un proveedor fue invitado (plan: invitaciones_pendientes)."""
    return queries.invitaciones_proveedor(cedula, limit)


@mcp.tool()
def sicop_invitados_vs_ofertantes(nro_sicop: str) -> dict:
    """Cuantos invitados vs cuantos ofertaron en un procedimiento (tasa de respuesta)."""
    return queries.invitados_vs_ofertantes(nro_sicop)


@mcp.tool()
def sicop_lineas_procedimiento(nro_sicop: str) -> dict:
    """Cadena de linea completa: cartel (pidio), ofertadas, adjudicadas, contratadas, recibidas."""
    return queries.lineas_procedimiento(nro_sicop)


@mcp.tool()
def sicop_proveedor_dim(cedula: str) -> dict:
    """Registro del proveedor: tipo, tamano, zona, fechas de constitucion/expira."""
    return queries.proveedor_dim(cedula)


@mcp.tool()
def sicop_ordenes_proveedor(cedula: str, anio: str = "", limit: int = 1000) -> dict:
    """Ordenes de pedido de un proveedor (nivel EJECUCION, solo CRC sumable)."""
    return queries.ordenes_proveedor(cedula, anio or None, limit)


@mcp.tool()
def sicop_recursos_procedimiento(nro_sicop: str) -> dict:
    """Recursos de objecion de un procedimiento con su desenlace."""
    return queries.recursos_procedimiento(nro_sicop)


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
    """Plazos reales entre etapas por procedimiento (dias)."""
    from sicop.models import GoldTiemposPorEtapa as M

    qs = M.objects.all()
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    return wrap(list(qs.order_by("NRO_SICOP")[:limit]))


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
        qs = qs.filter(TABLA=tabla)
    if campo:
        qs = qs.filter(CAMPO=campo)
    return wrap(list(qs.order_by("TABLA", "CAMPO")[:limit]))


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
    """Hecho de oferta: quien oferto, a que precio (crc) y en que linea."""
    from sicop.models import FactOferta as M

    qs = M.objects.all()
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    if cedula:
        qs = qs.filter(CEDULA_PROVEEDOR=cedula)
    return wrap(list(qs.order_by("NRO_SICOP", "NRO_OFERTA")[:limit]))


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
    """Hecho de contrato por linea: precio contratado (crc) y descripcion (marca/modelo)."""
    from sicop.models import FactContratoLinea as M

    qs = M.objects.all()
    if nro_contrato:
        qs = qs.filter(NRO_CONTRATO=nro_contrato)
    if nro_sicop:
        qs = qs.filter(NRO_SICOP=nro_sicop)
    return wrap(list(qs.order_by("NRO_CONTRATO", "SECUENCIA")[:limit]))


@mcp.tool()
def sicop_fact_orden(nro_orden: str = "", cedula: str = "", anio: str = "", limit: int = 500) -> dict:
    """Hecho de ejecucion: UNA fila por orden con TOTAL_ORDEN (solo CRC sumable). Nivel: EJECUCION."""
    from sicop.models import FactOrden as M

    qs = M.objects.all()
    if nro_orden:
        qs = qs.filter(NRO_ORDEN=nro_orden)
    if cedula:
        qs = qs.filter(CEDULA_PROVEEDOR=cedula)
    if anio:
        qs = qs.filter(FECHA_ELABORACION__year=anio)
    return wrap(list(qs.order_by("-FECHA_ELABORACION")[:limit]))


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
def sicop_reparar_mes(aaaamm: str) -> dict:
    """REPARA un mes (AAAAMM, ej 202608): re-extrae el anio desde la fuente SICOP,
    recarga Postgres, broncea el mes, reconstruye silver+gold y corre el gate.
    Es async: devuelve la corrida; consulta sicop_corrida_pasos para el resultado."""
    from sicop.tasks import reparar_mes as t

    aaaamm = aaaamm.strip()
    if not (len(aaaamm) == 6 and aaaamm.isdigit()):
        return {"error": "aaaamm debe ser YYYYMM (ej 202608)"}
    res = t.delay(aaaamm)
    return {"aaaamm": aaaamm, "corrida": f"reparar-{aaaamm}", "estado": "ENCOLADO",
            "nota": "monitorear con sicop_corrida_pasos; tarda ~20 min"}


@mcp.tool()
def sicop_reconciliar(anio: str = "", solo_reporte: bool = True) -> dict:
    """Reconciliacion: revisa mes por mes si la fuente publico un ZIP pero nuestra
    base esta VACIA (hueco). Con solo_reporte=True devuelve los meses con hueco;
    con False, encola sicop_reparar_mes para cada uno."""
    from django.db.models import Count

    from sicop import vigilancia
    from sicop.models import SicopAdjudicaciones, SicopOfertas

    hoy = __import__("datetime").datetime.now()
    actual = int(f"{hoy.year:04d}{hoy.month:02d}")
    meses = [v for v in range(202001, actual + 1) if 1 <= v % 100 <= 12]
    if anio:
        meses = [m for m in meses if str(m)[:4] == anio]

    adj_por_mes = {r["MES_PUBLICACION"]: r["n"] for r in
                   SicopAdjudicaciones.objects.values("MES_PUBLICACION").annotate(n=Count("id"))}
    of_por_mes = {r["MES_PUBLICACION"]: r["n"] for r in
                  SicopOfertas.objects.values("MES_PUBLICACION").annotate(n=Count("id"))}

    huecos = []
    for m in meses:
        h = vigilancia._head(str(m))
        existe_fuente = h.get("status") == 200 and not h.get("error")
        if not existe_fuente:
            continue
        n_adj = adj_por_mes.get(str(m), 0)
        n_of = of_por_mes.get(str(m), 0)
        if n_adj == 0 and n_of == 0:
            huecos.append({"aaaamm": str(m), "adjudicaciones": n_adj, "ofertas": n_of,
                           "fuente": "zip publicado, base vacia"})

    reparados = []
    if not solo_reporte and huecos:
        from sicop.tasks import reparar_mes as t
        for g in huecos:
            t.delay(g["aaaamm"])
            reparados.append(g["aaaamm"])
    return {"total_meses": len(meses), "huecos": huecos, "reparados_encolados": reparados,
            "nota": "hueco = la fuente publico el mes pero nuestra base no tiene adjudicaciones ni ofertas"}


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
