from typing import Literal

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from agents.executor import nodo_ejecutor
from agents.researcher import nodo_investigador
from agents.reviewer import nodo_revisor
from agents.supervisor import nodo_supervisor
from state import AgenteEspecialista, State, primera_subtarea_pendiente

load_dotenv()

RECURSION_LIMIT = 20

DestinoEspecialista = Literal["investigador", "ejecutor", "revisor", "__end__"]


def enrutar_siguiente_especialista(state: State) -> DestinoEspecialista:
    """Dirige el flujo hacia el especialista con la siguiente subtarea pendiente."""
    subtarea = primera_subtarea_pendiente(state.plan)
    if subtarea is None:
        return "revisor"

    if subtarea.agente_asignado == AgenteEspecialista.INVESTIGADOR:
        return "investigador"
    if subtarea.agente_asignado == AgenteEspecialista.EJECUTOR:
        return "ejecutor"

    return "revisor"


def build_graph():
    builder = StateGraph(state_schema=State)

    builder.add_node("supervisor", nodo_supervisor)
    builder.add_node("investigador", nodo_investigador)
    builder.add_node("ejecutor", nodo_ejecutor)
    builder.add_node("revisor", nodo_revisor)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        enrutar_siguiente_especialista,
        {
            "investigador": "investigador",
            "ejecutor": "ejecutor",
            "revisor": "revisor",
        },
    )
    builder.add_conditional_edges(
        "investigador",
        enrutar_siguiente_especialista,
        {
            "investigador": "investigador",
            "ejecutor": "ejecutor",
            "revisor": "revisor",
        },
    )
    builder.add_conditional_edges(
        "ejecutor",
        enrutar_siguiente_especialista,
        {
            "investigador": "investigador",
            "ejecutor": "ejecutor",
            "revisor": "revisor",
        },
    )
    builder.add_edge("revisor", END)

    return builder.compile()


def ejecutar(solicitud: str) -> dict:
    graph = build_graph()
    return graph.invoke(
        {"solicitud": solicitud},
        config={"recursion_limit": RECURSION_LIMIT},
    )


if __name__ == "__main__":
    estado_final = ejecutar("¿Cuáles son las tendencias en IA para 2026?")

    print("--- Estado final del orquestador ---")
    print(f"solicitud: {estado_final.get('solicitud', '')}")
    print(f"aprobado_por_humano: {estado_final.get('aprobado_por_humano', False)}")
    print(f"resultado_final:\n{estado_final.get('resultado_final', '')}")
    print("\nplan:")
    for subtarea in estado_final.get("plan", []):
        estado = subtarea.estado.value if hasattr(subtarea, "estado") else subtarea["estado"]
        subtarea_id = subtarea.id if hasattr(subtarea, "id") else subtarea["id"]
        descripcion = (
            subtarea.descripcion if hasattr(subtarea, "descripcion") else subtarea["descripcion"]
        )
        print(f"  - [{estado}] {subtarea_id}: {descripcion}")
    print("\ncontexto_acumulado:")
    for fragmento in estado_final.get("contexto_acumulado", []):
        print(f"  - {fragmento}")
