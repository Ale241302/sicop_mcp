"""FASE 4 — Prueba: ficha ESOSA, backtest de invitaciones, holdout temporal + gate."""
import json

from django.core.management.base import BaseCommand

from sicop.fase4 import ficha_esosa, backtest_invitaciones, holdout


class Command(BaseCommand):
    help = "FASE 4: ficha ESOSA desde gold, backtest de invitaciones, holdout temporal + gate de muerte."

    def add_arguments(self, parser):
        parser.add_argument("--solo", choices=["ficha", "backtest", "holdout"], default=None)
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        result = {}
        if opts["solo"] in (None, "ficha"):
            result["ficha_esosa"] = ficha_esosa()
        if opts["solo"] in (None, "backtest"):
            result["backtest"] = backtest_invitaciones()
        if opts["solo"] in (None, "holdout"):
            result["holdout"] = holdout()
        if opts["json"]:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            for k, v in result.items():
                self.stdout.write(f"== {k} ==")
                self.stdout.write(json.dumps(v, ensure_ascii=False, indent=2, default=str)[:3000])
