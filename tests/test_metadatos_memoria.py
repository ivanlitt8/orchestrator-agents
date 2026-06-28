import unittest

from tools.vector_db import construir_filtro_chroma, normalizar_metadatos_memoria


class TestNormalizarMetadatosMemoria(unittest.TestCase):
    def test_serializa_lista_como_tags_csv(self):
        resultado = normalizar_metadatos_memoria(
            {
                "sector": "Gastronomía",
                "tags": ["La Plata", "smash burgers", "precios"],
            }
        )
        self.assertEqual(resultado["sector"], "Gastronomía")
        self.assertEqual(resultado["tags"], "La Plata, smash burgers, precios")

    def test_preserva_fecha_y_booleanos(self):
        resultado = normalizar_metadatos_memoria(
            {
                "fecha": "2026-06-26",
                "aprobado_por_humano": True,
            }
        )
        self.assertEqual(resultado["fecha"], "2026-06-26")
        self.assertTrue(resultado["aprobado_por_humano"])


class TestConstruirFiltroChroma(unittest.TestCase):
    def test_filtro_sector_unico(self):
        filtro = construir_filtro_chroma({"sector": "Gastronomía"})
        self.assertEqual(filtro, {"sector": "Gastronomía"})

    def test_filtro_multiple_usa_and(self):
        filtro = construir_filtro_chroma(
            {
                "sector": "Tecnología",
                "tipo_tarea": "Análisis Técnico",
            }
        )
        self.assertEqual(
            filtro,
            {
                "$and": [
                    {"sector": "Tecnología"},
                    {"tipo_tarea": "Análisis Técnico"},
                ]
            },
        )

    def test_ignora_claves_no_filtrables(self):
        filtro = construir_filtro_chroma({"desconocido": "valor"})
        self.assertIsNone(filtro)


if __name__ == "__main__":
    unittest.main()
