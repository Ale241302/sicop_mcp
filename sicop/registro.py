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


def _enriquecer_con_labels(text):
    """Agrega labels humanos a las respuestas: NRO_SICOP -> NRO_PROCEDIMIENTO +
    INSTITUCION + PROCEDIMIENTO_LABEL, y CEDULA_PROVEEDOR -> NOMBRE_PROVEEDOR.
    Se aplica a TODAS las respuestas del MCP (chokepoint _logged) para que el
    chat de la IA no muestre codigos crudos de la base."""
    import json as _json

    try:
        data = _json.loads(text)
    except Exception:  # noqa: BLE001
        return text
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

    _walk(data)
    if not rows:
        return text
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
    return _json.dumps(data, ensure_ascii=False)


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
                # labels humanos (NRO_PROCEDIMIENTO / institucion / proveedor)
                try:
                    txt = getattr(result, "content", None)
                    if txt and txt[0].text:
                        txt[0].text = _enriquecer_con_labels(txt[0].text)
                except Exception:  # noqa: BLE001
                    pass
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
    # SOLO el despacho interno (tm.call_tool): el mcp.call_tool publico lo invoca
    # por dentro, asi que envolver ambos duplicaba cada registro. Con uno basta.
    if tm is not None and hasattr(tm, "call_tool"):
        tm.call_tool = _wrap(tm.call_tool)
