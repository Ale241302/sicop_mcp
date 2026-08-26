"""Recalcula las derivadas del plan que faltaban.

Uso:
  python manage.py recalcular_derivadas                   # todas
  python manage.py recalcular_derivadas --only producto_firma,precios_identicos
"""
from django.core.management.base import BaseCommand

from sicop.derivadas import ALL, run


class Command(BaseCommand):
    help = "Regenera las derivadas: recursos_desenlace, tiempos_por_etapa, precios_identicos, producto_firma, invitados_vs_ofertantes."

    def add_arguments(self, parser):
        parser.add_argument("--only", default=None, help="Solo estas (comas): " + ",".join(ALL))

    def handle(self, *args, **opts):
        names = [n.strip() for n in opts["only"].split(",") if n.strip()] if opts["only"] else None
        run(names)
