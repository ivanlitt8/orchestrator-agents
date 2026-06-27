from state import AgenteEspecialista, State, marcar_subtarea_completada


def nodo_ejecutor(state: State) -> dict:
    """Stub del Writer/Developer: consolida contexto en resultado final."""
    contexto = "\n".join(state.contexto_acumulado)
    resultado = (
        f"[Ejecutor] Respuesta consolidada para '{state.solicitud}':\n{contexto}"
    )
    return {
        "resultado_final": resultado,
        "plan": marcar_subtarea_completada(
            state.plan,
            AgenteEspecialista.EJECUTOR,
            resultado=resultado,
        ),
    }
