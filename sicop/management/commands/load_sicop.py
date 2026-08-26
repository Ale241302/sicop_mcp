"""Carga los CSV de Salidas/ a Postgres.

Uso:
  python manage.py load_sicop --sync            # todo inline (sin broker)
  python manage.py load_sicop                    # encola una tarea Celery por archivo
  python manage.py load_sicop --only adjudicaciones
  python manage.py load_sicop --only competencia_por_linea
  python manage.py load_sicop --force --only contratos   # recarga (DELETE previo)
  python manage.py load_sicop --no-gold
  python manage.py load_sicop --year 2026
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from sicop import loader
from sicop.loader import CORE_SETS, GOLD_SETS


class Command(BaseCommand):
    help = "Carga los CSV de Salidas/ a Postgres (inline con --sync o via Celery)."

    def add_arguments(self, parser):
        parser.add_argument("--sync", action="store_true", help="Correr inline, sin Celery.")
        parser.add_argument("--force", action="store_true", help="Recargar archivos ya cargados.")
        parser.add_argument("--only", default=None, help="Solo un conjunto (nombre o sufijo de archivo).")
        parser.add_argument("--year", default=None, help="Solo un año para conjuntos core (ej 2026).")
        parser.add_argument("--no-gold", action="store_true", help="Saltar tablas gold.")
        parser.add_argument("--no-core", action="store_true", help="Saltar conjuntos core.")

    def handle(self, *args, **opts):
        data_dir = settings.SICOP_DATA_DIR
        if not os.path.isdir(data_dir):
            self.stderr.write(f"Directorio de datos no existe: {data_dir}")
            self.stderr.write("Ajusta SICOP_DATA_DIR en .env")
            return

        jobs = loader.discover_files(data_dir)
        if opts["only"]:
            only = opts["only"].lower()
            jobs = [j for j in jobs if only in j[0].lower() or only in os.path.basename(j[1]).lower()]
        if opts["year"]:
            jobs = [j for j in jobs if opts["year"] in os.path.basename(j[1])]
        if opts["no_gold"]:
            jobs = [j for j in jobs if not j[0].startswith("Gold")]
        if opts["no_core"]:
            jobs = [j for j in jobs if j[0].startswith("Gold")]

        self.stdout.write(f"{len(jobs)} archivos por cargar desde {data_dir}")

        if opts["sync"]:
            for model, path in jobs:
                self.stdout.write(f"> {os.path.basename(path)}")
                res = loader.load_csv(model, path, force=opts["force"])
                self.stdout.write(f"  {res}")
            return

        from sicop.tasks import load_file

        for model, path in jobs:
            load_file.delay(model, path, opts["force"])
        self.stdout.write(f"Encoladas {len(jobs)} tareas. Correr: celery -A config worker -l info")
