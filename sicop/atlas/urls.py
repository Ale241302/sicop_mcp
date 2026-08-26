from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="atlas"),
    path("buscar/", views.buscar, name="atlas-buscar"),
    path("proveedores/", views.proveedores, name="atlas-proveedores"),
    path("proveedor/<str:cedula>/", views.proveedor, name="atlas-proveedor"),
    path("producto/<str:codigo>/", views.producto, name="atlas-producto"),
    path("procedimiento/<str:nro>/", views.procedimiento, name="atlas-procedimiento"),
    path("mercado/<str:familia>/", views.mercado, name="atlas-mercado"),
    path("calidad/", views.calidad, name="atlas-calidad"),
]
