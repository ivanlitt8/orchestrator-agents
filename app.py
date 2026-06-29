import asyncio
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from main import (
    build_graph,
    construir_actualizacion_feedback_humano,
    crear_config,
    esta_interrumpido_antes_hitl,
    thread_existe_en_checkpointer,
)

load_dotenv()

app = FastAPI(
    title="Orchestrator Agents API",
    description="API asíncrona para el orquestador multi-agente con HITL vía LangGraph.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

graph = build_graph()

NODOS_PIPELINE = frozenset({
    "supervisor",
    "investigador",
    "ejecutor",
    "revisor",
    "revision_humana",
})

# Hilos registrados cuyo grafo aún no escribió el primer checkpoint.
_hilos_sin_checkpoint: dict[str, dict[str, Any]] = {}


class CrearTareaRequest(BaseModel):
    solicitud: str = Field(min_length=1, description="Solicitud del usuario")


class ResponderTareaRequest(BaseModel):
    feedback: str = Field(min_length=1, description='Feedback humano o "sí" para aprobar')


class EstadoTareaResponse(BaseModel):
    thread_id: str
    esperando_feedback_humano: bool
    finalizado: bool
    solicitud: str = ""
    resultado_final: str = ""
    score_calidad: int = 0
    aprobado_tecnicamente: bool = False
    aprobado_por_humano: bool = False
    intentos_ejecucion: int = 0
    intentos_busqueda: int = 0
    proximos_nodos: list[str] = Field(default_factory=list)
    estado: dict[str, Any] = Field(default_factory=dict)


def _serializar_valor(valor: Any) -> Any:
    if hasattr(valor, "model_dump"):
        return valor.model_dump(mode="json")
    if isinstance(valor, list):
        return [_serializar_valor(item) for item in valor]
    if isinstance(valor, dict):
        return {clave: _serializar_valor(item) for clave, item in valor.items()}
    return valor


def _nodo_desde_metadata(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None

    source = metadata.get("source")
    if isinstance(source, str) and source in NODOS_PIPELINE:
        return source

    writes = metadata.get("writes")
    if isinstance(writes, dict):
        for clave in reversed(list(writes)):
            if clave in NODOS_PIPELINE:
                return clave

    return None


def _resolver_nodos_para_frontend(snapshot, config: dict) -> list[str]:
    """Nodo en ejecución pendiente o último del historial, apto para el mapeador del frontend."""
    if esta_interrumpido_antes_hitl(graph, config):
        return ["revision_humana"]

    proximos = list(snapshot.next) if snapshot.next else []
    if proximos:
        return proximos

    historial = list(graph.get_state_history(config, limit=10))
    for entrada in historial:
        nodo = _nodo_desde_metadata(entrada.metadata)
        if nodo:
            return [nodo]

    return []


def _construir_respuesta_pendiente(thread_id: str) -> EstadoTareaResponse:
    datos = _hilos_sin_checkpoint[thread_id]
    entrada = datos["entrada"]
    return EstadoTareaResponse(
        thread_id=thread_id,
        esperando_feedback_humano=False,
        finalizado=False,
        solicitud=str(datos.get("solicitud", "")),
        proximos_nodos=["supervisor"],
        estado=_serializar_valor(entrada),
    )


def _obtener_snapshot_o_404(thread_id: str):
    config = crear_config(thread_id)
    if not thread_existe_en_checkpointer(graph, config):
        if thread_id in _hilos_sin_checkpoint:
            return None, config
        raise HTTPException(status_code=404, detail=f"thread_id '{thread_id}' no encontrado.")
    return graph.get_state(config), config


def _construir_respuesta_estado(thread_id: str, snapshot) -> EstadoTareaResponse:
    config = crear_config(thread_id)
    valores = snapshot.values or {}
    proximos_raw = list(snapshot.next) if snapshot.next else []
    esperando_hitl = esta_interrumpido_antes_hitl(graph, config)
    nodos_visibles = _resolver_nodos_para_frontend(snapshot, config)

    return EstadoTareaResponse(
        thread_id=thread_id,
        esperando_feedback_humano=esperando_hitl,
        finalizado=not proximos_raw and not esperando_hitl,
        solicitud=str(valores.get("solicitud", "")),
        resultado_final=str(valores.get("resultado_final", "")),
        score_calidad=int(valores.get("score_calidad", 0) or 0),
        aprobado_tecnicamente=bool(valores.get("aprobado_tecnicamente", False)),
        aprobado_por_humano=bool(valores.get("aprobado_por_humano", False)),
        intentos_ejecucion=int(valores.get("intentos_ejecucion", 0) or 0),
        intentos_busqueda=int(valores.get("intentos_busqueda", 0) or 0),
        proximos_nodos=nodos_visibles,
        estado=_serializar_valor(valores),
    )


async def _ejecutar_grafo_async(
    thread_id: str,
    entrada: dict | None,
    config: dict,
) -> None:
    """Ejecuta el grafo hasta interrupción HITL o finalización, con logs en consola."""
    print(f"[{thread_id}] >> Iniciando ejecucion del grafo...")
    try:
        async for evento in graph.astream(entrada, config, stream_mode="updates"):
            for nodo in evento:
                print(f"[{thread_id}] >> Nodo ejecutado: {nodo}")
        print(f"[{thread_id}] -- Ejecucion pausada o finalizada.")
    finally:
        _hilos_sin_checkpoint.pop(thread_id, None)


@app.post("/api/tareas", response_model=EstadoTareaResponse, status_code=201)
async def crear_tarea(
    payload: CrearTareaRequest,
    background_tasks: BackgroundTasks,
) -> EstadoTareaResponse:
    thread_id = str(uuid.uuid4())
    config = crear_config(thread_id)
    solicitud = payload.solicitud.strip()
    entrada_inicial = {
        "solicitud": solicitud,
        "intentos_ejecucion": 0,
        "intentos_busqueda": 0,
    }

    _hilos_sin_checkpoint[thread_id] = {
        "solicitud": solicitud,
        "entrada": entrada_inicial,
    }
    background_tasks.add_task(_ejecutar_grafo_async, thread_id, entrada_inicial, config)

    return EstadoTareaResponse(
        thread_id=thread_id,
        esperando_feedback_humano=False,
        finalizado=False,
        solicitud=solicitud,
        proximos_nodos=["supervisor"],
        estado=_serializar_valor(entrada_inicial),
    )


@app.get("/api/tareas/{thread_id}", response_model=EstadoTareaResponse)
async def obtener_tarea(thread_id: str) -> EstadoTareaResponse:
    snapshot, _ = _obtener_snapshot_o_404(thread_id)
    if snapshot is None:
        return _construir_respuesta_pendiente(thread_id)
    return _construir_respuesta_estado(thread_id, snapshot)


@app.post("/api/tareas/{thread_id}/responder", response_model=EstadoTareaResponse)
async def responder_tarea(
    thread_id: str,
    payload: ResponderTareaRequest,
    background_tasks: BackgroundTasks,
) -> EstadoTareaResponse:
    snapshot, config = _obtener_snapshot_o_404(thread_id)
    if snapshot is None:
        raise HTTPException(
            status_code=409,
            detail="El hilo aún no está listo para recibir feedback.",
        )

    if not esta_interrumpido_antes_hitl(graph, config):
        raise HTTPException(
            status_code=409,
            detail="El hilo no está esperando feedback humano en revision_humana.",
        )

    valores = snapshot.values or {}
    actualizacion = await asyncio.to_thread(
        construir_actualizacion_feedback_humano,
        valores,
        payload.feedback,
    )
    graph.update_state(config, actualizacion, as_node="revision_humana")

    background_tasks.add_task(_ejecutar_grafo_async, thread_id, None, config)

    snapshot_actualizado = graph.get_state(config)
    return _construir_respuesta_estado(thread_id, snapshot_actualizado)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
