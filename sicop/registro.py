"""FASE 3: registro de respuestas (agente, herramienta, params, build_id, conteo, calidad)."""
import json
import logging
import time

from django.utils import timezone

from .models import RegistroRespuesta

logger = logging.getLogger(__name__)


def registrar(herramienta, parametros=None, agente=None, build_id=None, conteo=None,
              calidad=None, carril="operacion", corrida=None, duracion_ms=None, status="OK"):
    """Registra una respuesta de agente->herramienta (auditoria FASE 3)."""
    try:
        RegistroRespuesta.objects.create(
            timestamp=timezone.now(), agente=agente or "desconocido", herramienta=herramienta,
            parametros=json.dumps(parametros or {}, ensure_ascii=False)[:2000],
            build_id=build_id, conteo=conteo, calidad=calidad, carril=carril,
            corrida=corrida, duracion_ms=duracion_ms, status=str(status)[:50],
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("no se pudo registrar respuesta: %s", e)


def _etiquetar_laboratorio(result, name):
    """En carril laboratorio: marca la respuesta NO_APTO_PARA_DECISIÓN."""
    import json

    try:
        if not getattr(result, "content", None):
            return result
        txt = result.content[0].text
        data = json.loads(txt)
        data = {
            "etiqueta": "NO_APTO_PARA_DECISION",
            "decision_eligible": False,
            "carril": "laboratorio",
            "herramienta": name,
            "datos": data,
        }
        result.content[0].text = json.dumps(data, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass
    return result


def wrap_mcp_call_tool(mcp):
    """Envuelve el despacho real (tool_manager) para registrar cada llamada y etiquetar laboratorio."""
    if getattr(mcp, "_sicop_logged", False):
        return
    mcp._sicop_logged = True

    def _wrap(target):
        import functools

        orig = target

        async def _logged(name, arguments, context=None, **kw):
            import os

            t0 = time.time()
            carril = os.environ.get("SICOP_CARRIL", "operacion")
            conteo = None
            try:
                result = await orig(name, arguments, context=context, **kw) if context is not None else await orig(name, arguments, **kw)
                status = "OK"
                try:
                    import json as _json

                    txt = getattr(result, "content", None)
                    txt = txt[0].text if txt else ""
                    data = _json.loads(txt)
                    if isinstance(data, dict) and "resultados" in data:
                        conteo = len(data["resultados"])
                    elif isinstance(data, dict) and "total" in data:
                        conteo = data["total"]
                    elif isinstance(data, dict) and "datos" in data and isinstance(data["datos"], list):
                        conteo = len(data["datos"])
                except Exception:  # noqa: BLE001
                    pass
                if carril == "laboratorio" and name not in ("sicop_lab_sql",):
                    result = _etiquetar_laboratorio(result, name)
                return result
            except Exception as e:  # noqa: BLE001
                status = f"ERROR: {type(e).__name__}"
                raise
            finally:
                import asyncio

                await asyncio.to_thread(
                    registrar,
                    herramienta=name, parametros=arguments,
                    agente=os.environ.get("SICOP_AGENTE", "mcp"),
                    build_id=os.environ.get("SICOP_BUILD_ID"),
                    conteo=conteo, carril=carril,
                    duracion_ms=int((time.time() - t0) * 1000), status=status,
                )

        return _logged

    tm = getattr(mcp, "_tool_manager", None)
    if tm is not None and hasattr(tm, "call_tool"):
        tm.call_tool = _wrap(tm.call_tool)
    # tambien la llamada programatica (si algun cliente la usa)
    if hasattr(mcp, "call_tool"):
        mcp.call_tool = _wrap(mcp.call_tool)
