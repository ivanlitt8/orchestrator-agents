import os
import sys
import uuid
from typing import Literal

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents.executor import nodo_ejecutor
from agents.memory import nodo_consolidacion_memoria
from agents.researcher import nodo_investigador
from agents.reviewer import detectar_necesidad_busqueda_humana, nodo_revision_humana, nodo_revisor
from agents.supervisor import nodo_supervisor
from state import (
    AgenteEspecialista,
    State,
    primera_subtarea_pendiente,
    reabrir_subtarea_ejecutor,
)

load_dotenv()

RECURSION_LIMIT = 20
DEFAULT_THREAD_ID = "orquestador-hitl"
MAX_INTENTOS_EJECUCION = 2
MAX_INTENTOS_BUSQUEDA = 2

MENSAJE_LIMITE_REINTENTOS = (
    "⚠️ ALERTA: Se ha alcanzado el límite máximo de reintentos automáticos del sistema. "
    "El informe actual podría requerir intervención o cambio de directivas manuales."
)

DestinoEspecialista = Literal["investigador", "ejecutor", "revisor", "__end__"]
DestinoRevisor = Literal["ejecutor", "revision_humana", "investigador"]
DestinoHitl = Literal["ejecutor", "consolidacion_memoria", "investigador"]

RESPUESTAS_APROBACION = {"sí", "si", "yes", "y", "s"}


def _como_state(state: State | dict) -> State:
    if isinstance(state, State):
        return state
    return State.model_validate(state)


def enrutar_siguiente_especialista(state: State | dict) -> DestinoEspecialista:
    """Dirige el flujo hacia el especialista con la siguiente subtarea pendiente."""
    estado = _como_state(state)
    subtarea = primera_subtarea_pendiente(estado.plan)
    if subtarea is None:
        return "revisor"

    if subtarea.agente_asignado == AgenteEspecialista.INVESTIGADOR:
        return "investigador"
    if subtarea.agente_asignado == AgenteEspecialista.EJECUTOR:
        return "ejecutor"

    return "revisor"


def _limites_reintentos_alcanzados(estado: State) -> bool:
    """True si algún contador de reintentos automáticos alcanzó su tope."""
    return (
        estado.intentos_ejecucion >= MAX_INTENTOS_EJECUCION
        or estado.intentos_busqueda >= MAX_INTENTOS_BUSQUEDA
    )


def _destino_tras_rechazo(estado: State) -> Literal["investigador", "ejecutor"]:
    """Bifurca hacia investigador si se requiere nueva búsqueda web."""
    if estado.necesita_nueva_busqueda and estado.nueva_query_busqueda.strip():
        return "investigador"
    return "ejecutor"


def enrutar_despues_revisor(state: State | dict) -> DestinoRevisor:
    """Tras revisión técnica: HITL si aprueba o si se agotaron reintentos automáticos."""
    estado = _como_state(state)
    if estado.aprobado_tecnicamente:
        return "revision_humana"
    if _limites_reintentos_alcanzados(estado):
        return "revision_humana"
    return _destino_tras_rechazo(estado)


def enrutar_despues_revision_humana(state: State | dict) -> DestinoHitl:
    """Tras revisión humana: consolida memoria o corrige vía investigador/ejecutor."""
    estado = _como_state(state)
    if estado.aprobado_por_humano:
        return "consolidacion_memoria"
    return _destino_tras_rechazo(estado)


def _entorno_langgraph_api() -> bool:
    """True si LangGraph API/Studio gestiona persistencia (sin checkpointer manual)."""
    if (
        os.getenv("LANGGRAPH_API_KEY")
        or os.getenv("LANGGRAPH_ENDPOINT")
        or os.getenv("UNDER_LANGGRAPH_CLI") == "true"
    ):
        return True
    # langgraph dev importa main.py tras cargar langgraph_api (sin env vars anteriores)
    return any(name.startswith("langgraph_api") for name in sys.modules)


def build_graph():
    builder = StateGraph(state_schema=State)

    builder.add_node("supervisor", nodo_supervisor)
    builder.add_node("investigador", nodo_investigador)
    builder.add_node("ejecutor", nodo_ejecutor)
    builder.add_node("revisor", nodo_revisor)
    builder.add_node("revision_humana", nodo_revision_humana)
    builder.add_node("consolidacion_memoria", nodo_consolidacion_memoria)

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
    builder.add_conditional_edges(
        "revisor",
        enrutar_despues_revisor,
        {
            "ejecutor": "ejecutor",
            "revision_humana": "revision_humana",
            "investigador": "investigador",
        },
    )
    builder.add_conditional_edges(
        "revision_humana",
        enrutar_despues_revision_humana,
        {
            "ejecutor": "ejecutor",
            "consolidacion_memoria": "consolidacion_memoria",
            "investigador": "investigador",
        },
    )
    builder.add_edge("consolidacion_memoria", END)

    if _entorno_langgraph_api():
        return builder.compile(interrupt_before=["revision_humana"])

    checkpointer = MemorySaver()
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["revision_humana"],
    )


# Exportación para LangGraph CLI / Studio (`langgraph dev`)
graph = build_graph()


