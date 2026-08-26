"""Ciclo diario (FASE 2): vigilancia + consolidar + senales + cola + gold.

Uso:
  python manage.py ciclo_diario                 # el ciclo completo de las 06:00
  python manage.py ciclo_diario --sin-gold      # sin rebuild de gold
  python manage.py ciclo_diario --sin-reproceso # no re-extraer meses cambiados
"""
from django.core.management.base import BaseCommand

from sicop.ciclo import ciclo_diario


class Command(BaseCommand):
    help = "FASE 2: ejecuta el ciclo diario (vigilancia, consolidar, senales, cola, gold)."

    def add_arguments(self, parser):
        parser.add_argument("--corrida", default=None)
        parser.add_argument("--sin-gold", action="store_true")
        parser.add_argument("--sin-reproceso", action="store_true")

    def handle(self, *args, **opts):
        res = ciclo_diario(corrida=opts["corrida"],
                           reprocesar=not opts["sin_reproceso"],
                           gold=not opts["sin_gold"])
        self.stdout.write(self.style.SUCCESS(
            f"ciclo {res['corrida']}: {res['senales']} senales | cambios: {res['cambios']}"))
