"""API REST v1 sobre los datos SICOP."""
from django.db.models import Count, Sum
from django.db import connection
from rest_framework import viewsets, filters
from rest_framework.decorators import api_view
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.renderers import JSONRenderer, TemplateHTMLRenderer
from rest_framework.response import Response

from sicop import models as m
from .serializers import serializer_for

# Mapa: sufijo de tabla -> (modelo, prefijo de ruta)
MODEL_TABLES = [
    (m.SicopAdjudicaciones, "adjudicaciones"),
    (m.SicopAdjudicacionesFirme, "adjudicaciones-firme"),
    (m.SicopCarteles, "carteles"),
    (m.SicopContratos, "contratos"),
    (m.SicopEtapas, "etapas"),
    (m.SicopEvaluacionOfertas, "evaluacion-ofertas"),
    (m.SicopGarantias, "garantias"),
    (m.SicopInhibiciones, "inhibiciones"),
    (m.SicopInstituciones, "instituciones"),
    (m.SicopProcedimientosAdm, "procedimientos-adm"),
    (m.SicopReajustes, "reajustes"),
    (m.SicopRemates, "remates"),
    (m.SicopSancionesRegistro, "sanciones-registro"),
    (m.GoldCatalogoProductos, "catalogo"),
    (m.GoldCarteraProveedor, "cartera"),
    (m.GoldCarteraResumen, "cartera-resumen"),
    (m.GoldDesempenoProveedor, "desempeno"),
    (m.GoldDesempenoPorFamilia, "desempeno-familia"),
    (m.GoldAtributosProducto, "atributos"),
    (m.GoldPrecioPorInstitucion, "precio-institucion"),
    (m.GoldBaratoYProrrogado, "barato-prorrogado"),
    (m.GoldBaratoYProrrogadoResumen, "barato-prorrogado-resumen"),
    (m.GoldRepresentanteEmpresas, "representantes"),
    (m.GoldRepresentanteCompetencia, "representantes-competencia"),
    (m.GoldExcepcionesPorAdjudicatario, "excepciones"),
    (m.GoldSancionesProveedores, "sanciones-proveedores"),
    (m.GoldCartelesObjetados, "carteles-objetados"),
    (m.GoldExpedienteTrazabilidad, "expedientes"),
    (m.GoldInvitacionesConcentracion, "invitaciones-concentracion"),
    (m.GoldRankingCaptacionEjecucion, "ranking"),
    (m.GoldCompetenciaPorLinea, "competencia"),
    (m.GoldRecursosDesenlace, "recursos-desenlace"),
    (m.GoldTiemposPorEtapa, "tiempos-por-etapa"),
    (m.GoldPreciosIdenticos, "precios-identicos"),
    (m.GoldProductoFirma, "producto-firma"),
    (m.GoldRegimenEvaluacion, "regimen"),
    (m.GoldCompetenciaPorRegimen, "competencia-por-regimen"),
    (m.CtlDeriva, "ctl-deriva"),
    (m.CatalogoCampo, "catalogo-campo"),
    (m.CtlCorrida, "ctl-corrida"),
    (m.CtlTest, "ctl-test"),
    (m.CorridaPaso, "corrida-paso"),
    (m.CtlMesFuente, "ctl-mes-fuente"),
    (m.CtlEsquema, "ctl-esquema"),
    (m.CtlCuarentena, "ctl-cuarentena"),
    (m.BronzeFila, "bronze"),
    (m.FactRequerimiento, "fact-requerimiento"),
    (m.FactOferta, "fact-oferta"),
    (m.FactAdjudicacion, "fact-adjudicacion"),
    (m.FactContratoLinea, "fact-contrato-linea"),
    (m.FactOrden, "fact-orden"),
    (m.FactRecepcion, "fact-recepcion"),
    (m.ResultadoDecision, "resultados"),
    (m.Senal, "senales"),
    (m.VigilanciaCheck, "vigilancia"),
]