def crear_config(thread_id: str) -> dict:
    """Configuración LangGraph para un hilo de ejecución."""
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": RECURSION_LIMIT,
    }


def _crear_config(thread_id: str | None = None) -> dict:
    return crear_config(thread_id or DEFAULT_THREAD_ID)


def thread_existe_en_checkpointer(app, config: dict) -> bool:
    """True si el hilo tiene al menos un checkpoint persistido."""
    historial = list(app.get_state_history(config, limit=1))
    return len(historial) > 0


def esta_interrumpido_antes_hitl(app, config: dict) -> bool:
    snapshot = app.get_state(config)
    return bool(snapshot.next) and "revision_humana" in snapshot.next


def construir_actualizacion_feedback_humano(valores: dict, feedback: str) -> dict:
    """Prepara el patch de estado para revision_humana según el feedback recibido."""
    respuesta = feedback.strip()
    if respuesta.lower() in RESPUESTAS_APROBACION:
        return {
            "aprobado_por_humano": True,
            "feedback_revisor": "",
            "necesita_nueva_busqueda": False,
            "nueva_query_busqueda": "",
        }

    plan_actual = valores.get("plan", [])
    necesita_busqueda, query_busqueda = detectar_necesidad_busqueda_humana(
        respuesta,
        solicitud=valores.get("solicitud", ""),
        contexto_acumulado=valores.get("contexto_acumulado", []),
    )
    return {
        "aprobado_por_humano": False,
        "feedback_revisor": respuesta,
        "plan": reabrir_subtarea_ejecutor(plan_actual),
        "necesita_nueva_busqueda": necesita_busqueda,
        "nueva_query_busqueda": query_busqueda if necesita_busqueda else "",
    }


def _ejecutar_hasta_interrupcion(app, entrada: dict | None, config: dict) -> None:
    for _ in app.stream(entrada, config):
        pass


def _esta_interrumpido_antes_hitl(app, config: dict) -> bool:
    return esta_interrumpido_antes_hitl(app, config)


def _solicitar_revision_humana(app, config: dict) -> bool:
    """Solicita aprobación humana. Retorna True si el informe fue aprobado."""
    estado = app.get_state(config)
    valores = estado.values
    estado_actual = _como_state(valores)

    print("\n--- Revisión humana (HITL) ---")
    if (
        not estado_actual.aprobado_tecnicamente
        and _limites_reintentos_alcanzados(estado_actual)
    ):
        print(MENSAJE_LIMITE_REINTENTOS)
    print(f"Score técnico: {valores.get('score_calidad', 0)}/5")
    print(f"Aprobado técnicamente: {valores.get('aprobado_tecnicamente', False)}")
    print(
        f"Intentos automáticos — ejecutor: {valores.get('intentos_ejecucion', 0)}/"
        f"{MAX_INTENTOS_EJECUCION}, investigador: {valores.get('intentos_busqueda', 0)}/"
        f"{MAX_INTENTOS_BUSQUEDA}"
    )
    print(f"\nresultado_final:\n{valores.get('resultado_final', '')}\n")
    print('Escribe "sí" para aprobar el informe o indica correcciones/feedback.')

    respuesta = input("Tu decisión: ").strip()
    actualizacion = construir_actualizacion_feedback_humano(valores, respuesta)
    app.update_state(config, actualizacion, as_node="revision_humana")
    return actualizacion["aprobado_por_humano"]


def ejecutar(solicitud: str, thread_id: str | None = None) -> dict:
    """Ejecuta el orquestador con revisión técnica automática y ciclo HITL."""
    app = build_graph()
    config = _crear_config(thread_id)

    entrada_inicial = {
        "solicitud": solicitud,
        "intentos_ejecucion": 0,
        "intentos_busqueda": 0,
    }
    _ejecutar_hasta_interrupcion(app, entrada_inicial, config)

    while True:
        if not _esta_interrumpido_antes_hitl(app, config):
            break

        aprobado = _solicitar_revision_humana(app, config)
        _ejecutar_hasta_interrupcion(app, None, config)

        if aprobado:
            break

        if not _esta_interrumpido_antes_hitl(app, config):
            break

    return app.get_state(config).values


def _configurar_salida_consola() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


if __name__ == "__main__":
    _configurar_salida_consola()

    estado_final = ejecutar(
        "¿Cuál es el panorama actual y locales líderes del mercado de hamburgueserías smash en la ciudad de La Plata para este año 2026?",
        thread_id=str(uuid.uuid4()),
    )

    print("\n--- Estado final del orquestador ---")
    print(f"solicitud: {estado_final.get('solicitud', '')}")
    print(f"score_calidad: {estado_final.get('score_calidad', 0)}/5")
    print(f"aprobado_tecnicamente: {estado_final.get('aprobado_tecnicamente', False)}")
    print(f"aprobado_por_humano: {estado_final.get('aprobado_por_humano', False)}")
    print(f"criterios_incumplidos: {estado_final.get('criterios_incumplidos', [])}")
    print(f"feedback_revisor: {estado_final.get('feedback_revisor', '')}")
    print(f"memorias_recuperadas: {len(estado_final.get('memorias_recuperadas', []))}")
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
