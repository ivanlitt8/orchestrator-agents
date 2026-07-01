from enum import Enum

from pydantic import BaseModel, Field


class AgenteEspecialista(str, Enum):
    """Agentes especialistas disponibles para ejecutar subtareas."""

    INVESTIGADOR = "investigador"
    EJECUTOR = "ejecutor"


class EstadoSubtarea(str, Enum):
    """Ciclo de vida de una subtarea dentro del plan."""

    PENDIENTE = "pendiente"
    EN_PROGRESO = "en_progreso"
    COMPLETADA = "completada"


class Subtarea(BaseModel):
    """Unidad de trabajo asignable a un especialista."""

    id: str = Field(description="Identificador único de la subtarea")
    descripcion: str = Field(description="Instrucción concreta a ejecutar")
    agente_asignado: AgenteEspecialista = Field(
        description="Especialista responsable de la subtarea"
    )
    estado: EstadoSubtarea = Field(
        default=EstadoSubtarea.PENDIENTE,
        description="Estado actual de ejecución",
    )
    resultado: str = Field(
        default="",
        description="Salida generada al completar la subtarea",
    )


class EvaluacionRevisor(BaseModel):
    """Resultado estructurado de la revisión técnica automática."""

    score_calidad: int = Field(
        ge=1,
        le=5,
        description="Calificación global de calidad del informe (1=muy deficiente, 5=excelente)",
    )
    criterios_incumplidos: list[str] = Field(
        default_factory=list,
        description="Lista de criterios que no se cumplieron",
    )
    aprobado_tecnicamente: bool = Field(
        description="True solo si el informe supera la revisión técnica automática"
    )
    feedback_interno: str = Field(
        description="Feedback detallado para corrección del ejecutor si fue rechazado"
    )
    necesita_nueva_busqueda: bool = Field(
        default=False,
        description="True si faltan datos externos que requieren nueva búsqueda web",
    )
    nueva_query_busqueda: str = Field(
        default="",
        description="Consulta exacta que el Investigador debe ejecutar en Tavily",
    )


class ExtraccionBusquedaFeedbackHumano(BaseModel):
    """Resultado del clasificador LLM sobre feedback humano en HITL."""

    necesita_nueva_busqueda: bool = Field(
        description=(
            "True si el humano pide datos nuevos/frescos del mundo real; "
            "False si solo pide correcciones de redacción o formato"
        )
    )
    nueva_query_busqueda: str = Field(
        default="",
        description=(
            "Query concisa optimizada para Tavily cuando necesita_nueva_busqueda es True; "
            "vacío en caso contrario"
        ),
    )


class MemoriaRecuperada(BaseModel):
    """Experiencia pasada recuperada de la memoria vectorial."""

    tarea_original: str = Field(description="Solicitud original de la ejecución pasada")
    enfoque_exitoso: str = Field(description="Estrategia y agentes que funcionaron")
    resultado_resumido: str = Field(
        description="Resumen del resultado entregado con éxito"
    )
    similitud: float | None = Field(
        default=None,
        description="Score de similitud semántica con la solicitud actual",
    )
    sector: str = Field(default="", description="Sector inferido al indexar la memoria")
    tipo_tarea: str = Field(default="", description="Tipo de tarea inferido al indexar")
    tags: str = Field(default="", description="Tags separados por comas")
    fecha: str = Field(default="", description="Fecha ISO de indexación (YYYY-MM-DD)")


class ExtraccionMetadatosMemoria(BaseModel):
    """Metadatos inferidos por LLM al consolidar una ejecución exitosa."""

    sector: str = Field(
        description='Sector temático principal (ej: "Gastronomía", "Tecnología", "Finanzas")'
    )
    tipo_tarea: str = Field(
        description=(
            'Tipo de entrega (ej: "Estudio de Mercado", "Análisis Técnico", '
            '"Guía Comercial")'
        )
    )
    tags: list[str] = Field(
        min_length=1,
        max_length=8,
        description="Etiquetas concisas: ubicaciones, productos, temas clave",
    )


class PrediccionMetadatosSolicitud(BaseModel):
    """Clasificación predictiva de la solicitud antes de recuperar memorias."""

    sector_predicho: str = Field(
        description='Sector temático esperado (ej: "Tecnología", "Gastronomía", "Finanzas")'
    )
    tipo_tarea_predicho: str = Field(
        description=(
            'Tipo de entrega esperado (ej: "Análisis Técnico", "Estudio de Mercado", '
            '"Guía Comercial")'
        )
    )