# Columnas por modelo que se filtran por igualdad desde query params.
FILTERABLE = {
    "SicopAdjudicaciones": ["CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR", "CEDULA", "NRO_SICOP", "ANO", "MES_PUBLICACION", "OBJETO_GASTO", "TIPO_PROCEDIMIENTO", "MODALIDAD_PROCEDIMIENTO", "PROD_ID"],
    "SicopCarteles": ["NRO_SICOP", "CEDULA_INSTITUCION", "TIPO_PROCEDIMIENTO", "MODALIDAD_PROCEDIMIENTO", "CARTEL_STAT", "MES_PUBLICACION"],
    "SicopContratos": ["NRO_SICOP", "NRO_CONTRATO", "CEDULA_PROVEEDOR", "CEDULA_INSTITUCION", "TIPO_CONTRATO", "MES_PUBLICACION"],
    "SicopEtapas": ["NRO_SICOP", "MES_PUBLICACION"],
    "SicopGarantias": ["NRO_SICOP", "CEDULA_PROVEEDOR", "CEDULA_INSTITUCION", "TIPO_GARANTIA"],
    "SicopInhibiciones": ["CED_INSTITUCION", "NOM_FUNCIONARIO", "ESTADO"],
    "SicopInstituciones": ["CEDULA", "NOMBRE_INSTITUCION"],
    "SicopAdjudicacionesFirme": ["NRO_SICOP", "MES_PUBLICACION"],
    "GoldCatalogoProductos": ["FAMILIA_UNSPSC", "MARCA", "MARCA_PLAUSIBLE"],
    "GoldCarteraProveedor": ["CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR", "ANIO_EJECUCION"],
    "GoldDesempenoProveedor": ["CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR"],
    "GoldDesempenoPorFamilia": ["CEDULA_PROVEEDOR", "FAMILIA_UNSPSC"],
    "GoldCompetenciaPorLinea": ["NRO_SICOP", "CEDULA_PROVEEDOR", "CODIGO_PRODUCTO"],
    "GoldExpedienteTrazabilidad": ["NRO_SICOP", "CEDULA_INSTITUCION"],
    "GoldCartelesObjetados": ["NRO_SICOP", "CEDULA_INSTITUCION", "MES_PUBLICACION"],
    "GoldRepresentanteCompetencia": ["CEDULA_REPRESENTANTE", "NRO_SICOP"],
    "GoldRepresentanteEmpresas": ["CEDULA_REPRESENTANTE", "REPRESENTANTE"],
    "GoldPrecioPorInstitucion": ["FAMILIA_UNSPSC", "MARCA", "MODELO", "ANIO"],
    "GoldSancionesProveedores": ["CEDULAS_PROVEEDOR", "NOMBRES_PROVEEDOR"],
    "GoldExcepcionesPorAdjudicatario": ["CEDULA_PROVEEDOR", "CAUSAL_EXCEPCION"],
    "GoldInvitacionesConcentracion": ["CEDULA_INSTITUCION", "INSTITUCION"],
    "GoldAtributosProducto": ["CODIGO_PRODUCTO_CL", "FAMILIA_UNSPSC", "TIPO_ATRIBUTO"],
    "GoldBaratoYProrrogado": ["NRO_SICOP", "ANIO"],
    "GoldRankingCaptacionEjecucion": ["CEDULA_PROVEEDOR"],
    "FactRequerimiento": ["NRO_SICOP", "NUMERO_LINEA"],
    "FactOferta": ["NRO_SICOP", "CEDULA_PROVEEDOR"],
    "FactAdjudicacion": ["NRO_SICOP", "CEDULA_PROVEEDOR", "OBJETO_GASTO"],
    "FactContratoLinea": ["NRO_CONTRATO", "NRO_SICOP", "CEDULA_PROVEEDOR"],
    "FactOrden": ["NRO_ORDEN", "CEDULA_PROVEEDOR"],
    "FactRecepcion": ["NRO_CONTRATO", "NRO_SICOP"],
    "CatalogoCampo": ["TABLA", "CAMPO", "ES_CLAVE"],
    "CtlDeriva": ["CONJUNTO", "CAMPO", "ANIO"],
    "BronzeFila": ["CONJUNTO", "MES"],
}

