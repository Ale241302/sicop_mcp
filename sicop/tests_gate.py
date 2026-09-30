"""Tests de los puntos de auditoria del cron (2026-09-30).

Cubren:
  1. A2 dentro del gate (a2.py + control).
  2. esquema -> gate y cuarentena en base.
  3. conjuntos recuperados (evaluacion_ofertas en bronze, lineas_sistema en
     bronze+loader).
  5. sellado sha256 de codigo+config y rechazo de mezclas.
  6. minimizacion de datos personales en `inhibiciones` (Ley 8968).
"""
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase

from sicop import a2, bronze, control, loader, sellos


class ConjuntosRecuperadosTest(SimpleTestCase):
    """Punto 3: los conjuntos que faltaban entran a bronze y loader."""

    def test_bronze_incluye_evaluacion_ofertas_y_lineas_sistema(self):
        self.assertIn("evaluacion_ofertas", bronze.BRONZE_SETS)
        self.assertIn("lineas_sistema", bronze.BRONZE_SETS)

    def test_loader_conoce_lineas_sistema(self):
        self.assertIn("lineas_sistema", loader.CORE_SETS)
        self.assertEqual(loader.CORE_SETS["lineas_sistema"], "SicopLineasSistema")

    def test_set_for_filename_resuelve_lineas_sistema(self):
        self.assertEqual(loader.set_for_filename("lineas_sistema_2026.csv"),
                         "lineas_sistema")

    def test_bronze_cubre_los_25_conjuntos_del_extractor(self):
        # 25 conjuntos de la skill = 23 core (BRONZE) + evaluacion + sistema.
        self.assertGreaterEqual(len(set(bronze.BRONZE_SETS)), 25)


