"""O5 - regresion del bug de carga 2026: un archivo de un conjunto no puede
cargarse en el modelo de otro (p.ej. adjudicaciones_firme_2026.csv en
SicopAdjudicaciones). El bug original usaba fn.split("_")[0].
"""
from django.test import SimpleTestCase

from sicop import loader


class SetForFilenameTest(SimpleTestCase):
    def test_firme_y_adjudicaciones_se_distinguen(self):
        self.assertEqual(loader.set_for_filename("adjudicaciones_2026.csv"), "adjudicaciones")
        self.assertEqual(loader.set_for_filename("adjudicaciones_firme_2026.csv"),
                         "adjudicaciones_firme")

    def test_todos_los_sets_resuelven_sin_colision(self):
        for setn in loader.CORE_SETS:
            self.assertEqual(loader.set_for_filename(f"{setn}_2026.csv"), setn,
                             msg=f"no resuelve {setn}_2026.csv")

    def test_archivos_no_particionados_por_anio(self):
        for fn in ("catalogo_productos.csv", "invitaciones_2022-002.csv",
                   "barato_y_prorrogado_resumen.csv"):
            self.assertIsNone(loader.set_for_filename(fn), msg=fn)


class GuardModelFileTest(SimpleTestCase):
    def test_rechaza_modelo_equivocado(self):
        with self.assertRaises(ValueError):
            loader._guard_model_file("SicopAdjudicaciones", "/data/adjudicaciones_firme_2026.csv")

    def test_acepta_modelo_correcto(self):
        loader._guard_model_file("SicopAdjudicaciones", "/data/adjudicaciones_2026.csv")
        loader._guard_model_file("SicopAdjudicacionesFirme",
                                 "/data/adjudicaciones_firme_2026.csv")

    def test_no_bloquea_archivos_sin_anio(self):
        loader._guard_model_file("SicopInvitaciones", "/data/invitaciones_2022-002.csv")


class SembrarRecuperacionTest(SimpleTestCase):
    def test_siembra_la_base_completa_en_recuperacion(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "data"
            rec = Path(td) / "rec"
            data.mkdir()
            rec.mkdir()
            (data / "ordenes_pedido_2026.csv").write_text("a\n" * 100, encoding="utf-8", newline="\n")
            # recovery trae una copia PARCIAL (mas chica)
            (rec / "ordenes_pedido_2026.csv").write_text("a\n" * 5, encoding="utf-8", newline="\n")
            copiados = loader.sembrar_recuperacion(str(rec), str(data), "2026")
            self.assertIn("ordenes_pedido_2026.csv", copiados)
            self.assertEqual((rec / "ordenes_pedido_2026.csv").stat().st_size,
                             (data / "ordenes_pedido_2026.csv").stat().st_size)

    def test_no_pisa_un_recovery_mas_completo(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "data"
            rec = Path(td) / "rec"
            data.mkdir()
            rec.mkdir()
            (data / "ordenes_pedido_2026.csv").write_text("a\n" * 5, encoding="utf-8", newline="\n")
            (rec / "ordenes_pedido_2026.csv").write_text("a\n" * 100, encoding="utf-8", newline="\n")
            copiados = loader.sembrar_recuperacion(str(rec), str(data), "2026")
            self.assertEqual(copiados, [])
            self.assertEqual((rec / "ordenes_pedido_2026.csv").stat().st_size,
                             len("a\n" * 100))


class CoercerDatetimeTest(SimpleTestCase):
    def test_dt_devuelve_aware(self):
        from django.utils import timezone as dj_tz
        for raw in ("2026-09-25 09:27:33", "2026-09-25", "25/09/2026 09:27:33"):
            dt = loader._dt(raw)
            self.assertIsNotNone(dt, msg=raw)
            self.assertFalse(dj_tz.is_naive(dt), msg=f"{raw} debe ser aware")

    def test_dt_vacio(self):
        self.assertIsNone(loader._dt(""))
        self.assertIsNone(loader._dt(None))


class HuecosFuenteJsonTest(SimpleTestCase):
    def test_json_valido(self):
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parent / "data" / "huecos_fuente.json"
        self.assertTrue(p.exists(), "falta sicop/data/huecos_fuente.json")
        payload = json.loads(p.read_text(encoding="utf-8"))
        self.assertGreater(payload["total"], 0)
        self.assertEqual(len(payload["huecos"]), payload["total"])
        tipos = set()
        for h in payload["huecos"]:
            for k in ("mes", "conjunto", "tipo"):
                self.assertIn(k, h, msg=str(h))
            self.assertRegex(h["mes"], r"^\d{6}$")
            tipos.add(h["tipo"])
        self.assertTrue({"ZIP_VACIO", "TRUNCADO_FUENTE", "REPUBLICADO"} <= tipos)


class SenalesCambioFuenteTest(SimpleTestCase):
    """La reescritura de la fuente debe ser UNA sola senal por mes (no una por dia)."""

    def test_senales_define_helpers(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parent / "senales.py").read_text(encoding="utf-8")
        self.assertIn("def emitir_cambio_fuente(", src)
        self.assertIn("def atender_cambio_fuente(", src)

    def test_ciclo_usa_el_helper_deduplicado(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parent / "ciclo.py").read_text(encoding="utf-8")
        self.assertIn("senales.emitir_cambio_fuente(", src)
        self.assertIn("senales.atender_cambio_fuente(", src)
        self.assertNotIn('senales._emit(corrida, "cambio_hash_fuente"', src)