SEARCH_FIELDS = {
    "SicopAdjudicaciones": ["NOMBRE_PROVEEDOR", "DESCR_PROCEDIMIENTO", "NRO_SICOP", "INSTITUCION"],
    "GoldCatalogoProductos": ["DESCRIPCION", "MARCA", "MODELO"],
    "GoldCarteraProveedor": ["NOMBRE_PROVEEDOR"],
    "GoldDesempenoProveedor": ["NOMBRE_PROVEEDOR"],
    "SicopInstituciones": ["NOMBRE_INSTITUCION"],
}


class SicopViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        qs = super().get_queryset()
        filters_map = FILTERABLE.get(self.queryset.model.__name__, [])
        for key, val in self.request.query_params.items():
            if key in filters_map and val:
                qs = qs.filter(**{key: val})
        return qs


def build_viewset(model):
    name = model.__name__
    _ser = serializer_for(model)

    class V(SicopViewSet):
        queryset = model.objects.all()
        serializer_class = _ser

        def get_queryset(self):
            qs = super().get_queryset()
            sf = SEARCH_FIELDS.get(name, [])
            search = self.request.query_params.get("search")
            if search and sf:
                from django.db.models import Q

                q = Q()
                for f in sf:
                    q |= Q(**{f + "__icontains": search})
                qs = qs.filter(q)
            return qs

    V.__name__ = name + "ViewSet"
    return V


class _AggListView(viewsets.ViewSet):
    """ViewSet de agregados: queryset_agg devuelve lista de dicts paginada.

    Content negotiation: JSON para clientes API (Accept: application/json),
    HTML con el diseno del Atlas para el navegador (Accept: text/html).
    """

    renderer_classes = [JSONRenderer, TemplateHTMLRenderer]
    template_name = "atlas/api.html"

    def list(self, request):
        rows = self.queryset_agg(request)
        page = self.paginate_queryset(rows) if hasattr(self, "paginate_queryset") else rows
        resp = self.get_paginated_response(page) if page is not None else Response(rows)
        if getattr(request, "accepted_renderer", None) and request.accepted_renderer.format == "html":
            resp.template_name = self.template_name
        return resp

    def paginate_queryset(self, rows):
        return self.paginator.paginate_queryset(rows, self.request, view=self)

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            self._paginator = LimitOffsetPagination()
        return self._paginator

    def get_paginated_response(self, data):
        paginator = self.paginator
        return Response({
            "count": paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": data,
        })


class ProveedoresViewSet(_AggListView):
    def queryset_agg(self, request):
        qs = m.SicopAdjudicaciones.objects.all()
        ced = request.query_params.get("cedula")
        nombre = request.query_params.get("search")
        anio = request.query_params.get("anio")
        if ced:
            qs = qs.filter(CEDULA_PROVEEDOR=ced)
        if anio:
            qs = qs.filter(ANO=anio)
        if nombre:
            qs = qs.filter(NOMBRE_PROVEEDOR__icontains=nombre)
        rows = list(
            qs.values("CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR")
            .annotate(
                n_lineas=Count("id"),
                monto_crc=Sum("MONTO_ADJU_LINEA_CRC"),
                instituciones=Count("CEDULA", distinct=True),
                anios=Count("ANO", distinct=True),
                procedimientos=Count("NRO_SICOP", distinct=True),
            )
            .order_by("-monto_crc")
        )
        return rows


class InstitucionesViewSet(_AggListView):
    def queryset_agg(self, request):
        qs = m.SicopAdjudicaciones.objects.all()
        ced = request.query_params.get("cedula")
        if ced:
            qs = qs.filter(CEDULA=ced)
        rows = list(
            qs.values("CEDULA", "INSTITUCION")
            .annotate(
                n_lineas=Count("id"),
                monto_crc=Sum("MONTO_ADJU_LINEA_CRC"),
                proveedores=Count("CEDULA_PROVEEDOR", distinct=True),
                anios=Count("ANO", distinct=True),
            )
            .order_by("-monto_crc")
        )
        return rows


