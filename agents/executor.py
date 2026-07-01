from functools import lru_cache

from agents.llm import crear_chat_groq
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from state import (
    AgenteEspecialista,
    State,
    marcar_subtarea_completada,
    primera_subtarea_pendiente_por_agente,
)

load_dotenv()


PROMPT_SISTEMA = """\
Eres el Ejecutor de un sistema de orquestación multi-agente. Actúas como redactor \
experto y analista técnico.

## Tu misión
Redactar una respuesta final pulida, profesional, exhaustiva y directamente útil que \
responda la solicitud original del usuario.

## Entradas que recibirás
1. La solicitud original del usuario.
2. La subtarea concreta que debes cumplir (redactar, consolidar, sintetizar, etc.).
3. El contexto acumulado con hallazgos reales de investigación web (Tavily) y análisis previos.

## Reglas obligatorias
1. Lee y utiliza TODO el contexto acumulado; no ignores fuentes ni datos relevantes.
2. Responde de forma directa a la solicitud del usuario; la subtarea guía el enfoque del reporte.
3. Estructura el informe con secciones claras (introducción, hallazgos, conclusiones).
4. Prioriza precisión, claridad y utilidad práctica; evita relleno genérico.
5. Cita o referencia las fuentes del contexto cuando aporten valor (URLs incluidas en el contexto).
6. Escribe en el mismo idioma que la solicitud del usuario.
7. Devuelve únicamente el reporte final, sin meta-comentarios sobre tu proceso interno.
"""

PROMPT_SISTEMA_REVISION = """\
Eres el Ejecutor de un sistema de orquestación multi-agente en modo revisión. Actúas \
como redactor experto encargado de corregir un informe previamente entregado.

## Tu misión
Re-redactar el informe anterior aplicando estrictamente las correcciones solicitadas \
por el revisor (técnico automático o humano), manteniendo calidad profesional.

## Reglas obligatorias
1. Toma como base el informe anterior; no lo descartes por completo salvo que el feedback lo pida.
2. Aplica estrictamente cada punto del feedback; no lo ignores ni lo suavices.
3. Si el feedback es técnico, corrige completitud, rigor (URLs/datos del contexto) y formato Markdown.
4. Conserva información válida del informe anterior que no contradiga las correcciones.
5. Escribe en el mismo idioma que la solicitud del usuario.
6. Devuelve únicamente el informe revisado, sin meta-comentarios sobre tu proceso interno.
"""


@lru_cache(maxsize=1)
def _obtener_llm() -> ChatGroq:
    """Inicializa ChatGroq para redacción (singleton)."""
    return crear_chat_groq(temperature=0.4)


def _extraer_contenido(respuesta) -> str:
    contenido = respuesta.content
    if isinstance(contenido, str):
        return contenido.strip()
    if isinstance(contenido, list):
        fragmentos = [
            bloque.get("text", "") if isinstance(bloque, dict) else str(bloque)
            for bloque in contenido
        ]
        return "\n".join(fragmentos).strip()
    return str(contenido).strip()


def _construir_mensaje_usuario(
    solicitud: str,
    subtarea_descripcion: str,
    contexto_acumulado: list[str],
) -> str:
    contexto = "\n\n---\n\n".join(contexto_acumulado) if contexto_acumulado else "(sin contexto previo)"
    return (
        f"## Solicitud original del usuario\n{solicitud.strip()}\n\n"
        f"## Subtarea asignada al ejecutor\n{subtarea_descripcion.strip()}\n\n"
        f"## Contexto acumulado (investigación y análisis previos)\n{contexto}"
    )


def _construir_mensaje_revision(
    solicitud: str,
    subtarea_descripcion: str,
    contexto_acumulado: list[str],
    informe_anterior: str,
    feedback: str,
    origen_feedback: str,
) -> str:
    contexto = "\n\n---\n\n".join(contexto_acumulado) if contexto_acumulado else "(sin contexto previo)"
    return (
        f"## Solicitud original del usuario\n{solicitud.strip()}\n\n"
        f"## Subtarea asignada al ejecutor\n{subtarea_descripcion.strip()}\n\n"
        f"## Informe anterior a corregir\n{informe_anterior.strip()}\n\n"
        f"## Feedback del {origen_feedback} (aplicar estrictamente)\n{feedback.strip()}\n\n"
        f"## Contexto acumulado de referencia\n{contexto}"
    )


