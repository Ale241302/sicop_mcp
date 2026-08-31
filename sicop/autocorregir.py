"""Autocorrecion del ciclo diario (FASE: cron autocurable).

Detecta FAIL de tests, corridas BLOQUEADO y EN_CURSO colgadas (>30 min) y las
corrige dejando log en corrida_paso / ctl_corrida.

Reglas:
- EN_CURSO colgadas -> se cierran como FALLIDA con motivo (nunca quedan
  "para siempre en curso").
- FAIL / BLOQUEADO recientes -> se re-corre silver+gold+tests UNA vez
  (boundado por Redis 6h para no entrar en loop). Si pasa, la corrida nueva
  queda PUBLICADO y los problemas previos se marcan como autocorregidos.
  Si sigue fallando, queda BLOQUEADO con motivo y se pide intervencion.
- Toda accion se devuelve como lista para registrarla en corrida_paso.
"""
import time
from datetime import timedelta

from django.utils import timezone

COLGADA_MIN = 30
VENTANA_PROBLEMAS = 48  # horas: solo se autocorrigen problemas recientes


def detectar():
    """Problemas actuales (ventana de 48h): fails, bloqueados, colgadas."""
    from .models import CtlCorrida, CtlTest

    desde = timezone.now() - timedelta(hours=VENTANA_PROBLEMAS)
    recientes = set(
        CtlCorrida.objects.filter(INICIADO_EN__gte=desde)
        .values_list("CORRIDA_ID", flat=True)
    )
    fails = list(
        CtlTest.objects.filter(RESULTADO="FAIL")
        .exclude(CORRIDA_ID__isnull=True)
        .filter(CORRIDA_ID__in=recientes)
        .order_by("-id")[:20]
        .values("CORRIDA_ID", "TEST", "VALOR_OBTENIDO")
    )
    bloqueados = list(
        CtlCorrida.objects.filter(ESTADO="BLOQUEADO", INICIADO_EN__gte=desde)
        .values_list("CORRIDA_ID", flat=True)[:10]
    )
    colgadas = list(
        CtlCorrida.objects.filter(
            ESTADO="EN_CURSO", INICIADO_EN__lt=timezone.now() - timedelta(minutes=COLGADA_MIN)
        ).values_list("CORRIDA_ID", flat=True)
    )
    return {"fails": fails, "bloqueados": bloqueados, "colgadas": colgadas}


def corregir():
    """Intenta corregir los problemas. Devuelve lista de acciones (para el log)."""
    from django.core.cache import cache

    from . import control, silver
    from .derivadas import run as run_derivadas
    from .models import CtlCorrida

    acciones = []

    # 1) cerrar EN_CURSO colgadas (proceso muerto sin cerrar)
    colgadas = detectar()["colgadas"]
    for cid in colgadas:
        CtlCorrida.objects.filter(CORRIDA_ID=cid, ESTADO="EN_CURSO").update(
            ESTADO="FALLIDA", CERRADO_EN=timezone.now(),
            NOTAS=f"auto: corrida colgada >{COLGADA_MIN} min, cerrada por autocorregir")
        acciones.append(f"EN_CURSO {cid} -> FALLIDA (colgada)")

    # 2) FAIL / BLOQUEADO -> re-correr gold+tests UNA vez (boundado)
    p = detectar()
    problemas = len(p["fails"]) + len(p["bloqueados"])
    if not problemas:
        if not acciones:
            acciones.append("sin problemas (0 FAIL, 0 BLOQUEADO, 0 colgadas)")
        return acciones

    lock = None
    try:
        lock = cache.get("sicop:autocorregir:ultimo")
    except Exception:  # noqa: BLE001  (Redis caido -> correr igual una vez)
        pass
    if lock:
        try:
            ultimo = timezone.datetime.fromisoformat(lock)
            if (timezone.now() - ultimo) < timedelta(hours=6):
                acciones.append(
                    f"{len(p['fails'])} FAIL / {len(p['bloqueados'])} BLOQUEADO persisten; "
                    "ultimo intento <6h -> requiere intervencion")
                return acciones
        except Exception:  # noqa: BLE001
            pass
    try:
        cache.set("sicop:autocorregir:ultimo", timezone.now().isoformat(), 6 * 3600)
    except Exception:  # noqa: BLE001
        pass

    corrida = f"auto-{timezone.now().strftime('%Y%m%d-%H%M%S')}"
    control.registrar_corrida(corrida, "autocorregir",
                              notas=f"re-correccion por {len(p['fails'])} FAIL / {len(p['bloqueados'])} BLOQUEADO")
    t0 = time.time()
    try:
        silver.build_all(corrida)
        run_derivadas(None)
        ok, failed = control.run_tests(corrida)
    except Exception as e:  # noqa: BLE001
        control.cerrar_corrida(corrida, "BLOQUEADO",
                               notas=f"autocorregir fallo en pipeline: {type(e).__name__}: {str(e)[:120]}")
        acciones.append(f"autocorregir {corrida}: ERROR {type(e).__name__} (queda BLOQUEADO)")
        return acciones
    ms = int((time.time() - t0) * 1000)

    if not failed:
        control.cerrar_corrida(corrida, "PUBLICADO",
                               notas=f"autocorregido: {len(ok)} PASS / 0 FAIL ({ms}ms)")
        for cid in p["bloqueados"]:
            CtlCorrida.objects.filter(CORRIDA_ID=cid).update(
                NOTAS=f"autocorregido por {corrida} (PASS); el FAIL original queda en el log")
        acciones.append(f"corregido: {corrida} PUBLICADO ({len(ok)} PASS / 0 FAIL); "
                        f"{len(p['bloqueados'])} BLOQUEADO + {len(p['fails'])} FAIL resueltos")
    else:
        control.cerrar_corrida(corrida, "BLOQUEADO",
                               notas=f"no se pudo autocorregir: {len(failed)} FAIL ({ms}ms)")
        acciones.append(f"no se pudo autocorregir: {corrida} BLOQUEADO con {len(failed)} FAIL; requiere intervencion")
    return acciones
