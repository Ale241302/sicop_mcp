"""Sellado sha256 de codigo + configuracion por corrida (skill §12.5).

La skill lo pide textual: *«Cada lote sella sha256 del codigo y de la
configuracion; el merge rechaza mezclas»*. El caso real que lo motivó: un agente
editó `restricciones.yaml` mientras otro corría producción, y el resultado se
publicó como si nada.

Aqui el sello cubre:
  - **codigo**: el extractor y el harness A0-A5 (los que producen el dato).
  - **config**: los YAML/JSON versionados que cambian el resultado (watchlist,
    politica de acciones, alias de marca, restricciones). Si un archivo no
    existe, no se sella (no se inventa un hash de la nada).

`verificar(esperado)` es lo que usa el merge (`recargar_anio_afectado`): si el
hash actual de un artefacto no coincide con el del arranque de la corrida, la
mezcla se rechaza en vez de publicarse a medias.
"""
import hashlib
import logging
import os

from django.conf import settings

from .models import CtlSello

logger = logging.getLogger(__name__)

# Rutas relativas a SICOP_SCRIPTS_DIR (codigo que produce el dato).
CODIGO = (
    "harness_actualizado/sicop_loop.py",
    "harness_actualizado/harness_sicop.py",
)
# Rutas relativas a SICOP_SCRIPTS_DIR o SICOP_DATA_DIR (configuracion).
CONFIG = (
    "restricciones.yaml",
    "marcas_alias.yaml",
    "colores_final.yaml",
    "prefijos_registrador.yaml",
    "estado/watchlist.json",
    "estado/politica_acciones.json",
)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _bases():
    """Directorios donde buscar los artefactos (sin duplicados, sin vacios)."""
    bases = []
    for d in (getattr(settings, "SICOP_SCRIPTS_DIR", None),
              getattr(settings, "SICOP_DATA_DIR", None)):
        if d and os.path.isdir(d) and d not in bases:
            bases.append(d)
    return bases


def _rutas():
    """[(ruta, relativo, rol)] de los artefactos que existen hoy."""
    out = []
    vistos = set()
    for base in _bases():
        for rel in CODIGO:
            p = os.path.join(base, *rel.split("/"))
            if os.path.exists(p) and p not in vistos:
                out.append((p, rel, "codigo"))
                vistos.add(p)
        for rel in CONFIG:
            p = os.path.join(base, *rel.split("/"))
            if os.path.exists(p) and p not in vistos:
                out.append((p, rel, "config"))
                vistos.add(p)
    return out


def sello_actual():
    """dict {artefacto: sha256} sin tocar la base (para comparar)."""
    s = {}
    for p, rel, _rol in _rutas():
        try:
            s[rel] = sha256_file(p)
        except OSError as e:  # noqa: BLE001
            logger.warning("no pude sellar %s: %s", p, e)
    return s


def sellar(corrida, rol_extra=None, artefactos_extra=None):
    """Sella codigo+config de esta corrida. Idempotente (borra y reescribe).

    `artefactos_extra`: rutas absolutas adicionales (p. ej. un YAML de otro
    layout). Devuelve {artefacto: sha256} para comparar al cierre.
    """
    filas = []
    for p, rel, rol in _rutas():
        try:
            h = sha256_file(p)
            tam = os.path.getsize(p)
        except OSError as e:  # noqa: BLE001
            logger.warning("no pude sellar %s: %s", p, e)
            continue
        filas.append((rel, h, tam, rol))
    for p in (artefactos_extra or []):
        if os.path.exists(p):
            try:
                filas.append((p, sha256_file(p), os.path.getsize(p),
                              rol_extra or "config"))
            except OSError as e:  # noqa: BLE001
                logger.warning("no pude sellar %s: %s", p, e)

    CtlSello.objects.filter(corrida=corrida).delete()
    CtlSello.objects.bulk_create([
        CtlSello(corrida=corrida, artefacto=rel, sha256=h, tamano_bytes=tam, rol=rol)
        for rel, h, tam, rol in filas
    ], batch_size=500)
    return {rel: h for rel, h, _t, _r in filas}


def comparar(a, b):
    """Diferencias entre dos sellos (dict artefacto->sha). Lista de tuplas."""
    diffs = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            diffs.append((k, a.get(k), b.get(k)))
    return diffs


def verificar(esperado):
    """Comprueba el sello actual contra `esperado` (dict). Devuelve diferencias.

    Un artefacto que estaba sellado y ahora no existe cuenta como diferencia:
    el insumo desaparecio a mitad de corrida.
    """
    return comparar(esperado or {}, sello_actual())