def redactar_informe(
    solicitud: str,
    subtarea_descripcion: str,
    contexto_acumulado: list[str],
) -> str:
    """Genera el reporte consolidado."""
    if not solicitud.strip():
        raise ValueError("La solicitud no puede estar vacía.")

    llm = _obtener_llm()
    respuesta = llm.invoke(
        [
            SystemMessage(content=PROMPT_SISTEMA),
            HumanMessage(
                content=_construir_mensaje_usuario(
                    solicitud,
                    subtarea_descripcion,
                    contexto_acumulado,
                )
            ),
        ]
    )
    return _extraer_contenido(respuesta)


def redactar_informe_con_feedback(
    solicitud: str,
    subtarea_descripcion: str,
    contexto_acumulado: list[str],
    informe_anterior: str,
    feedback: str,
    origen_feedback: str = "revisor humano",
) -> str:
    """Re-redacta el informe anterior aplicando feedback de revisión."""
    if not solicitud.strip():
        raise ValueError("La solicitud no puede estar vacía.")
    if not informe_anterior.strip():
        raise ValueError("No hay informe anterior para revisar.")
    if not feedback.strip():
        raise ValueError("No hay feedback del revisor para aplicar.")

    llm = _obtener_llm()
    respuesta = llm.invoke(
        [
            SystemMessage(content=PROMPT_SISTEMA_REVISION),
            HumanMessage(
                content=_construir_mensaje_revision(
                    solicitud,
                    subtarea_descripcion,
                    contexto_acumulado,
                    informe_anterior,
                    feedback,
                    origen_feedback,
                )
            ),
        ]
    )
    return _extraer_contenido(respuesta)


def nodo_ejecutor(state: State) -> dict:
    """Redacta o revisa el informe final."""
    contador = {"intentos_ejecucion": state.intentos_ejecucion + 1}

    subtarea = primera_subtarea_pendiente_por_agente(
        state.plan,
        AgenteEspecialista.EJECUTOR,
    )

    feedback_humano = state.feedback_revisor.strip()
    feedback_tecnico = state.feedback_interno.strip()
    feedback = feedback_humano or feedback_tecnico
    origen = "revisor humano" if feedback_humano else "revisor técnico"

    if feedback:
        descripcion = (
            subtarea.descripcion
            if subtarea
            else "Revisar y corregir el informe según el feedback recibido."
        )
        informe = redactar_informe_con_feedback(
            solicitud=state.solicitud,
            subtarea_descripcion=descripcion,
            contexto_acumulado=state.contexto_acumulado,
            informe_anterior=state.resultado_final,
            feedback=feedback,
            origen_feedback=origen,
        )
        actualizacion: dict = {
            **contador,
            "resultado_final": informe,
            "feedback_revisor": "",
            "feedback_interno": "",
            "aprobado_por_humano": False,
            "aprobado_tecnicamente": False,
            "necesita_nueva_busqueda": False,
            "nueva_query_busqueda": "",
            "score_calidad": 0,
            "criterios_incumplidos": [],
        }
        if subtarea is not None:
            actualizacion["plan"] = marcar_subtarea_completada(
                state.plan,
                AgenteEspecialista.EJECUTOR,
                resultado=informe,
            )
        return actualizacion

    if subtarea is None:
        return contador

    informe = redactar_informe(
        solicitud=state.solicitud,
        subtarea_descripcion=subtarea.descripcion,
        contexto_acumulado=state.contexto_acumulado,
    )

    return {
        **contador,
        "resultado_final": informe,
        "plan": marcar_subtarea_completada(
            state.plan,
            AgenteEspecialista.EJECUTOR,
            resultado=informe,
        ),
    }
