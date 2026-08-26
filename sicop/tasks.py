import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="sicop.load_file")
def load_file(self, model_name, path, force=False):
    """Carga un CSV individual. Una tarea por archivo."""
    from .loader import load_csv

    try:
        return load_csv(model_name, path, force=force)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo cargando %s", path)
        raise self.retry(exc=exc, countdown=30, max_retries=3)


@shared_task(bind=True, name="sicop.load_all")
def load_all(self, force=False, only=None, gold=True, core=True):
    """Encola una tarea por archivo."""
    from django.conf import settings

    from .loader import CORE_SETS, GOLD_SETS, discover_files

    data_dir = settings.SICOP_DATA_DIR
    jobs = discover_files(data_dir)

    if only:
        jobs = [j for j in jobs if j[0].lower() == only.lower() or j[1].lower().endswith(only.lower())]
    if not core:
        jobs = [j for j in jobs if j[0].startswith("Gold")]
    if not gold:
        jobs = [j for j in jobs if not j[0].startswith("Gold")]

    queued = []
    for model, path in jobs:
        load_file.delay(model, path, force)
        queued.append(path)
    return {"queued": len(queued), "files": queued}


@shared_task(bind=True, name="sicop.ciclo_diario")
def ciclo_diario(self, corrida=None):
    """El ciclo de las 06:00: vigilancia + consolidar + senales + cola + gold."""
    from .ciclo import ciclo_diario as run

    return run(corrida=corrida, reprocesar=True, gold=True)


@shared_task(bind=True, name="sicop.vigilancia_reescritura")
def vigilancia_reescritura(self, corrida=None):
    """Vigilancia de reescritura (3 cerrados + 2 rotativos)."""
    from .vigilancia import revisar_reescritura

    return revisar_reescritura(corrida=corrida or "vig-{date}")


@shared_task(bind=True, name="sicop.consolidar_resultados")
def consolidar_resultados(self, corrida=None):
    from .resultado import consolidar_resultados

    return consolidar_resultados(corrida)
