from state import EstadoSubtarea, State


def nodo_revisor(state: State) -> dict:
    """Stub del Reviewer: valida que el plan esté completo antes de finalizar."""
    subtareas_pendientes = [
        t for t in state.plan if t.estado != EstadoSubtarea.COMPLETADA
    ]
    if subtareas_pendientes or not state.resultado_final.strip():
        return {
            "contexto_acumulado": state.contexto_acumulado
            + ["[Revisor] El resultado aún no cumple los requisitos del plan."]
        }

    return {
        "contexto_acumulado": state.contexto_acumulado
        + ["[Revisor] Resultado aprobado. Listo para revisión humana."]
    }
