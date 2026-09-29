"""O6 - Censo VIVO: recalcula meta.censo_mes_tabla desde la base (no estatico).

El censo del paquete (r3_r2_censo) es un CSV estatico: no se regenera, llega
hasta 202608 y no audita `invitaciones`. Este comando recalcula, para cada
conjunto CORE y cada MES_PUBLICACION presente en la base, las filas cargadas y
el veredicto, y lo persiste en meta.censo_mes_tabla (conservando el filas_zip
conocido). Sirve de gate del mes en curso.

Uso:
  python manage.py censo_vivo            # dry-run: imprime, no escribe
  python manage.py censo_vivo --write    # persiste en meta.censo_mes_tabla
"""
import logging

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count

from sicop import loader

logger = logging.getLogger(__name__)

# conjuntos CORE que se auditan (loader.CORE_SETS; ya incluye invitaciones).
SETS = list(dict.fromkeys(list(loader.CORE_SETS.keys()) + ["invitaciones"]))


def _model_for(setn):
    from django.apps import apps
    return apps.get_model("sicop", loader.CORE_SETS[setn])


def _veredicto(fz, base):
    if fz is None:
        return "COMPLETO" if base > 0 else "VACIO"
    if fz == 0:
        return "ZIP_VACIO"
    if base == 0:
        return "VACIO"
    return "COMPLETO" if (base / fz * 100) >= 95 else "PARCIAL"


class Command(BaseCommand):
    help = "Recalcula meta.censo_mes_tabla desde la base (incluye invitaciones y el mes en curso)."

    def add_arguments(self, parser):
        parser.add_argument("--write", action="store_true",
                            help="persiste en meta.censo_mes_tabla (default: dry-run)")
        parser.add_argument("--solo", default=None, help="un conjunto (p.ej. invitaciones)")

    def handle(self, *args, **opts):
        sets = [opts["solo"]] if opts.get("solo") else SETS

        # filas_zip / filas_base conocidos (para conservar referencia de fuente)
        prev = {}
        with connection.cursor() as cur:
            cur.execute("SELECT tabla, aaaamm, filas_zip FROM meta.censo_mes_tabla")
            for tabla, mes, fz in cur.fetchall():
                prev[(tabla, mes)] = float(fz) if fz is not None else None

        filas = []
        for setn in sets:
            if setn not in loader.CORE_SETS:
                continue
            try:
                model = _model_for(setn)
            except LookupError:
                self.stderr.write(f"  {setn}: sin modelo, se omite")
                continue
            q = (model.objects.exclude(MES_PUBLICACION__isnull=True)
                 .values("MES_PUBLICACION").annotate(n=Count("id")))
            for r in q.iterator():
                mes = r["MES_PUBLICACION"]
                base = r["n"]
                fz = prev.get((setn, mes))
                pct = round(base / fz * 100, 2) if fz else None
                delta = (base - int(fz)) if fz is not None else None
                filas.append((setn, mes, fz, base, delta, pct, _veredicto(fz, base)))

        filas.sort(key=lambda x: (x[1], x[0]))
        for f in filas:
            self.stdout.write(f"{f[0]:24s} {f[1]} base={f[3]:>8d} zip={f[2]} {f[6]}")

        self.stdout.write(f"TOTAL celdas: {len(filas)}")
        if not opts["write"]:
            self.stdout.write(self.style.WARNING("dry-run: no se escribio nada (use --write)"))
            return

        with connection.cursor() as cur:
            for setn, mes, fz, base, delta, pct, ver in filas:
                cur.execute(
                    "DELETE FROM meta.censo_mes_tabla WHERE tabla=%s AND aaaamm=%s", [setn, mes])
                cur.execute(
                    "INSERT INTO meta.censo_mes_tabla "
                    "(aaaamm, tabla, filas_zip, filas_base, delta, pct_cargado, veredicto, nota) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    [mes, setn, int(fz) if fz is not None else None, base, delta, pct, ver,
                     "censo vivo (recalculado desde la base)"])
        self.stdout.write(self.style.SUCCESS(f"meta.censo_mes_tabla actualizado: {len(filas)} celdas"))
