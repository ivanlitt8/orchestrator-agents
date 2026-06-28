import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from state import (
    AgenteEspecialista,
    EstadoSubtarea,
    MemoriaRecuperada,
    PrediccionMetadatosSolicitud,
    State,
    Subtarea,
)
from tools.vector_db import buscar_memorias_similares

load_dotenv()

SUPERVISOR_MODEL = "gemini-3-flash-preview"
PREDICTOR_METADATOS_MODEL = "gemini-3-flash-preview"

PROMPT_SISTEMA = """\
Eres el Supervisor de un sistema de orquestación multi-agente. Tu única responsabilidad \
es analizar la solicitud del usuario y generar un plan de ejecución estructurado.

## Agentes disponibles
- `investigador`: recopila información externa, investiga fuentes y nutre el contexto.
- `ejecutor`: redacta reportes, consolida hallazgos o genera código según el plan.

## Reglas obligatorias
1. Descompón la solicitud en subtareas concretas, ejecutables y sin ambigüedad.
2. Asigna cada subtarea al agente correcto según su especialidad.
3. Usa prioridades del 1 (más urgente) al 5 (menos urgente) sin repetir números si es posible.
4. Si la solicitud requiere datos externos o investigación, incluye al menos una subtarea \
para `investigador` antes de las de `ejecutor`.
5. El campo `siguiente_agente` debe coincidir con el agente de la subtarea de mayor prioridad \
(menor número).
6. Si se proporciona contexto de ejecuciones pasadas exitosas, úsalo como referencia \
estratégica; no lo copies literalmente si la solicitud actual difiere.
7. Si se indican metadatos predichos (sector/tipo de tarea), alínea el plan con esa clasificación.
8. Responde únicamente mediante el esquema estructurado solicitado; no incluyas texto libre \
fuera del JSON.
"""

PROMPT_SISTEMA_PREDICCION = """\
Eres un clasificador predictivo de solicitudes para un orquestador multi-agente. \
Analiza la solicitud del usuario ANTES de planificar y predice metadatos para filtrar \
memorias de ejecuciones pasadas exitosas.

## Campos a generar
1. **sector_predicho**: sector temático principal (1-3 palabras). Ejemplos: Tecnología, \
Gastronomía, Finanzas, Turismo, Salud.
2. **tipo_tarea_predicho**: naturaleza de la entrega esperada (2-4 palabras). Ejemplos: \
Análisis Técnico, Estudio de Mercado, Guía Comercial, Informe Comparativo.

## Reglas
- Basa la predicción en la intención explícita de la solicitud, no en suposiciones vagas.
- Usa el mismo idioma que la solicitud del usuario.
- Usa categorías consistentes con las que se indexan memorias (nombres propios capitalizados).
- Responde únicamente mediante el esquema estructurado solicitado.
"""


class SubtareaPlanificada(BaseModel):
    """Subtarea generada por el Supervisor antes de mapearse al State."""

    descripcion: str = Field(description="Acción concreta que debe ejecutar el especialista")
    agente_asignado: AgenteEspecialista = Field(
        description="Especialista al que se delega la subtarea"
    )
    prioridad: int = Field(
        ge=1,
        le=5,
        description="Prioridad relativa (1 = más urgente)",
    )


class PlanSupervisor(BaseModel):
    """Esquema de Structured Output obligatorio del Supervisor."""

    analisis: str = Field(
        description="Breve análisis de la solicitud y estrategia de ejecución"
    )
    subtareas: list[SubtareaPlanificada] = Field(
        min_length=1,
        description="Desglose procesable de la solicitud en subtareas",
    )
    siguiente_agente: AgenteEspecialista = Field(
        description="Primer especialista que debe activarse según el plan"
    )


def _obtener_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta la variable de entorno GEMINI_API_KEY. "
            "Configúrala en el archivo .env antes de ejecutar el Supervisor."
        )
    return api_key


@lru_cache(maxsize=1)
def _obtener_planificador():
    """Inicializa ChatGoogleGenerativeAI con salida estructurada (singleton)."""
    llm = ChatGoogleGenerativeAI(
        model=SUPERVISOR_MODEL,
        api_key=_obtener_api_key(),
        temperature=0.2,
    )
    return llm.with_structured_output(PlanSupervisor, method="json_schema")