class ResumenViewSet(_AggListView):
    """Conteo de filas por tabla + estado de carga (cacheado ~6h: los datos solo
    cambian en el ciclo diario)."""

    def queryset_agg(self, request):
        from django.core.cache import cache

        clave = "sicop:resumen:api:v1"
        try:
            cached = cache.get(clave)
            if cached:
                return cached
        except Exception:  # noqa: BLE001  (Redis caido -> computar sin cache)
            cached = None
        rows = []
        for model, _ in MODEL_TABLES:
            name = model.__name__
            try:
                rows.append({"tabla": model._meta.db_table, "modelo": name, "filas": model.objects.count()})
            except Exception:  # noqa: BLE001
                rows.append({"tabla": model._meta.db_table, "modelo": name, "filas": None})
        try:
            cache.set(clave, rows, 6 * 3600)
        except Exception:  # noqa: BLE001
            pass
        return rows


class EstadoCargaViewSet(_AggListView):
    def queryset_agg(self, request):
        return list(m.LoadState.objects.all().values("table_name", "file_path", "rows_loaded", "coerced_cells", "loaded_at"))


class CaraACaraViewSet(_AggListView):
    def queryset_agg(self, request):
        from sicop import queries

        a = request.query_params.get("cedula_a")
        b = request.query_params.get("cedula_b")
        if not a or not b:
            return [{"error": "cedula_a y cedula_b son obligatorias"}]
        return [queries.cara_a_cara(a, b, request.query_params.get("familia_unspsc") or None)]


class ProductoHistoriaViewSet(_AggListView):
    def queryset_agg(self, request):
        from sicop import queries

        cod = request.query_params.get("codigo_cl")
        if not cod:
            return [{"error": "codigo_cl es obligatorio (16 digitos)"}]
        return [queries.producto_historia(cod)]


class BuscarViewSet(_AggListView):
    def queryset_agg(self, request):
        from sicop import queries

        termino = request.query_params.get("termino", request.query_params.get("search", ""))
        if not termino:
            return [{"error": "termino es obligatorio"}]
        return [queries.campo_buscar(termino, int(request.query_params.get("limit", 20)))]


class PerdidasBaratasViewSet(_AggListView):
    def queryset_agg(self, request):
        from sicop import queries

        return [queries.perdidas_baratas(request.query_params.get("cedula", ""),
                                         request.query_params.get("familia_unspsc") or None,
                                         int(request.query_params.get("limit", 200)))]


class RegimenEvaluacionViewSet(_AggListView):
    def queryset_agg(self, request):
        from sicop import queries

        nro = request.query_params.get("nro_sicop")
        if not nro:
            return [{"error": "nro_sicop es obligatorio"}]
        return [queries.regimen_evaluacion(nro)]


class InvitacionesViewSet(_AggListView):
    def queryset_agg(self, request):
        from sicop import queries

        nro = request.query_params.get("nro_sicop")
        ced = request.query_params.get("cedula")
        if nro:
            return [queries.invitaciones_procedimiento(nro, int(request.query_params.get("limit", 500)))]
        if ced:
            return [queries.invitaciones_proveedor(ced, int(request.query_params.get("limit", 200)))]
        return [{"error": "nro_sicop o cedula son obligatorios"}]


class InvitadosVsOfertantesViewSet(_AggListView):
    def queryset_agg(self, request):
        from sicop import queries

        nro = request.query_params.get("nro_sicop")
        if not nro:
            return [{"error": "nro_sicop es obligatorio"}]
        return [queries.invitados_vs_ofertantes(nro)]


class LineasProcedimientoViewSet(_AggListView):
    def queryset_agg(self, request):
        from sicop import queries

        nro = request.query_params.get("nro_sicop")
        if not nro:
            return [{"error": "nro_sicop es obligatorio"}]
        return [queries.lineas_procedimiento(nro)]


class ProveedorDimViewSet(_AggListView):
    def queryset_agg(self, request):
        from sicop import queries

        ced = request.query_params.get("cedula")
        if not ced:
            return [{"error": "cedula es obligatoria"}]
        return [queries.proveedor_dim(ced)]


