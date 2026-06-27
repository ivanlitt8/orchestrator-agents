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
    aprobado_por_humano: bool = Field(
        default=False,
        description="Control de flujo para human-in-the-loop",
    )