@lru_cache(maxsize=1)
def _obtener_predictor_metadatos():
    llm = ChatGoogleGenerativeAI(
        model=PREDICTOR_METADATOS_MODEL,
        api_key=_obtener_api_key(),
        temperature=0.0,
    )
    return llm.with_structured_output(PrediccionMetadatosSolicitud, method="json_schema")


def predecir_metadatos_solicitud(solicitud: str) -> PrediccionMetadatosSolicitud:
    """Clasifica sector y tipo de tarea antes de consultar la memoria vectorial."""
    if not solicitud.strip():
        raise ValueError("La solicitud no puede estar vacía.")

    predictor = _obtener_predictor_metadatos()
    resultado = predictor.invoke(
        [
            SystemMessage(content=PROMPT_SISTEMA_PREDICCION),
            HumanMessage(content=f"Solicitud del usuario:\n{solicitud.strip()}"),
        ]
    )
    return (
        resultado
        if isinstance(resultado, PrediccionMetadatosSolicitud)
        else PrediccionMetadatosSolicitud.model_validate(resultado)
    )


def _mapear_resultados_a_memorias(resultados: list[dict]) -> list[MemoriaRecuperada]:
    return [
        MemoriaRecuperada(
            tarea_original=item.get("tarea_original", ""),
            enfoque_exitoso=item.get("enfoque_exitoso", ""),
            resultado_resumido=item.get("resultado_resumido", ""),
            similitud=item.get("similitud"),
            sector=item.get("sector", ""),
            tipo_tarea=item.get("tipo_tarea", ""),
            tags=item.get("tags", ""),
            fecha=item.get("fecha", ""),
        )
        for item in resultados
    ]


def _construir_filtros_estrictos(prediccion: PrediccionMetadatosSolicitud) -> dict[str, str]:
    filtros: dict[str, str] = {}
    sector = prediccion.sector_predicho.strip()
    tipo_tarea = prediccion.tipo_tarea_predicho.strip()
    if sector:
        filtros["sector"] = sector
    if tipo_tarea:
        filtros["tipo_tarea"] = tipo_tarea
    return filtros


def recuperar_memorias_con_fallback(
    solicitud: str,
    prediccion: PrediccionMetadatosSolicitud,
    limite: int = 3,
) -> tuple[list[MemoriaRecuperada], bool]:
    """
    Recupera memorias filtrando por metadatos predichos; si no hay resultados, fallback semántico.

    Returns:
        Tupla (memorias, uso_fallback) donde uso_fallback indica si se omitieron filtros.
    """
    filtros = _construir_filtros_estrictos(prediccion)

    if filtros:
        resultados_filtrados = buscar_memorias_similares(
            solicitud,
            limite=limite,
            filtros=filtros,
        )
        if resultados_filtrados:
            return _mapear_resultados_a_memorias(resultados_filtrados), False

    resultados = buscar_memorias_similares(solicitud, limite=limite)
    uso_fallback = bool(filtros)
    return _mapear_resultados_a_memorias(resultados), uso_fallback


def recuperar_memorias_similares(solicitud: str, limite: int = 3) -> list[MemoriaRecuperada]:
    """Consulta ChromaDB con predicción de metadatos y fallback semántico."""
    prediccion = predecir_metadatos_solicitud(solicitud)
    memorias, _ = recuperar_memorias_con_fallback(solicitud, prediccion, limite=limite)
    return memorias


def _formatear_prediccion_para_prompt(
    prediccion: PrediccionMetadatosSolicitud,
    uso_fallback: bool,
) -> str:
    modo_busqueda = (
        "búsqueda semántica pura (sin filtros por base de datos pequeña o sin coincidencias)"
        if uso_fallback
        else "filtros estrictos por sector y tipo de tarea"
    )
    return (
        "## Clasificación predictiva de la solicitud\n"
        f"- Sector predicho: {prediccion.sector_predicho.strip()}\n"
        f"- Tipo de tarea predicho: {prediccion.tipo_tarea_predicho.strip()}\n"
        f"- Modo de recuperación de memorias: {modo_busqueda}"
    )


