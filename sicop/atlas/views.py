"""PLAN_ATLAS — app de navegacion del corpus (Django + plantillas).

Decisiones del plan:
- Ninguna cifra viaja sola: cada numero se muestra con su sobre (nivel_medicion, cobertura, moneda, caveats).
- Las trampas se bloquean, no se documentan: la UI deshabilita comparaciones peligrosas (monedas, anios sin CL).
- La pantalla de calidad del dato entra primero.
- La app le pone cara al harness (senales y tests visibles).
"""
from django.db.models import Count, Sum
from django.shortcuts import render
from django.http import Http404

from sicop import queries


def _fmt(n):
    if n is None:
        return "—"
    try:
        return f"\u20a1{n:,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def index(request):
    from django.core.cache import cache

    from sicop.models import (CtlTest, CtlDeriva, Senal, CtlCorrida, FactAdjudicacion,
                              FactOrden, FactOferta, SicopInvitaciones)

    clave = "sicop:atlas:resumen:v1"
    try:
        resumen = cache.get(clave)
    except Exception:  # noqa: BLE001  (Redis caido -> computar sin cache)
        resumen = None
    if resumen is None:
        resumen = {
            "adjudicaciones": FactAdjudicacion.objects.count(),
            "ofertas": FactOferta.objects.count(),
            "ordenes": FactOrden.objects.count(),
            "invitaciones": SicopInvitaciones.objects.count(),
        }
        try:
            cache.set(clave, resumen, 6 * 3600)
        except Exception:  # noqa: BLE001
            pass

    ctx = {
        "titulo": "Atlas SICOP",
        "resumen": resumen,
        "tests": list(CtlTest.objects.order_by("-id")[:8]),
        "corridas": list(CtlCorrida.objects.order_by("-INICIADO_EN")[:6]),
        "senales": list(Senal.objects.order_by("-fecha")[:8]),
        "deriva": list(CtlDeriva.objects.filter(LLENADO_PCT__lt=95).values("CONJUNTO", "CAMPO", "ANIO", "LLENADO_PCT").order_by("LLENADO_PCT")[:12]),
        "sobre": queries.sobre("mixto", queries.COBERTURA_CRUCE),
    }
    return render(request, "atlas/index.html", ctx)


def buscar(request):
    q = request.GET.get("q", "").strip()
    res = queries.campo_buscar(q, limit=15) if q else None
    return render(request, "atlas/buscar.html", {"q": q, "res": res, "titulo": "Buscar"})


def proveedor(request, cedula):
    f = queries.ficha_proveedor(cedula)
    if not f.get("nombre"):
        raise Http404("Proveedor no encontrado")
    return render(request, "atlas/proveedor.html", {"cedula": cedula, "f": f, "fmt": _fmt, "titulo": f"Proveedor {cedula}"})


def producto(request, codigo):
    from sicop.queries import producto_historia
    ph = producto_historia(codigo)
    if not ph.get("catalogo"):
        raise Http404("Producto no encontrado")
    return render(request, "atlas/producto.html", {"ph": ph, "fmt": _fmt, "titulo": f"Producto {codigo}"})


def procedimiento(request, nro):
    from sicop import queries as q
    adj = q.adjudicaciones(nro_sicop=nro, limit=200)
    comp = q.competencia_procedimiento(nro)
    reg = q.regimen_evaluacion(nro)
    exp = q.expediente(nro)
    inv = q.invitaciones_procedimiento(nro, limit=200)
    rec = q.recursos_procedimiento(nro)
    return render(request, "atlas/procedimiento.html", {
        "nro": nro, "adj": adj, "comp": comp, "reg": reg, "exp": exp,
        "inv": inv, "rec": rec, "fmt": _fmt, "titulo": f"Procedimiento {nro}",
    })


