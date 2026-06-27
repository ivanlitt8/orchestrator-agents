import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_community.tools import TavilySearchResults

load_dotenv()

MAX_RESULTS = 5
SEARCH_DEPTH = "advanced"


def _obtener_api_key() -> str:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta la variable de entorno TAVILY_API_KEY. "
            "Configúrala en el archivo .env antes de ejecutar búsquedas."
        )
    return api_key


@lru_cache(maxsize=1)
def _obtener_herramienta_busqueda() -> TavilySearchResults:
    """Instancia singleton de TavilySearchResults con credenciales del entorno."""
    return TavilySearchResults(
        max_results=MAX_RESULTS,
        search_depth=SEARCH_DEPTH,
        include_answer=True,
        tavily_api_key=_obtener_api_key(),
    )


def _formatear_hallazgos(
    consulta: str,
    resultados: list[dict],
    respuesta: str | None,
) -> str:
    lineas = [
        f"[Investigador — Tavily] Subtarea: {consulta}",
    ]
    if respuesta:
        lineas.append(f"Resumen ejecutivo: {respuesta}")

    lineas.append("Hallazgos detallados:")
    for indice, item in enumerate(resultados, start=1):
        titulo = item.get("title", "Sin título")
        url = item.get("url", "")
        contenido = item.get("content", "")
        score = item.get("score")

        lineas.append(f"  {indice}. {titulo}")
        lineas.append(f"     URL: {url}")
        if score is not None:
            lineas.append(f"     Relevancia: {float(score):.3f}")
        lineas.append(f"     Extracto: {contenido}")

    return "\n".join(lineas)


def buscar_web(consulta: str) -> str:
    """
    Ejecuta una búsqueda web con Tavily y devuelve hallazgos formateados.

    Args:
        consulta: Texto de búsqueda derivado de la subtarea del investigador.

    Returns:
        Texto estructurado listo para almacenar en `contexto_acumulado`.
    """
    if not consulta.strip():
        raise ValueError("La consulta de búsqueda no puede estar vacía.")

    herramienta = _obtener_herramienta_busqueda()
    resultados, metadata = herramienta._run(consulta.strip())

    if isinstance(resultados, str):
        return f"[Investigador — Tavily] Error en búsqueda: {resultados}"

    respuesta = metadata.get("answer") if metadata else None
    return _formatear_hallazgos(consulta.strip(), resultados, respuesta)
