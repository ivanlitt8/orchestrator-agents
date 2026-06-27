import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from state import AgenteEspecialista, EstadoSubtarea, State, Subtarea

load_dotenv()

SUPERVISOR_MODEL = "gemini-3-flash-preview"

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
6. Responde únicamente mediante el esquema estructurado solicitado; no incluyas texto libre \
fuera del JSON.
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


def generar_plan(solicitud: str) -> PlanSupervisor:
    """Genera el plan estructurado del Supervisor usando Gemini."""
    if not solicitud.strip():
        raise ValueError("La solicitud no puede estar vacía.")

    planificador = _obtener_planificador()
    resultado = planificador.invoke(
        [
            SystemMessage(content=PROMPT_SISTEMA),
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
    """Nodo Supervisor: desglosa la solicitud en un plan estructurado validado."""
    plan_estructurado = generar_plan(state.solicitud)
    subtareas = _mapear_plan_a_subtareas(plan_estructurado)

    return {
        "plan": subtareas,
        "contexto_acumulado": [plan_estructurado.analisis],
    }
