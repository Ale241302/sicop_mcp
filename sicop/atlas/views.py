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


def _fmtn(n):
    """Formatea un entero con separador de miles (punto)."""
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


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

    tests = list(CtlTest.objects.order_by("-id")[:8])
    corridas = list(CtlCorrida.objects.order_by("-INICIADO_EN")[:6])
    senales = list(Senal.objects.order_by("-fecha")[:8])
    fails = sum(1 for t in tests if t.RESULTADO == "FAIL")
    ultima_estado = corridas[0].ESTADO if corridas else None
    sano = fails == 0 and ultima_estado in ("PUBLICADO", "OK")

    ctx = {
        "titulo": "Atlas SICOP",
        "resumen": {k: _fmtn(v) for k, v in resumen.items()},
        "sano": sano,
        "fails": fails,
        "ultima_estado": ultima_estado,
        "ultima_corrida": corridas[0].CORRIDA_ID if corridas else "—",
        "tests": tests,
        "corridas": corridas,
        "senales": senales,
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


def _bronze_count():
    """Conteo de bronze rapido y robusto: cache 6h; si expiro, usa reltuples de
    pg_class (instantaneo, aproximado) y dispara el conteo exacto en background.
    Evita bloquear la pagina con un count(*) de ~16s sobre 90M filas."""
    from django.core.cache import cache

    try:
        c = cache.get("sicop:bronze:count")
        if c is not None:
            return c
    except Exception:  # noqa: BLE001
        pass
    try:
        from django.db import connection

        with connection.cursor() as cur:
            cur.execute(
                "SELECT c.reltuples::bigint FROM pg_class c WHERE c.relname='bronze_fila'")
            approx = cur.fetchone()[0]
    except Exception:  # noqa: BLE001
        approx = None
    try:
        import threading

        threading.Thread(target=_warm_bronze_count, daemon=True).start()
    except Exception:  # noqa: BLE001
        pass
    return approx


def _warm_bronze_count():
    """Conteo EXACTO de bronze en background, para poblar el cache sin bloquear."""
    from django.core.cache import cache

    from sicop.models import BronzeFila

    try:
        cache.set("sicop:bronze:count", BronzeFila.objects.count(), 6 * 3600)
    except Exception:  # noqa: BLE001
        pass


def calidad(request):
    from sicop.models import (CtlDeriva, CtlTest, CtlCorrida, CatalogoCampo,
                              VigilanciaCheck, CorridaPaso)

    tests = list(CtlTest.objects.order_by("-id")[:50])
    corridas = list(CtlCorrida.objects.order_by("-INICIADO_EN")[:20])
    pasos = list(CorridaPaso.objects.order_by("-id")[:60])
    fails = sum(1 for t in tests if t.RESULTADO == "FAIL")
    n_pass = len(tests) - fails
    n_pub = sum(1 for c in corridas if c.ESTADO == "PUBLICADO")
    n_bloq = sum(1 for c in corridas if c.ESTADO == "BLOQUEADO")
    n_colg = sum(1 for c in corridas if c.ESTADO == "EN_CURSO")
    if fails or n_bloq or n_colg:
        veredicto, vcls = "Requiere atencion", "r"
    else:
        veredicto, vcls = "Saludable", "g"

    ctx = {
        "deriva": list(CtlDeriva.objects.order_by("CONJUNTO", "ANIO", "CAMPO")[:300]),
        "tests": tests,
        "corridas": corridas,
        "campos": list(CatalogoCampo.objects.exclude(TRAMPA__isnull=True)[:40]),
        "vigilancia": list(VigilanciaCheck.objects.order_by("-fecha")[:20]),
        "pasos": pasos,
        "bronze": _bronze_count(),
        "veredicto": veredicto, "vcls": vcls,
        "n_pass": n_pass, "n_fail": fails,
        "n_pub": n_pub, "n_bloq": n_bloq, "n_colg": n_colg,
    }
    return render(request, "atlas/calidad.html", ctx)


def _warm_bench(clave):
    """Benchmark de TODAS las tools (solo lectura). Se corre en background y
    llena la cache de Redis. Excluye tools que mutan el sistema, consultan
    servicios externos o son experimentos de Fase 4."""
    try:
        from concurrent.futures import ThreadPoolExecutor

        import asyncio
        import time
        from django.core.cache import cache

        from sicop.mcp_server import mcp

        BENCH_SKIP = {
            "sicop_reparar_mes", "sicop_ciclo_diario", "sicop_registrar_resultado",
            "sicop_cgr_buscar", "sicop_backtest_invitaciones", "sicop_holdout",
            "sicop_ficha_esosa", "sicop_reconciliar",
        }
        BENCH_ARGS = {
            "sicop_ficha_proveedor": {"cedula": "3101029593"},
            "sicop_mercado_familia": {"familia_unspsc": "81112399"},
            "sicop_cara_a_cara": {"cedula_a": "3101086562", "cedula_b": "3101095926"},
            "sicop_perdidas_baratas": {"cedula": "3101095926"},
            "sicop_precios_institucion": {"familia_unspsc": "461816"},
            "sicop_precios_identicos": {"nro_sicop": "20230802921"},
            "sicop_excepciones": {"cedula": "3101086562"},
            "sicop_sanciones": {"cedula": "3101095926"},
            "sicop_proveedor_dim": {"cedula": "3101029593"},
            "sicop_ordenes_proveedor": {"cedula": "3101095926", "anio": "2025", "limit": 10},
            "sicop_campo_buscar": {"termino": "UPS"},
            "sicop_producto": {"codigo_cl": "5311160192296606"},
            "sicop_producto_historia": {"codigo_cl": "5311160192296606"},
            "sicop_producto_firma": {"codigo_cl": "5311160192296606"},
            "sicop_buscar_procedimiento": {"numero_procedimiento": "2023LE-000016-0000200001"},
            "sicop_verificar_procedimiento": {"nro_sicop": "20230802921"},
            "sicop_competencia_procedimiento": {"nro_sicop": "20230802921"},
            "sicop_expediente": {"nro_sicop": "20230802921"},
            "sicop_lineas_procedimiento": {"nro_sicop": "20230802921"},
            "sicop_regimen_evaluacion": {"nro_sicop": "20251200067"},
            "sicop_regimen": {"nro_sicop": "20230802921"},
            "sicop_tiempos_por_etapa": {"nro_sicop": "20230802921"},
            "sicop_recursos_procedimiento": {"nro_sicop": "20230802921"},
            "sicop_recursos_desenlace": {"nro_sicop": "20230802921"},
            "sicop_invitaciones_procedimiento": {"nro_sicop": "20230802921"},
            "sicop_invitaciones_proveedor": {"cedula": "3101095926"},
            "sicop_invitados_vs_ofertantes": {"nro_sicop": "20230802921"},
            "sicop_carteles_objetados": {},
            "sicop_fact_requerimiento": {"nro_sicop": "20230802921"},
            "sicop_fact_oferta": {"nro_sicop": "20230802921"},
            "sicop_fact_adjudicacion": {"nro_sicop": "20230802921"},
            "sicop_fact_contrato": {"nro_sicop": "20230802921"},
            "sicop_fact_orden": {"nro_sicop": "20230802921", "limit": 5},
            "sicop_fact_recepcion": {"nro_sicop": "20230802921"},
            "sicop_mes_publicacion": {"nro_sicop": "20230802921"},
            "sicop_ctl_deriva": {"conjunto": "adjudicaciones"},
            "sicop_catalogo_campo": {"tabla": "carteles"},
            "sicop_competencia_por_regimen": {},
            "sicop_bccr_tc": {},
            "sicop_diagnostico": {},
            "sicop_resumen": {},
            "sicop_gold_status": {},
            "sicop_corrida_pasos": {},
            "sicop_politica": {},
            "sicop_carril": {},
            "sicop_senales": {},
            "sicop_resultado": {},
            "sicop_actividad_mcp": {},
            "sicop_registro": {},
            "sicop_vigilancia": {},
            "sicop_representantes": {},
            "sicop_representante_competencia": {},
        }

        def _bm(name, args):
            try:
                t0 = time.time()
                asyncio.run(mcp.call_tool(name, args))
                return name, int((time.time() - t0) * 1000)
            except Exception:  # noqa: BLE001
                return name, None

        todos = [(t.name, BENCH_ARGS.get(t.name, {}))
                 for t in mcp._tool_manager.list_tools() if t.name not in BENCH_SKIP]
        bench = {}
        with ThreadPoolExecutor(max_workers=10) as ex:
            for name, ms in ex.map(lambda p: _bm(*p), todos):
                bench[name] = ms
        bench = {k: v for k, v in sorted(bench.items(), key=lambda kv: (kv[1] is None, kv[1] or 0))}
        cache.set(clave, bench, 6 * 3600)
    except Exception:  # noqa: BLE001
        pass


def _actividad_mcp(dedup=True):
    """Actividad reciente del MCP: llamadas deduplicadas + resumen (quien pidio que y cuanto tardo)."""
    from datetime import timedelta

    from django.utils import timezone

    from sicop.models import RegistroRespuesta

    desde = timezone.now() - timedelta(hours=24)
    rows = list(RegistroRespuesta.objects.filter(timestamp__gte=desde).order_by("-id")[:500])

    def clave(r):
        # dedupe de registros duplicados historicos (misma tool+params+mismo segundo)
        ts = (r.timestamp or desde).strftime("%Y%m%d%H%M%S")
        return (r.herramienta, (r.parametros or "")[:120], ts)

    if dedup:
        vistos, unicos = set(), []
        for r in rows:
            k = clave(r)
            if k not in vistos:
                vistos.add(k)
                unicos.append(r)
        rows = unicos

    por_herramienta = {}
    for r in rows:
        h = r.herramienta or "?"
        por_herramienta[h] = por_herramienta.get(h, 0) + 1
    por_herramienta = sorted(por_herramienta.items(), key=lambda kv: -kv[1])

    ultimas = []
    n_lentas = 0
    for r in rows[:15]:
        params = (r.parametros or "").replace("\u20a1", "")
        if len(params) > 60:
            params = params[:60] + "…"
        if (r.duracion_ms or 0) >= 3000:
            n_lentas += 1
        ultimas.append({
            "hora": (r.timestamp or desde).strftime("%d/%m %H:%M"),
            "herramienta": r.herramienta,
            "params": params,
            "ms": r.duracion_ms,
            "agente": r.agente,
        })
    # top tools con pct (para barras) y max para escalar
    top = por_herramienta[:10]
    max_n = max((n for _, n in top), default=1)
    top_bars = [{"tool": t, "n": n, "pct": round(n / max_n * 100)} for t, n in top]
    lentas = [u for u in ultimas if (u["ms"] or 0) >= 3000]
    return {
        "total": len(rows),
        "por_herramienta": por_herramienta,
        "tools_distintas": len(por_herramienta),
        "top": top_bars,
        "n_lentas": n_lentas,
        "ultimas": ultimas,
        "lentas": lentas,
    }


def mcp_docs(request):
    """Documentacion del servidor MCP: como conectarse, tools, ejemplos y tiempos."""
    from django.core.cache import cache
    from sicop.mcp_server import mcp

    from sicop.atlas.tool_docs import CATEGORIAS as DOC_CAT, DOCS as TOOL_DOCS

    tools = []
    for t in mcp._tool_manager.list_tools():
        props = (t.parameters or {}).get("properties", {})
        required = set((t.parameters or {}).get("required", []) or [])
        params = ", ".join(
            f"{k}{'*' if k in required else ''}" for k in props.keys()
        )
        tools.append({"name": t.name, "desc": t.description or "", "params": params,
                      "doc": TOOL_DOCS.get(t.name)})

    by_name = {t["name"]: t for t in tools}
    grouped = []
    for cat, names in DOC_CAT:
        items = [by_name[n] for n in names if n in by_name]
        if items:
            grouped.append({"categoria": cat, "tools": items})
    # tools sin documentar (por si agregan una nueva) van al final
    documentados = {n for _, ns in DOC_CAT for n in ns}
    sueltos = [t for t in tools if t["name"] not in documentados]
    if sueltos:
        grouped.append({"categoria": "Otras", "tools": sueltos})

    clave = "sicop:mcp:bench:v2"
    try:
        bench = cache.get(clave)
    except Exception:  # noqa: BLE001
        bench = None
    if bench is None:
        # no bloquear la pagina: disparar el computo en background y devolver
        # esta vez con una nota. El benchmark se calienta aparte.
        bench = {}
        try:
            import threading

            threading.Thread(target=_warm_bench, args=(clave,), daemon=True).start()
        except Exception:  # noqa: BLE001
            pass
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

    # estadisticas del benchmark para la visualizacion (KPIs + barras)
    import statistics

    bv = [v for v in bench.values() if v is not None]
    bench_stats = {
        "total": len(bench),
        "mediana": int(statistics.median(bv)) if bv else None,
        "lenta": max(bench.items(), key=lambda kv: kv[1] or 0),
        "rapida": min(bench.items(), key=lambda kv: kv[1] if kv[1] is not None else 10**12),
        "lentas_2s": sum(1 for v in bv if v >= 2000),
    }
    bmax = max(bv) if bv else 1
    bench_bars = []
    for t, ms in sorted(bench.items(), key=lambda kv: (kv[1] is None, kv[1] or 0)):
        m = ms or 0
        pct = round((m / bmax) ** 0.5 * 100) if bmax else 0  # escala raiz: legible
        cls = "fast" if m < 300 else ("med" if m < 2000 else "slow")
        bench_bars.append((t, m, pct, cls))

    return render(request, "atlas/mcp.html", {
        "tools": tools, "bench": bench, "ejemplos": ejemplos_uso,
        "total_tools": len(tools), "titulo": "Documentación MCP",
        "actividad": _actividad_mcp(),
        "grupos": grouped,
        "bench_stats": bench_stats, "bench_bars": bench_bars,
    })


def favicon(request):
    """Sirve el favicon del Atlas (SVG). Tambien responde en /favicon.ico."""
    from django.http import HttpResponse
    import os

    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favicon.svg")
    try:
        with open(p, "rb") as f:
            svg = f.read()
    except OSError:
        return HttpResponse(status=404)
    return HttpResponse(svg, content_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=86400"})


def mercado(request, familia):
    m = queries.mercado_familia(familia)
    return render(request, "atlas/mercado.html", {"familia": familia, "m": m, "fmt": _fmt, "titulo": f"Familia {familia}"})


def proveedores(request):
    from django.db.models import Count, F, Sum

    from sicop.models import FactAdjudicacion, SicopProveedores

    # solo cedulas validas (excluye NULL y vacias); agrupa por cedula (no por
    # (cedula,nombre): el nombre varia por spelling y parte el ranking).
    # ORDER BY m DESC con nulls_last: los montos NULL (cedulas malformadas o
    # adjudicaciones sin monto) NO contaminan el ranking.
    top = list(
        FactAdjudicacion.objects
        .exclude(CEDULA_PROVEEDOR__isnull=True).exclude(CEDULA_PROVEEDOR="")
        .values("CEDULA_PROVEEDOR")
        .annotate(m=Sum("MONTO_ADJUDICADO_CRC"), n=Count("id"))
        .order_by(F("m").desc(nulls_last=True))[:50]
    )
    # resolver nombre desde el dim (proveedores) cuando la adjudicacion no lo trae
    ceds = [r["CEDULA_PROVEEDOR"] for r in top]
    names = dict(
        SicopProveedores.objects.filter(CEDULA_PROVEEDOR__in=ceds)
        .values_list("CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR")
    )
    for r in top:
        r["NOMBRE_PROVEEDOR"] = r.get("NOMBRE_PROVEEDOR") or names.get(r["CEDULA_PROVEEDOR"])
    return render(request, "atlas/proveedores.html", {"top": top, "fmt": _fmt, "titulo": "Proveedores"})