def _formatear_memorias_para_prompt(memorias: list[MemoriaRecuperada]) -> str:
    if not memorias:
        return "## Contexto de ejecuciones pasadas exitosas\n(No se recuperaron memorias relevantes.)"

    bloques = ["## Contexto de ejecuciones pasadas exitosas"]
    for indice, memoria in enumerate(memorias, start=1):
        similitud = (
            f"{memoria.similitud:.2f}"
            if memoria.similitud is not None
            else "N/A"
        )
        metadatos = ", ".join(
            parte
            for parte in (
                f"sector={memoria.sector}" if memoria.sector else "",
                f"tipo={memoria.tipo_tarea}" if memoria.tipo_tarea else "",
                f"tags={memoria.tags}" if memoria.tags else "",
                f"fecha={memoria.fecha}" if memoria.fecha else "",
            )
            if parte
        )
        bloques.append(
            f"{indice}. Tarea similar: {memoria.tarea_original}\n"
            f"   Metadatos: {metadatos or 'N/A'}\n"
            f"   Enfoque exitoso: {memoria.enfoque_exitoso}\n"
            f"   Resultado resumido: {memoria.resultado_resumido}\n"
            f"   Similitud: {similitud}"
        )
    return "\n".join(bloques)


def generar_plan(
    solicitud: str,
    memorias: list[MemoriaRecuperada] | None = None,
    prediccion: PrediccionMetadatosSolicitud | None = None,
    uso_fallback: bool = False,
) -> PlanSupervisor:
    """Genera el plan estructurado del Supervisor usando Gemini."""
    if not solicitud.strip():
        raise ValueError("La solicitud no puede estar vacía.")

    memorias = memorias or []
    bloques_contexto = [PROMPT_SISTEMA]
    if prediccion is not None:
        bloques_contexto.append(_formatear_prediccion_para_prompt(prediccion, uso_fallback))
    contexto_memorias = _formatear_memorias_para_prompt(memorias)
    if contexto_memorias:
        bloques_contexto.append(contexto_memorias)
    prompt_sistema = "\n\n".join(bloques_contexto)

    planificador = _obtener_planificador()
    resultado = planificador.invoke(
        [
            SystemMessage(content=prompt_sistema),
            HumanMessage(content=f"Solicitud del usuario:\n{solicitud.strip()}"),
        ]
    )

    plan = (
        resultado
        if isinstance(resultado, PlanSupervisor)
        else PlanSupervisor.model_validate(resultado)
    )

    primera_subtarea = min(plan.subtareas, key=lambda s: s.prioridad)
    if plan.siguiente_agente != primera_subtarea.agente_asignado:
        plan = plan.model_copy(
            update={"siguiente_agente": primera_subtarea.agente_asignado}
        )

    return plan


def _mapear_plan_a_subtareas(plan: PlanSupervisor) -> list[Subtarea]:
    ordenadas = sorted(plan.subtareas, key=lambda s: s.prioridad)
    return [
        Subtarea(
            id=f"tarea-{indice + 1}",
            descripcion=subtarea.descripcion,
            agente_asignado=subtarea.agente_asignado,
            estado=EstadoSubtarea.PENDIENTE,
        )
        for indice, subtarea in enumerate(ordenadas)
    ]


def nodo_supervisor(state: State) -> dict:
    """Recupera memorias similares y desglosa la solicitud en un plan estructurado."""
    prediccion = predecir_metadatos_solicitud(state.solicitud)
    memorias, uso_fallback = recuperar_memorias_con_fallback(state.solicitud, prediccion)
    plan_estructurado = generar_plan(
        state.solicitud,
        memorias=memorias,
        prediccion=prediccion,
        uso_fallback=uso_fallback,
    )
    subtareas = _mapear_plan_a_subtareas(plan_estructurado)

    contexto_inicial = [plan_estructurado.analisis]
    modo_recuperacion = "fallback semántico" if uso_fallback else "filtros estrictos"
    contexto_inicial.append(
        f"[Supervisor] Predicción: sector={prediccion.sector_predicho}, "
        f"tipo={prediccion.tipo_tarea_predicho}. "
        f"Memorias recuperadas: {len(memorias)} ({modo_recuperacion})."
    )

    return {
        "plan": subtareas,
        "memorias_recuperadas": memorias,
        "contexto_acumulado": contexto_inicial,
    }
