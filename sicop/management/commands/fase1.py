"""FASE 1: carga inicial canonica (bronze -> silver facts -> tests -> gold publica).

Uso:
  python manage.py fase1                     # todo (bronze + silver + tests + gold)
  python manage.py fase1 --skip-bronze       # sin bronze (si ya existe)
  python manage.py fase1 --solo-silver       # solo los 6 hechos
  python manage.py fase1 --corrida MI_CORRIDA
"""
from datetime import datetime

from django.core.management.base import BaseCommand

from sicop import control
from sicop.derivadas import run as run_derivadas


class Command(BaseCommand):
    help = "FASE 1: bronze + silver (6 hechos) + tests-gate + publicacion atomica de gold."

    def add_arguments(self, parser):
        parser.add_argument("--corrida", default=None)
        parser.add_argument("--skip-bronze", action="store_true")
        parser.add_argument("--solo-silver", action="store_true")
        parser.add_argument("--solo-tests", action="store_true")

    def handle(self, *args, **opts):
        from django.conf import settings

        corrida = opts["corrida"] or f"fase1-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        control.registrar_corrida(corrida, "bronze+silver+gold", notas="FASE 1")

        if opts["solo_tests"]:
            results, failed = control.run_tests(corrida)
            for k, v in results.items():
                self.stdout.write(f"  {k}: {'PASS' if v else 'FAIL'}")
            control.cerrar_corrida(corrida, "TESTS")
            return

        if not opts["skip_bronze"] and not opts["solo_silver"]:
            self.stdout.write("== bronze ==")
            from sicop import bronze
            bronze.backfill_core(corrida, settings.SICOP_DATA_DIR)

        if not opts["solo_tests"]:
            self.stdout.write("== silver (6 hechos) ==")
            from sicop import silver
            corrida = silver.build_all(corrida)

        if opts["solo_silver"]:
            return

        self.stdout.write("== catalogo_campo + ctl_deriva ==")
        run_derivadas(["catalogo_campo", "ctl_deriva"])

        self.stdout.write("== tests como gate ==")
        ok, failed = control.publicar_gold(corrida)
        if ok:
            self.stdout.write(self.style.SUCCESS(f"GOLD PUBLICADO (corrida {corrida})"))
        else:
            self.stdout.write(self.style.ERROR(f"BLOQUEADO por tests: {failed}"))