class OrdenesProveedorViewSet(_AggListView):
    def queryset_agg(self, request):
        from sicop import queries

        ced = request.query_params.get("cedula")
        if not ced:
            return [{"error": "cedula es obligatoria"}]
        return [queries.ordenes_proveedor(ced, request.query_params.get("anio") or None,
                                          int(request.query_params.get("limit", 1000)))]


class RecursosProcedimientoViewSet(_AggListView):
    def queryset_agg(self, request):
        from sicop import queries

        nro = request.query_params.get("nro_sicop")
        if not nro:
            return [{"error": "nro_sicop es obligatorio"}]
        return [queries.recursos_procedimiento(nro)]


@api_view(["GET"])
def api_root(request):
    return Response({"api": "SICOP", "version": "v1", "docs": "Ver /api/v1/<recurso>/"})


@api_view(["POST"])
def registrar_resultado(request):
    """Registra una decision (FASE 2, SCH_RESULTADO). Append-only, contexto obligatorio."""
    from sicop import resultado

    try:
        obj = resultado.registrar_resultado(**request.data)
    except (TypeError, ValueError) as e:
        return Response({"error": str(e)}, status=400)
    return Response({"resultado_id": str(obj.resultado_id), "estado": "PENDIENTE"}, status=201)


@api_view(["GET"])
def politica(request):
    """Pruebas de politica (FASE 3 enforcement). Si alguna falla, la entrega falla."""
    from sicop.enforcement import pruebas_politica

    results = pruebas_politica(f"politica-{request.query_params.get('corrida', 'api')}")
    return Response({
        "resultados": {k: "PASS" if v else "FAIL" for k, v in results.items()},
        "todo_pasa": all(results.values()),
    })


@api_view(["GET"])
def registro(request):
    """Auditoria de respuestas recientes (agente, herramienta, params, build, conteo)."""
    from sicop.models import RegistroRespuesta

    rows = list(RegistroRespuesta.objects.order_by("-timestamp").values(
        "timestamp", "agente", "herramienta", "build_id", "conteo", "carril",
        "duracion_ms", "status")[: int(request.query_params.get("limit", 100))])
    return Response({"registro": rows})


@api_view(["GET"])
def carril(request):
    """Carril actual: operacion (canonico) o laboratorio (NO_APTO_PARA_DECISION)."""
    import os

    c = os.environ.get("SICOP_CARRIL", "operacion")
    return Response({"carril": c, "decision_eligible": c == "operacion"})


@api_view(["GET"])
def prueba_fase4(request):
    """FASE 4: ficha ESOSA (prueba del plan), backtest y holdout."""
    from sicop.fase4 import ficha_esosa, backtest_invitaciones, holdout

    solo = request.query_params.get("solo", "")
    res = {}
    if solo in ("", "ficha"):
        res["ficha_esosa"] = ficha_esosa()
    if solo in ("", "backtest"):
        res["backtest"] = backtest_invitaciones()
    if solo in ("", "holdout"):
        res["holdout"] = holdout()
    return Response(res)


@api_view(["GET"])
def pendientes_api(request):
    """Pendientes P1-P7 resueltos."""
    from sicop.pendientes import PENDIENTES, run

    solo = request.query_params.get("solo", "")
    names = [n.strip() for n in solo.split(",") if n.strip()] if solo else None
    return Response(run(names))


@api_view(["GET"])
def cgr_buscar(request):
    """Buscador CGR: PDFs de resoluciones (uso dirigido, no barrido)."""
    from sicop.cgr import buscar

    termino = request.query_params.get("termino", request.query_params.get("q", ""))
    if not termino:
        return Response({"error": "termino es obligatorio"}, status=400)
    page = int(request.query_params.get("page", 1))
    return Response(buscar(termino, page))


@api_view(["GET"])
def bccr_tc(request):
    """Tipo de cambio CRC/USD: BCCR oficial (si token) o implicito de la fuente."""
    from datetime import date
    from sicop.bccr import tipo_cambio

    fecha = request.query_params.get("fecha") or date.today().isoformat()
    try:
        from datetime import date as _d
        fecha_d = _d.fromisoformat(fecha)
    except ValueError:
        return Response({"error": "fecha invalida (YYYY-MM-DD)"}, status=400)
    return Response(tipo_cambio(fecha_d))
