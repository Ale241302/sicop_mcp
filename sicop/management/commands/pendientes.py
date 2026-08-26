"""Pendientes del traspaso P1-P7 (resolubles): conversion moneda, familias, recursos, sanciones, tamano."""
import json

from django.core.management.base import BaseCommand

from sicop.pendientes import PENDIENTES, run


class Command(BaseCommand):
    help = "Resuelve los pendientes P1, P3, P5, P6, P7 del traspaso."

    def add_arguments(self, parser):
        parser.add_argument("--solo", default=None, help="p1_conversion_cartera,p3_catalogo_familias,...")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        names = [n.strip() for n in opts["solo"].split(",") if n.strip()] if opts["solo"] else None
        result = run(names)
        if opts["json"]:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            for k, v in result.items():
                self.stdout.write(f"== {k} ==")
                self.stdout.write(json.dumps(v, ensure_ascii=False, indent=2, default=str)[:2500])
