from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (MODEL_TABLES, build_viewset, ProveedoresViewSet, InstitucionesViewSet, ResumenViewSet,
                    EstadoCargaViewSet, CaraACaraViewSet, ProductoHistoriaViewSet, BuscarViewSet,
                    PerdidasBaratasViewSet, RegimenEvaluacionViewSet, InvitacionesViewSet,
                    InvitadosVsOfertantesViewSet, LineasProcedimientoViewSet, ProveedorDimViewSet,
                    OrdenesProveedorViewSet, RecursosProcedimientoViewSet, registrar_resultado,
                    politica, registro, carril, prueba_fase4, pendientes_api, cgr_buscar, bccr_tc)
from django.urls import re_path

router = DefaultRouter()
for model, route in MODEL_TABLES:
    router.register(route, build_viewset(model), basename=route)
router.register("proveedores", ProveedoresViewSet, basename="proveedores")
router.register("instituciones-agg", InstitucionesViewSet, basename="instituciones-agg")
router.register("resumen", ResumenViewSet, basename="resumen")
router.register("estado-carga", EstadoCargaViewSet, basename="estado-carga")
router.register("cara-a-cara", CaraACaraViewSet, basename="cara-a-cara")
router.register("producto-historia", ProductoHistoriaViewSet, basename="producto-historia")
router.register("buscar", BuscarViewSet, basename="buscar")
router.register("perdidas-baratas", PerdidasBaratasViewSet, basename="perdidas-baratas")
router.register("regimen-evaluacion", RegimenEvaluacionViewSet, basename="regimen-evaluacion")
router.register("invitaciones", InvitacionesViewSet, basename="invitaciones")
router.register("invitados-vs-ofertantes", InvitadosVsOfertantesViewSet, basename="invitados-vs-ofertantes")
router.register("lineas-procedimiento", LineasProcedimientoViewSet, basename="lineas-procedimiento")
router.register("proveedor-dim", ProveedorDimViewSet, basename="proveedor-dim")
router.register("ordenes-proveedor", OrdenesProveedorViewSet, basename="ordenes-proveedor")
router.register("recursos-procedimiento", RecursosProcedimientoViewSet, basename="recursos-procedimiento")

urlpatterns = [
    path("", include(router.urls)),
    re_path(r"^resultado-registrar/$", registrar_resultado),
    re_path(r"^politica/$", politica),
    re_path(r"^registro/$", registro),
    re_path(r"^carril/$", carril),
    re_path(r"^prueba-fase4/$", prueba_fase4),
    re_path(r"^pendientes/$", pendientes_api),
    re_path(r"^cgr/$", cgr_buscar),
    re_path(r"^bccr-tc/$", bccr_tc),
]