def marcar_subtarea_completada(
    plan: list["Subtarea"],
    agente: AgenteEspecialista,
    *,
    resultado: str,
) -> list["Subtarea"]:
    """Marca como completada la primera subtarea pendiente del agente indicado."""
    plan_actualizado: list[Subtarea] = []
    for subtarea in plan:
        if (
            subtarea.agente_asignado == agente
            and subtarea.estado == EstadoSubtarea.PENDIENTE
        ):
            plan_actualizado.append(
                subtarea.model_copy(
                    update={
                        "estado": EstadoSubtarea.COMPLETADA,
                        "resultado": resultado,
                    }
                )
            )
        else:
            plan_actualizado.append(subtarea)
    return plan_actualizado


def primera_subtarea_pendiente(plan: list["Subtarea"]) -> Subtarea | None:
    """Devuelve la primera subtarea pendiente según el orden del plan."""
    for subtarea in plan:
        if subtarea.estado == EstadoSubtarea.PENDIENTE:
            return subtarea
    return None


def primera_subtarea_pendiente_por_agente(
    plan: list["Subtarea"],
    agente: AgenteEspecialista,
) -> Subtarea | None:
    """Devuelve la primera subtarea pendiente asignada a un agente concreto."""
    for subtarea in plan:
        if (
            subtarea.estado == EstadoSubtarea.PENDIENTE
            and subtarea.agente_asignado == agente
        ):
            return subtarea
    return None


def reabrir_subtarea_ejecutor(plan: list["Subtarea"]) -> list["Subtarea"]:
    """Reabre la última subtarea del ejecutor para una nueva iteración HITL."""
    plan_actualizado: list[Subtarea] = []
    indice_objetivo: int | None = None

    for indice in range(len(plan) - 1, -1, -1):
        if plan[indice].agente_asignado == AgenteEspecialista.EJECUTOR:
            indice_objetivo = indice
            break

    if indice_objetivo is None:
        return plan

    for indice, subtarea in enumerate(plan):
        if indice == indice_objetivo:
            plan_actualizado.append(
                subtarea.model_copy(
                    update={
                        "estado": EstadoSubtarea.PENDIENTE,
                        "resultado": "",
                    }
                )
            )
        else:
            plan_actualizado.append(subtarea)

    return plan_actualizado


class UsoTokensNodo(BaseModel):
    """Tokens LLM atribuidos a un nodo del grafo."""

    nodo: str = Field(description="Identificador del nodo LangGraph")
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    llamadas: int = Field(default=0, ge=0)


class MetricasTokens(BaseModel):
    """Uso acumulado de tokens por tarea (persistido en checkpoint)."""

    por_nodo: dict[str, UsoTokensNodo] = Field(default_factory=dict)
    total_prompt_tokens: int = Field(default=0, ge=0)
    total_completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class State(BaseModel):
    """Estado centralizado que viaja entre nodos del grafo LangGraph."""

    solicitud: str = Field(
        default="",
        description="Mensaje original del usuario",
    )
    plan: list[Subtarea] = Field(
        default_factory=list,
        description="Subtareas estructuradas pendientes y completadas",
    )
    contexto_acumulado: list[str] = Field(
        default_factory=list,
        description="Información descubierta por los especialistas",
    )
    resultado_final: str = Field(
        default="",
        description="Respuesta consolidada lista para revisión",
    )
    feedback_revisor: str = Field(
        default="",
        description="Comentarios del revisor humano cuando no aprueba el informe",
    )
    feedback_interno: str = Field(
        default="",
        description="Feedback del revisor técnico automático para corrección del ejecutor",
    )
    score_calidad: int = Field(
        default=0,
        ge=0,
        le=5,
        description="Score de calidad asignado por el revisor técnico (0=sin evaluar)",
    )
    criterios_incumplidos: list[str] = Field(
        default_factory=list,
        description="Criterios técnicos incumplidos detectados por el revisor",
    )
    aprobado_tecnicamente: bool = Field(
        default=False,
        description="Indica si el informe pasó la revisión técnica automática",
    )
    necesita_nueva_busqueda: bool = Field(
        default=False,
        description="Indica si se requiere una búsqueda web adicional antes de re-redactar",
    )
    nueva_query_busqueda: str = Field(
        default="",
        description="Consulta Tavily pendiente para el Investigador",
    )
    memorias_recuperadas: list[MemoriaRecuperada] = Field(
        default_factory=list,
        description="Experiencias pasadas similares recuperadas antes de planificar",
    )
    aprobado_por_humano: bool = Field(
        default=False,
        description="Control de flujo para human-in-the-loop",
    )
    intentos_ejecucion: int = Field(
        default=0,
        ge=0,
        description="Veces que el flujo ha pasado por el nodo Ejecutor en esta tarea",
    )
    intentos_busqueda: int = Field(
        default=0,
        ge=0,
        description="Veces que el flujo ha pasado por el nodo Investigador/Tavily en esta tarea",
    )
    metricas_tokens: MetricasTokens = Field(
        default_factory=MetricasTokens,
        description="Uso acumulado de tokens LLM por nodo del grafo",
    )
