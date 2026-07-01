from datetime import date
from functools import lru_cache

from agents.llm import STRUCTURED_OUTPUT_METHOD, crear_chat_groq
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from state import AgenteEspecialista, ExtraccionMetadatosMemoria, State
from tools.vector_db import guardar_memoria

load_dotenv()

MAX_CARACTERES_RESULTADO_EXTRACTOR = 3000

PROMPT_SISTEMA_METADATOS = """\
Eres un clasificador de metadatos para una memoria vectorial de informes exitosos. \
Analiza la solicitud del usuario y el informe final entregado, y extrae metadatos \
útiles para indexación y filtrado futuro.

## Campos a generar
1. **sector**: categoría temática principal (1-3 palabras). Ejemplos: Gastronomía, \
Tecnología, Finanzas, Turismo, Salud, Educación.
2. **tipo_tarea**: naturaleza de la entrega (2-4 palabras). Ejemplos: Estudio de Mercado, \
Análisis Técnico, Guía Comercial, Informe Comparativo, Resumen Ejecutivo.
3. **tags**: 3-8 etiquetas concisas separadas conceptualmente (ubicaciones, productos, \
temas, entidades). Ejemplo: ["La Plata", "smash burgers", "precios", "competencia"].

## Reglas
- Basa los metadatos en el contenido real del informe, no en suposiciones genéricas.
- Usa el mismo idioma que la solicitud del usuario.
- Las tags deben ser específicas y buscables (nombres propios, ciudades, productos).
- Responde únicamente en formato JSON válido, siguiendo estrictamente el esquema estructurado solicitado.
"""


@lru_cache(maxsize=1)
def _obtener_extractor_metadatos():
    llm = crear_chat_groq(temperature=0.0)
    return llm.with_structured_output(
        ExtraccionMetadatosMemoria,
        method=STRUCTURED_OUTPUT_METHOD,
    )


def _extraer_enfoque_exitoso(plan: list) -> str:
    if not plan:
        return "Sin plan registrado."

    fragmentos = []
    for subtarea in plan:
        agente = (
            subtarea.agente_asignado.value
            if hasattr(subtarea.agente_asignado, "value")
            else str(subtarea.agente_asignado)
        )
        fragmentos.append(f"{agente}: {subtarea.descripcion}")
    return " | ".join(fragmentos)


def _agentes_utilizados(plan: list) -> str:
    agentes = set()
    for subtarea in plan:
        if hasattr(subtarea, "agente_asignado"):
            agentes.add(subtarea.agente_asignado.value)
    return ", ".join(sorted(agentes)) if agentes else "desconocido"


def _construir_mensaje_extraccion_metadatos(solicitud: str, resultado_final: str) -> str:
    informe = resultado_final.strip()
    if len(informe) > MAX_CARACTERES_RESULTADO_EXTRACTOR:
        informe = informe[:MAX_CARACTERES_RESULTADO_EXTRACTOR].rstrip() + "\n... (truncado)"

    return (
        f"## Solicitud del usuario\n{solicitud.strip()}\n\n"
        f"## Informe final entregado\n{informe}"
    )


def extraer_metadatos_memoria(solicitud: str, resultado_final: str) -> ExtraccionMetadatosMemoria:
    """Infiere sector, tipo_tarea y tags con salida estructurada."""
    extractor = _obtener_extractor_metadatos()
    resultado = extractor.invoke(
        [
            SystemMessage(content=PROMPT_SISTEMA_METADATOS),
            HumanMessage(
                content=_construir_mensaje_extraccion_metadatos(solicitud, resultado_final)
            ),
        ]
    )
    return (
        resultado
        if isinstance(resultado, ExtraccionMetadatosMemoria)
        else ExtraccionMetadatosMemoria.model_validate(resultado)
    )


def _construir_metadatos_indexacion(
    state: State,
    extraccion: ExtraccionMetadatosMemoria,
) -> dict[str, str | list[str] | bool]:
    tags_limpios = [tag.strip() for tag in extraccion.tags if tag.strip()]
    return {
        "fecha": date.today().isoformat(),
        "sector": extraccion.sector.strip(),
        "tipo_tarea": extraccion.tipo_tarea.strip(),
        "tags": tags_limpios,
        "agentes_utilizados": _agentes_utilizados(state.plan),
        "aprobado_por_humano": True,
    }


def nodo_consolidacion_memoria(state: State) -> dict:
    """Persiste la ejecución aprobada en la memoria vectorial con metadatos enriquecidos."""
    if not state.aprobado_por_humano or not state.resultado_final.strip():
        return {}

    extraccion = extraer_metadatos_memoria(state.solicitud, state.resultado_final)
    metadatos = _construir_metadatos_indexacion(state, extraccion)

    memoria_id = guardar_memoria(
        tarea_original=state.solicitud,
        enfoque_exitoso=_extraer_enfoque_exitoso(state.plan),
        resultado_resumido=state.resultado_final,
        metadatos=metadatos,
    )

    tags_texto = metadatos["tags"]
    if isinstance(tags_texto, list):
        tags_texto = ", ".join(tags_texto)

    return {
        "contexto_acumulado": state.contexto_acumulado
        + [
            f"[Memoria] Ejecución exitosa indexada (id: {memoria_id}). "
            f"Sector: {metadatos['sector']} | Tipo: {metadatos['tipo_tarea']} | "
            f"Tags: {tags_texto} | Fecha: {metadatos['fecha']}."
        ],
    }
