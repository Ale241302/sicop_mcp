"""URL configuration for sicop_mcp."""
from django.contrib import admin
from django.urls import include, path

from sicop.api.views import api_root

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("sicop.api.urls")),
    path("api/v1/", api_root),
    path("atlas/", include("sicop.atlas.urls")),
]