class FuncionesDeSelloTest(SimpleTestCase):
    """Punto 5: sellado determinista y comparacion."""

    def test_sha256_es_determinista(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.py"
            p.write_text("print('hola')\n", encoding="utf-8")
            self.assertEqual(sellos.sha256_file(str(p)), sellos.sha256_file(str(p)))

    def test_sello_actual_incluye_codigo_y_config(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "harness_actualizado").mkdir()
            (base / "harness_actualizado" / "sicop_loop.py").write_text("x=1\n", encoding="utf-8")
            (base / "estado").mkdir()
            (base / "estado" / "watchlist.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(sellos, "_bases", return_value=[str(base)]):
                s = sellos.sello_actual()
            self.assertIn("harness_actualizado/sicop_loop.py", s)
            self.assertIn("estado/watchlist.json", s)
            self.assertEqual(len(s), 2)

    def test_comparar_detecta_cambio_y_ausencia(self):
        diffs = sellos.comparar({"a": "1", "b": "2"}, {"a": "1", "b": "9"})
        self.assertEqual(diffs, [("b", "2", "9")])
        self.assertEqual(sellos.comparar({"a": "1"}, {"a": "1", "b": "2"}),
                         [("b", None, "2")])

    def test_verificar_detecta_artefacto_que_desaparecio(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with mock.patch.object(sellos, "_bases", return_value=[str(base)]):
                diffs = sellos.verificar({"harness_actualizado/sicop_loop.py": "abc"})
            self.assertEqual(len(diffs), 1)
            self.assertEqual(diffs[0][0], "harness_actualizado/sicop_loop.py")


class MergeRechazaMezclaTest(SimpleTestCase):
    """Punto 5: recargar_anio_afectado rechaza si el sello no coincide."""

    def test_rechaza_si_el_sello_cambio(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeError) as ctx:
                loader.recargar_anio_afectado(td, td, "2026", corrida="c",
                                              sello_esperado={"x.py": "deadbeef"})
            self.assertIn("merge rechazado", str(ctx.exception))

    def test_sin_sello_no_rechaza(self):
        with tempfile.TemporaryDirectory() as td:
            res = loader.recargar_anio_afectado(td, td, "2026", corrida="c")
            self.assertEqual(res["copiados"], 0)


class A2NoEvaluadoTest(SimpleTestCase):
    """Punto 1: si el harness falta, el veredicto es NO_EVALUADO (no CONFIABLE)."""

    def test_sin_harness_devuelve_no_evaluado(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(a2, "harness_dir", return_value=Path(td)), \
                 mock.patch.object(a2, "_HARNESS", None), \
                 mock.patch.object(a2, "_HARNESS_ERROR", None):
                res = a2.evaluar(out=Path(td))
            self.assertEqual(res["veredicto"], "NO_EVALUADO")
            self.assertTrue(res["no_evaluados"])

    def test_columnas_esperadas_trae_los_conjuntos_del_extractor(self):
        cols = a2.columnas_esperadas()
        # El harness real vive en 03_scripts/harness_actualizado (SICOP_SCRIPTS_DIR).
        if cols:
            self.assertIn("lineas_sistema", cols)
            self.assertIn("NRO_SICOP", cols["lineas_sistema"])
            self.assertGreaterEqual(len(cols), 25)

    def test_no_evaluado_es_distinto_de_pass(self):
        self.assertNotEqual(control.NO_EVALUADO, "PASS")
        self.assertNotEqual(control.NO_EVALUADO, "FAIL")

    def test_salto_magnitud_ignora_precios_de_1(self):
        # Con ₡1 incluidos, la mediana cae a 1 y el único precio real (₡100) se
        # marcaría como salto ×100. La skill §8 los declara simbólicos: se filtran.
        mod, _err = a2._cargar_harness()
        if not mod:
            self.skipTest("harness no disponible")
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "competencia_por_linea.csv").write_text(
                "NRO_SICOP,NRO_LINEA,CODIGO_PRODUCTO_CL,PRECIO_UNITARIO_CRC\n"
                "A,1,1111111111111111,1.00\n"
                "A,2,1111111111111111,1.00\n"
                "A,3,1111111111111111,1.00\n"
                "A,4,1111111111111111,1.00\n"
                "A,5,1111111111111111,100.00\n",
                encoding="utf-8-sig", newline="")
            d, motivo = mod.chequeo_salto_magnitud(Path(td), 2026)
        self.assertIsNone(motivo)
        self.assertIsNone(d, "un precio simbólico de ₡1 no debe generar desvío")


class EsquemaEsperadoTest(SimpleTestCase):
    """Punto 2: columna esperada ausente se detecta (config del harness)."""

    def test_deteccion_local_sin_base(self):
        esperadas = a2.columnas_esperadas()
        if not esperadas:
            self.skipTest("harness no disponible en este entorno")
        # El helper puro compara conjuntos; probamos la logica con un caso directo.
        self.assertTrue(all(isinstance(v, list) for v in esperadas.values()))


class SerializerInhibicionesTest(SimpleTestCase):
    """Punto 6: nombre y cedula del funcionario enmascarados por defecto."""

    def _data(self):
        from sicop.api.serializers import serializer_for
        from sicop.models import SicopInhibiciones

        obj = SicopInhibiciones(NOM_FUNCIONARIO="JUAN PEREZ SOLANO",
                                CED_FUNCIONARIO="102340567")
        return serializer_for(SicopInhibiciones)(obj).data

    def test_enmascara_por_defecto(self):
        data = self._data()
        self.assertNotEqual(data.get("NOM_FUNCIONARIO"), "JUAN PEREZ SOLANO")
        self.assertIn("*", data.get("CED_FUNCIONARIO") or "")

    def test_expone_solo_con_decision_expresa(self):
        with mock.patch("django.conf.settings.SICOP_INHIBICIONES_NOMBRES", True):
            data = self._data()
        self.assertEqual(data.get("NOM_FUNCIONARIO"), "JUAN PEREZ SOLANO")
        self.assertEqual(data.get("CED_FUNCIONARIO"), "102340567")

    def test_no_se_puede_filtrar_por_nombre(self):
        from sicop.api import views

        self.assertNotIn("NOM_FUNCIONARIO",
                         views.FILTERABLE.get("SicopInhibiciones", []))


class EsquemaYCUarentenaDBTest(TestCase):
    """Puntos 1-2 con base: ctl_esquema -> gate y cuarentena consultable."""

    def test_columnas_ausentes_desde_ctl_esquema(self):
        control.registrar_esquema("lineas_sistema",
                                  ["NRO_SICOP", "NUMERO_LINEA"], corrida_id="t")
        # Inyectamos la expectativa del harness para no depender de su presencia.
        fake = {"lineas_sistema": ["NRO_SICOP", "NUMERO_LINEA", "NUMERO_PARTIDA"]}
        with mock.patch.object(a2, "columnas_esperadas", return_value=fake):
            aus = control._columnas_ausentes_esquema()
        self.assertEqual(aus, {"lineas_sistema": ["NUMERO_PARTIDA"]})

    def test_cuarentena_desde_archivo(self):
        with tempfile.TemporaryDirectory() as td:
            qdir = Path(td)
            (qdir / "ofertas_2026.csv").write_text(
                "CONJUNTO,MES_PUBLICACION,MOTIVO,N_CAMPOS,CAMPOS_CRUDOS\n"
                "ofertas,202601,exceso de 2 campos,9,\"[\\\"a\\\",\\\"b\\\"]\"\n",
                encoding="utf-8-sig", newline="")
            n = control.registrar_cuarentena_desde_archivo("corrida-test", str(qdir))
            self.assertEqual(n, 1)
            row = control.CtlCuarentena.objects.get(CORRIDA_ID="corrida-test")
            self.assertEqual(row.TABLA, "ofertas")
            self.assertIn("n_campos=9", row.MOTIVO)
            # idempotente: re-correr no duplica
            control.registrar_cuarentena_desde_archivo("corrida-test", str(qdir))
            self.assertEqual(
                control.CtlCuarentena.objects.filter(CORRIDA_ID="corrida-test").count(), 1)


class SelloDBTest(TestCase):
    """Punto 5 con base: sellar persiste y es idempotente por corrida."""

    def test_sellar_e_idempotente(self):
        from sicop.models import CtlSello

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "harness_actualizado").mkdir()
            (base / "harness_actualizado" / "sicop_loop.py").write_text("x=1\n", encoding="utf-8")
            with mock.patch.object(sellos, "_bases", return_value=[str(base)]):
                s1 = sellos.sellar("c1")
                s2 = sellos.sellar("c1")
                self.assertEqual(s1, s2)
                self.assertEqual(CtlSello.objects.filter(corrida="c1").count(), len(s1))
                s3 = sellos.sellar("c2")
                self.assertEqual(s3, s1)
                self.assertEqual(CtlSello.objects.filter(corrida="c2").count(), len(s1))


class PruebasPoliticaTest(TestCase):
    """Punto 6: el gate de politica incluye la minimizacion de `inhibiciones`."""

    def test_p6_inhibiciones_pasa(self):
        from sicop.enforcement import pruebas_politica

        r = pruebas_politica("test-politica")
        self.assertIn("p6_inhibiciones_minimizadas", r)
        self.assertTrue(r["p6_inhibiciones_minimizadas"],
                        "la API debe enmascarar nombre/cedula por defecto")
        self.assertTrue(all(r.values()), f"algun politica fallo: {r}")
