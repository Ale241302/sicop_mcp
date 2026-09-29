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
            (data / "ordenes_pedido_2026.csv").write_text("a\n" * 100, encoding="utf-8")
            # recovery trae una copia PARCIAL (mas chica)
            (rec / "ordenes_pedido_2026.csv").write_text("a\n" * 5, encoding="utf-8")
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
            (data / "ordenes_pedido_2026.csv").write_text("a\n" * 5, encoding="utf-8")
            (rec / "ordenes_pedido_2026.csv").write_text("a\n" * 100, encoding="utf-8")
            copiados = loader.sembrar_recuperacion(str(rec), str(data), "2026")
            self.assertEqual(copiados, [])
            self.assertEqual((rec / "ordenes_pedido_2026.csv").stat().st_size,
                             len("a\n" * 100))
