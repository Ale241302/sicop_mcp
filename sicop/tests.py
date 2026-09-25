"""Tests de regresion del bug de search_path (copia huerfana de gold_invitaciones).

Contexto: la conexion pooled de Django (CONN_MAX_AGE) quedaba con
search_path=ag_catalog,public tras las queries AGE del ciclo. El rebuild de
gold_invitaciones corre en esa misma conexion; sin calificar el esquema, creaba
ag_catalog.gold_invitaciones (huerfana) y dejaba congelada la tabla que leen las
tools (sicop.gold_invitaciones).

Estos tests NO tocan la base: verifican el SQL emitido (con un cursor falso) y
que los archivos califiquen el esquema.
"""
import contextlib
import re
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from sicop import sync_capas

_BASE = Path(__file__).resolve().parent


class _FakeCursor:
    def __init__(self, log):
        self.log = log
        self.description = None

    def execute(self, sql, params=None):
        self.log.append(sql)

    def fetchone(self):
        return (True,)

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConnection:
    def __init__(self, log):
        self._log = log

    def cursor(self):
        return _FakeCursor(self._log)


class RebuildGoldInvitacionesTest(SimpleTestCase):
    def _run(self):
        log = []
        with mock.patch("django.db.connection", _FakeConnection(log)), \
             mock.patch("django.db.transaction.atomic",
                        lambda *a, **k: contextlib.nullcontext()):
            res = sync_capas._reconstruir_gold_invitaciones()
        return res, log

    def test_escribe_en_esquema_sicop_y_resetea_search_path(self):
        res, log = self._run()
        self.assertEqual(res["estado"], "OK")
        for sql in log:
            # "RENAME TO gold_invitaciones" es correcto sin esquema (hereda el de
            # la tabla); el resto de referencias DEBEN venir calificadas con sicop.
            limpio = sql.replace("RENAME TO gold_invitaciones", "RENAME TO <tabla>")
            self.assertIsNone(
                re.search(r"(?<!sicop\.)gold_invitaciones", limpio),
                msg=f"referencia sin esquema: {sql}",
            )
        self.assertTrue(any("public.sicop_invitaciones" in s for s in log),
                        "el origen debe venir de public.sicop_invitaciones (la cruda vive en public)")
        self.assertIn("RESET search_path", log,
                      "debe restaurar el search_path que ensucio AGE")

    def test_recrea_los_cuatro_indices_con_nombre_final(self):
        _, log = self._run()
        for nombre, _ in sync_capas._GINV_IDX:
            self.assertTrue(
                any(f"ALTER INDEX sicop.{nombre}__new RENAME TO {nombre}" in s for s in log),
                msg=f"falta renombrar el indice temporal de {nombre}",
            )


class ArchivosSinSearchPathAmbiguoTest(SimpleTestCase):
    def test_sync_grafo_invitados_califica_esquema(self):
        src = (_BASE / "sync_grafo_invitados.py").read_text(encoding="utf-8")
        self.assertIn("FROM sicop.gold_invitaciones", src)
        self.assertNotIn("FROM gold_invitaciones", src)

    def test_queries_tools_califican_esquema(self):
        src = (_BASE / "queries.py").read_text(encoding="utf-8")
        self.assertNotIn("FROM gold_invitaciones ", src)
        self.assertGreaterEqual(src.count("sicop.gold_invitaciones"), 3)
        self.assertIn("RESET search_path", src)
