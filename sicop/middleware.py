"""Middlewares FASE 3: enforcement fisico + registro de respuestas (API)."""
import time

from django.http import JsonResponse

from .enforcement import detectar_acceso_crudo


class EnforcementMiddleware:
    """Bloquea requests que intentan tocar la capa cruda (CSV, rutas, secretos)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        razon = detectar_acceso_crudo(request.path, request.GET)
        if razon:
            return JsonResponse({"error": "acceso a capa cruda bloqueado", "razon": razon}, status=403)
        return self.get_response(request)


class RegistroMiddleware:
    """Registra cada respuesta de la API (agente, herramienta, params, build, conteo)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .registro import registrar

        t0 = time.time()
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            conteo = None
            try:
                import json

                if response.get("Content-Type", "").startswith("application/json"):
                    body = json.loads(response.content.decode("utf-8", "replace"))
                    if isinstance(body, dict):
                        conteo = body.get("count")
            except Exception:  # noqa: BLE001
                pass
            registrar(
                herramienta=request.path, parametros=dict(request.GET),
                agente=request.META.get("HTTP_USER_AGENT", "api")[:100],
                build_id=request.META.get("HTTP_X_BUILD_ID"),
                conteo=conteo, carril="operacion",
                duracion_ms=int((time.time() - t0) * 1000), status=response.status_code,
            )
        return response
