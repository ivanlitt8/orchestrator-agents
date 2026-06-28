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


def _ejecutar_busqueda_adicional(state: State) -> dict:
    """Ejecuta búsqueda Tavily adicional sin borrar contexto previo."""
    consulta = state.nueva_query_busqueda.strip()
    hallazgo = buscar_web(consulta)
    encabezado = f"[Investigador] Búsqueda adicional: {consulta}"
    contexto = f"{encabezado}\n{hallazgo}"

    return {
        "contexto_acumulado": state.contexto_acumulado + [contexto],
        "necesita_nueva_busqueda": False,
        "nueva_query_busqueda": "",
    }


def nodo_investigador(state: State) -> dict:
    """Ejecuta búsqueda web con Tavily (plan o búsqueda adicional por feedback)."""
    contador = {"intentos_busqueda": state.intentos_busqueda + 1}

    if state.necesita_nueva_busqueda and state.nueva_query_busqueda.strip():
        return {**_ejecutar_busqueda_adicional(state), **contador}

    subtarea = primera_subtarea_pendiente_por_agente(
        state.plan,
        AgenteEspecialista.INVESTIGADOR,
    )
    if subtarea is None:
        return contador

    consulta = _construir_consulta(subtarea.descripcion, state.solicitud)
    hallazgo = buscar_web(consulta)

    encabezado = f"[Investigador] Subtarea '{subtarea.id}' completada."
    contexto = f"{encabezado}\n{hallazgo}"

    return {
        **contador,
        "contexto_acumulado": state.contexto_acumulado + [contexto],
        "plan": marcar_subtarea_completada(
            state.plan,
            AgenteEspecialista.INVESTIGADOR,
            resultado=contexto,
        ),
    }
