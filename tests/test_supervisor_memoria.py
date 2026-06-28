import unittest
from unittest.mock import patch

from agents.supervisor import (
    _construir_filtros_estrictos,
    recuperar_memorias_con_fallback,
)
from state import PrediccionMetadatosSolicitud


class TestRecuperarMemoriasConFallback(unittest.TestCase):
    @patch("agents.supervisor.buscar_memorias_similares")
    def test_usa_resultados_filtrados_si_existen(self, mock_buscar):
        mock_buscar.return_value = [
            {
                "tarea_original": "Cafeterías Mar del Plata",
                "enfoque_exitoso": "investigador + ejecutor",
                "resultado_resumido": "Informe gastronómico",
                "sector": "Gastronomía",
                "tipo_tarea": "Guía Comercial",
                "tags": "Mar del Plata, cafeterías",
                "fecha": "2026-06-26",
                "similitud": 0.91,
            }
        ]
        prediccion = PrediccionMetadatosSolicitud(
            sector_predicho="Gastronomía",
            tipo_tarea_predicho="Guía Comercial",
        )

        memorias, uso_fallback = recuperar_memorias_con_fallback(
            "cafeterías en Mar del Plata",
            prediccion,
        )

        self.assertFalse(uso_fallback)
        self.assertEqual(len(memorias), 1)
        self.assertEqual(memorias[0].sector, "Gastronomía")
        mock_buscar.assert_called_once_with(
            "cafeterías en Mar del Plata",
            limite=3,
            filtros={"sector": "Gastronomía", "tipo_tarea": "Guía Comercial"},
        )

    @patch("agents.supervisor.buscar_memorias_similares")
    def test_fallback_semantico_si_filtro_estricto_vacio(self, mock_buscar):
        mock_buscar.side_effect = [
            [],
            [
                {
                    "tarea_original": "Tarea genérica",
                    "enfoque_exitoso": "plan mixto",
                    "resultado_resumido": "Resultado previo",
                    "sector": "Turismo",
                    "tipo_tarea": "Informe Comparativo",
                    "tags": "playa",
                    "fecha": "2026-01-10",
                    "similitud": 0.75,
                }
            ],
        ]
        prediccion = PrediccionMetadatosSolicitud(
            sector_predicho="Gastronomía",
            tipo_tarea_predicho="Estudio de Mercado",
        )

        memorias, uso_fallback = recuperar_memorias_con_fallback(
            "hamburguesas smash en La Plata",
            prediccion,
        )

        self.assertTrue(uso_fallback)
        self.assertEqual(len(memorias), 1)
        self.assertEqual(mock_buscar.call_count, 2)
        mock_buscar.assert_any_call(
            "hamburguesas smash en La Plata",
            limite=3,
            filtros={"sector": "Gastronomía", "tipo_tarea": "Estudio de Mercado"},
        )
        mock_buscar.assert_any_call("hamburguesas smash en La Plata", limite=3)


class TestConstruirFiltrosEstrictos(unittest.TestCase):
    def test_incluye_sector_y_tipo(self):
        prediccion = PrediccionMetadatosSolicitud(
            sector_predicho="Tecnología",
            tipo_tarea_predicho="Análisis Técnico",
        )
        filtros = _construir_filtros_estrictos(prediccion)
        self.assertEqual(
            filtros,
            {"sector": "Tecnología", "tipo_tarea": "Análisis Técnico"},
        )


if __name__ == "__main__":
    unittest.main()
