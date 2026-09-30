"""A2 dentro del gate del ciclo (skill §7 y §10).

La skill deja claro que la mitad de la auditoría (regresión de inventario del
zip, salto de magnitud contra la mediana del propio producto, cobertura del
cruce y el campo `no_evaluados`) vivía en el harness A0-A5, que **no corría en
el cron**: se invocaba a mano. Este módulo la mete al gate reutilizando la
función `a2` del harness tal cual, sin portarla (una segunda implementación es
una segunda fuente de verdad que se desincroniza).

No registra CtlTest por sí mismo: devuelve un veredicto y `control.run_tests`
lo traduce a filas de `ctl_test`. Así se evita el ciclo de imports control<->a2.

Regla que respeta: un chequeo que no pudo correr **no es un chequeo que pasó**.
Si el harness o sus insumos faltan, el veredicto es `NO_EVALUADO`, nunca
`CONFIABLE`.
"""
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_HARNESS = None  # cache del módulo harness_sicop importado
_HARNESS_ERROR = None


def harness_dir():
    from django.conf import settings

    return Path(settings.SICOP_SCRIPTS_DIR) / "harness_actualizado"


def data_dir():
    from django.conf import settings

    return Path(settings.SICOP_DATA_DIR)


def _cargar_harness():
    """Importa harness_sicop (stdlib) una sola vez. Devuelve (mod, error)."""
    global _HARNESS, _HARNESS_ERROR
    if _HARNESS is not None or _HARNESS_ERROR is not None:
        return _HARNESS, _HARNESS_ERROR
    hd = harness_dir()
    if not (hd / "harness_sicop.py").exists():
        _HARNESS_ERROR = f"no existe {hd / 'harness_sicop.py'}"
        return None, _HARNESS_ERROR
    try:
        if str(hd) not in sys.path:
            sys.path.insert(0, str(hd))
        import harness_sicop  # noqa: PLC0415  (import perezoso y opcional)

        _HARNESS = harness_sicop
    except Exception as e:  # noqa: BLE001
        _HARNESS_ERROR = f"{type(e).__name__}: {e}"
    return _HARNESS, _HARNESS_ERROR


def _year(out):
    man = out / "manifiesto.json"
    if man.exists():
        try:
            ano = json.loads(man.read_text(encoding="utf-8")).get("ano")
            if isinstance(ano, int):
                return ano
        except (json.JSONDecodeError, OSError):
            pass
    return datetime.now().year


def columnas_esperadas():
    """{conjunto: [columnas]} del extractor (CONJUNTOS + PESADOS = 25)."""
    mod, _err = _cargar_harness()
    if not mod:
        return {}
    try:
        conf = dict(mod.sicop_loop.CONJUNTOS)
        conf.update(getattr(mod.sicop_loop, "PESADOS", {}))
        return {k: list(v.get("columnas", [])) for k, v in conf.items()}
    except Exception as e:  # noqa: BLE001
        logger.warning("no pude leer CONJUNTOS del harness: %s", e)
        return {}


def evaluar(year=None, out=None, estado=None):
    """Corre el A2 del harness y devuelve su veredicto.

    Devuelve:
      {"fuente": "harness_a2", "veredicto": CONFIABLE|REVISAR|BLOQUEADO|NO_EVALUADO,
       "desvios": [...], "no_evaluados": [...], "motivo": str|None}
    """
    out = Path(out) if out else data_dir()
    estado = Path(estado) if estado else (out / "estado")
    mod, err = _cargar_harness()
    if not mod:
        return {"fuente": "harness_a2", "veredicto": "NO_EVALUADO",
                "desvios": [], "no_evaluados": [{"chequeo": "harness_a2",
                                                "motivo": err}],
                "motivo": err}
    if not out.is_dir():
        motivo = f"no existe el directorio de datos {out}"
        return {"fuente": "harness_a2", "veredicto": "NO_EVALUADO",
                "desvios": [], "no_evaluados": [{"chequeo": "harness_a2",
                                                "motivo": motivo}],
                "motivo": motivo}
    try:
        estado.mkdir(parents=True, exist_ok=True)
        y = year or _year(out)
        control = mod.a2(out, y, estado)
    except Exception as e:  # noqa: BLE001
        motivo = f"a2 falló: {type(e).__name__}: {e}"
        logger.warning(motivo)
        return {"fuente": "harness_a2", "veredicto": "NO_EVALUADO",
                "desvios": [], "no_evaluados": [{"chequeo": "harness_a2",
                                                "motivo": motivo}],
                "motivo": motivo}
    return {"fuente": "harness_a2",
            "veredicto": control.get("veredicto", "NO_EVALUADO"),
            "desvios": control.get("desvios", []),
            "no_evaluados": control.get("no_evaluados", []),
            "motivo": None}