def calidad(request):
    from sicop.models import (CtlDeriva, CtlTest, CtlCorrida, CatalogoCampo,
                              VigilanciaCheck, BronzeFila, CorridaPaso)
    ctx = {
        "deriva": list(CtlDeriva.objects.order_by("CONJUNTO", "ANIO", "CAMPO")[:300]),
        "tests": list(CtlTest.objects.order_by("-id")[:50]),
        "corridas": list(CtlCorrida.objects.order_by("-INICIADO_EN")[:20]),
        "campos": list(CatalogoCampo.objects.exclude(TRAMPA__isnull=True)[:40]),
        "vigilancia": list(VigilanciaCheck.objects.order_by("-fecha")[:20]),
        "pasos": list(CorridaPaso.objects.order_by("-id")[:60]),
        "bronze": BronzeFila.objects.count(),
    }
    return render(request, "atlas/calidad.html", ctx)


def mcp_docs(request):
    """Documentacion del servidor MCP: como conectarse, tools, ejemplos y tiempos."""
    from django.core.cache import cache
    from sicop.mcp_server import mcp

    tools = []
    for t in mcp._tool_manager.list_tools():
        props = (t.parameters or {}).get("properties", {})
        required = set((t.parameters or {}).get("required", []) or [])
        params = ", ".join(
            f"{k}{'*' if k in required else ''}" for k in props.keys()
        )
        tools.append({"name": t.name, "desc": t.description or "", "params": params})

    clave = "sicop:mcp:bench:v1"
    try:
        bench = cache.get(clave)
    except Exception:  # noqa: BLE001
        bench = None
    if bench is None:
        bench = {}
        ejemplos = {
            "sicop_resumen": {},
            "sicop_carril": {},
            "sicop_ficha_proveedor": {"cedula": "3101029593"},
            "sicop_mercado_familia": {"familia_unspsc": "81112399"},
            "sicop_cara_a_cara": {"cedula_a": "3101086562", "cedula_b": "3101095926"},
            "sicop_regimen_evaluacion": {"nro_sicop": "20251200067"},
            "sicop_campo_buscar": {"termino": "UPS"},
        }
        for name, args in ejemplos.items():
            try:
                import asyncio
                import time
                t0 = time.time()
                asyncio.run(mcp.call_tool(name, args))
                bench[name] = int((time.time() - t0) * 1000)
            except Exception as e:  # noqa: BLE001
                bench[name] = None
        try:
            cache.set(clave, bench, 6 * 3600)
        except Exception:  # noqa: BLE001
            pass

    ejemplos_uso = [
        ("Ficha de un proveedor", "¿Ficha de la empresa 3101029593? Captación por año y cartera de ejecución."),
        ("Mercado de una familia", "¿Quiénes ganan en la familia 81112399 (mantenimiento de UPS)? Top adjudicatarios."),
        ("Cara a cara de competidores", "Compará ESOSA (3101086562) contra SONDEL (3101095926): dónde ofertan juntos y quién es más barato."),
        ("Perder siendo más barato", "¿Dónde ofertamos más barato que el ganador y perdimos? (perdidas_baratas)"),
        ("Espacios blancos", "¿Qué procedimientos invitaron a nuestro proveedor y nadie ofertó? (invitados_vs_ofertantes)"),
        ("Régimen de evaluación", "¿Cómo evalúan el procedimiento 20251200067? PRECIO_PURO o MIXTO."),
        ("Tasa de cambio del día", "¿Cuál es el tipo de cambio de hoy? (BCCR oficial)"),
        ("Log del pipeline", "¿Qué pasó en la última corrida del ciclo? (corrida_pasos)"),
    ]

    return render(request, "atlas/mcp.html", {
        "tools": tools, "bench": bench, "ejemplos": ejemplos_uso,
        "total_tools": len(tools), "titulo": "Documentación MCP",
    })


def mercado(request, familia):
    m = queries.mercado_familia(familia)
    return render(request, "atlas/mercado.html", {"familia": familia, "m": m, "fmt": _fmt, "titulo": f"Familia {familia}"})


def proveedores(request):
    from sicop.models import FactAdjudicacion
    top = list(
        FactAdjudicacion.objects.exclude(CEDULA_PROVEEDOR="").values("CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR")
        .annotate(m=Sum("MONTO_ADJUDICADO_CRC"), n=Count("id")).order_by("-m")[:50]
    )
    return render(request, "atlas/proveedores.html", {"top": top, "fmt": _fmt, "titulo": "Proveedores"})
