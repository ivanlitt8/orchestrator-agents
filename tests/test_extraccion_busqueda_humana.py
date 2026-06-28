import unittest
from unittest.mock import MagicMock, patch

from agents.reviewer import (
    _normalizar_extraccion_busqueda,
    _resumir_contexto_para_extractor,
    detectar_necesidad_busqueda_humana,
)
from state import ExtraccionBusquedaFeedbackHumano


class TestNormalizarExtraccionBusqueda(unittest.TestCase):
    def test_redaccion_pura_devuelve_false(self):
        extraccion = ExtraccionBusquedaFeedbackHumano(
            necesita_nueva_busqueda=False,
            nueva_query_busqueda="",
        )
        necesita, query = _normalizar_extraccion_busqueda(extraccion)
        self.assertFalse(necesita)
        self.assertEqual(query, "")

    def test_busqueda_sin_query_se_degrada_a_false(self):
        extraccion = ExtraccionBusquedaFeedbackHumano(
            necesita_nueva_busqueda=True,
            nueva_query_busqueda="   ",
        )
        necesita, query = _normalizar_extraccion_busqueda(extraccion)
        self.assertFalse(necesita)
        self.assertEqual(query, "")

    def test_busqueda_con_query_valida(self):
        extraccion = ExtraccionBusquedaFeedbackHumano(
            necesita_nueva_busqueda=True,
            nueva_query_busqueda="precios Starlink Argentina 2026",
        )
        necesita, query = _normalizar_extraccion_busqueda(extraccion)
        self.assertTrue(necesita)
        self.assertEqual(query, "precios Starlink Argentina 2026")


class TestResumirContexto(unittest.TestCase):
    def test_contexto_vacio(self):
        self.assertEqual(
            _resumir_contexto_para_extractor([]),
            "(sin contexto investigado previo)",
        )

    def test_resume_primeras_lineas(self):
        contexto = [
            "[Investigador] Subtarea 'inv-1' completada.\n"
            "Hallazgo sobre cafeterías de especialidad en Mar del Plata.",
            "[Investigador] Búsqueda adicional: precios promedio 2026.\n"
            "Datos de precios de café de especialidad.",
        ]
        resumen = _resumir_contexto_para_extractor(contexto)
        self.assertIn("1.", resumen)
        self.assertIn("2.", resumen)


class TestDetectarNecesidadBusquedaHumana(unittest.TestCase):
    def test_feedback_vacio_no_invoca_llm(self):
        with patch("agents.reviewer._obtener_extractor_busqueda_humana") as mock_factory:
            necesita, query = detectar_necesidad_busqueda_humana("   ")
            mock_factory.assert_not_called()
        self.assertFalse(necesita)
        self.assertEqual(query, "")

    @patch("agents.reviewer._obtener_extractor_busqueda_humana")
    def test_feedback_redaccion_clasificado_como_false(self, mock_factory):
        mock_extractor = MagicMock()
        mock_extractor.invoke.return_value = ExtraccionBusquedaFeedbackHumano(
            necesita_nueva_busqueda=False,
            nueva_query_busqueda="",
        )
        mock_factory.return_value = mock_extractor

        necesita, query = detectar_necesidad_busqueda_humana(
            "Cámbiale el título y hazlo más corto",
            solicitud="Informe sobre cafeterías",
            contexto_acumulado=["[Investigador] Datos previos sobre cafeterías."],
        )

        self.assertFalse(necesita)
        self.assertEqual(query, "")
        mock_extractor.invoke.assert_called_once()

    @patch("agents.reviewer._obtener_extractor_busqueda_humana")
    def test_feedback_busqueda_clasificado_como_true(self, mock_factory):
        mock_extractor = MagicMock()
        mock_extractor.invoke.return_value = ExtraccionBusquedaFeedbackHumano(
            necesita_nueva_busqueda=True,
            nueva_query_busqueda="horarios apertura cafeterías Mar del Plata 2026",
        )
        mock_factory.return_value = mock_extractor

        necesita, query = detectar_necesidad_busqueda_humana(
            "Investiga los horarios de apertura actuales de las cafeterías mencionadas",
            solicitud="Informe sobre cafeterías en Mar del Plata",
            contexto_acumulado=["[Investigador] Listado de cafeterías de especialidad."],
        )

        self.assertTrue(necesita)
        self.assertEqual(query, "horarios apertura cafeterías Mar del Plata 2026")


if __name__ == "__main__":
    unittest.main()
