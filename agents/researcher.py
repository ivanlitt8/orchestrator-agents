from state import (
    AgenteEspecialista,
    State,
    marcar_subtarea_completada,
    primera_subtarea_pendiente_por_agente,
)
from tools.search import buscar_web


def _construir_consulta(subtarea_descripcion: str, solicitud: str) -> str:
    """Deriva la consulta de Tavily a partir de la subtarea y la solicitud global."""
    return f"{subtarea_descripcion.strip()} | Contexto del usuario: {solicitud.strip()}"


def nodo_investigador(state: State) -> dict:
    """Ejecuta búsqueda web real con Tavily para la subtarea pendiente del investigador."""
    subtarea = primera_subtarea_pendiente_por_agente(
        state.plan,
        AgenteEspecialista.INVESTIGADOR,
    )
    if subtarea is None:
        return {}

    consulta = _construir_consulta(subtarea.descripcion, state.solicitud)
    hallazgo = buscar_web(consulta)

    encabezado = f"[Investigador] Subtarea '{subtarea.id}' completada."
    contexto = f"{encabezado}\n{hallazgo}"

    return {
        "contexto_acumulado": state.contexto_acumulado + [contexto],
        "plan": marcar_subtarea_completada(
            state.plan,
            AgenteEspecialista.INVESTIGADOR,
            resultado=contexto,
        ),
    }
