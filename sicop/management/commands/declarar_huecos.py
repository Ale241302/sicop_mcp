"""Declara en `meta.hueco_declarado` los huecos IRRECUPERABLES de la fuente.

No son errores de carga: la fuente no publico el dato (miembro vacio), lo publico
truncado por dia, o republico el mes anterior. Se declaran para que el producto
no los trate como datos completos. Idempotente: reconstruye la tabla.

Uso: python manage.py declarar_huecos [--file sicop/data/huecos_fuente.json]
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection

DATA = Path(__file__).resolve().parents[2] / "data" / "huecos_fuente.json"

DDL = [
    "CREATE SCHEMA IF NOT EXISTS meta",
    """CREATE TABLE IF NOT EXISTS meta.hueco_declarado (
         id serial PRIMARY KEY,
         conjunto text NOT NULL,
         mes text NOT NULL,
         tipo text NOT NULL,
         motivo text,
         evidencia text,
         declarado_en timestamptz NOT NULL DEFAULT now(),
         UNIQUE (conjunto, mes, tipo))""",
]


class Command(BaseCommand):
    help = "Declara los huecos irrecuperables de la fuente en meta.hueco_declarado."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DATA))

    def handle(self, *args, **opts):
        payload = json.loads(Path(opts["file"]).read_text(encoding="utf-8"))
        huecos = payload["huecos"]
        with connection.cursor() as cur:
            for ddl in DDL:
                cur.execute(ddl)
            cur.execute("DELETE FROM meta.hueco_declarado")
            for h in huecos:
                cur.execute(
                    "INSERT INTO meta.hueco_declarado (conjunto, mes, tipo, motivo, evidencia) "
                    "VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT (conjunto, mes, tipo) DO UPDATE "
                    "SET motivo=EXCLUDED.motivo, evidencia=EXCLUDED.evidencia",
                    [h["conjunto"], h["mes"], h["tipo"], h.get("motivo"), h.get("evidencia")],
                )
        self.stdout.write(self.style.SUCCESS(
            f"declarados {len(huecos)} huecos en meta.hueco_declarado (de {payload.get('total')})"))
