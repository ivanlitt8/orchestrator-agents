import asyncio
import json
import queue
import threading
import uuid
from collections import defaultdict
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.token_tracking import TokenAccumulator, parsear_metricas_tokens
from main import (
    build_graph,
    construir_actualizacion_feedback_humano,
    crear_config,
    esta_interrumpido_antes_hitl,
    thread_existe_en_checkpointer,
)
from state import MetricasTokens

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

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

# Hilos registrados cuyo grafo aún no escribió el primer checkpoint.
_hilos_sin_checkpoint: dict[str, dict[str, Any]] = {}

# Ejecuciones en cola tras feedback HITL (esperan POST /ejecutar).
_ejecuciones_pendientes: dict[str, dict[str, Any]] = {}

# Hilos con grafo corriendo actualmente.
_runs_activos: set[str] = set()
_run_tasks: dict[str, asyncio.Task[None]] = {}
_ejecutar_lock = asyncio.Lock()

# Suscriptores SSE por thread_id (colas asyncio).
_sse_subscribers: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)
_sse_subscribers_lock = asyncio.Lock()

# Buffer de eventos SSE para reconexiones (sin incluir `connected`).
_sse_event_buffers: dict[str, list[str]] = defaultdict(list)
_SSE_BUFFER_MAX = 512

# Conteo de líneas de contexto_acumulado ya emitidas por hilo (evita duplicados).
_contexto_emitido_count: dict[str, int] = {}


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
    metricas_tokens: MetricasTokens = Field(default_factory=MetricasTokens)
    estado: dict[str, Any] = Field(default_factory=dict)


def _serializar_valor(valor: Any) -> Any:
    if hasattr(valor, "model_dump"):
        return valor.model_dump(mode="json")
    if isinstance(valor, list):
        return [_serializar_valor(item) for item in valor]
    if isinstance(valor, dict):
        return {clave: _serializar_valor(item) for clave, item in valor.items()}
    return valor


def _format_sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _nodo_pipeline_desde_evento(evento: dict[str, Any]) -> str | None:
    """Solo nodos reales del grafo LangGraph (evita cadenas internas del LLM con el mismo nombre)."""
    metadata = evento.get("metadata")
    if not isinstance(metadata, dict):
        return None

    langgraph_node = metadata.get("langgraph_node")
    if isinstance(langgraph_node, str) and langgraph_node in NODOS_PIPELINE:
        return langgraph_node

    return None


def _nodo_desde_evento(evento: dict[str, Any]) -> str | None:
    return _nodo_pipeline_desde_evento(evento)


NODO_EJECUTOR = "ejecutor"


def _evento_en_nodo_ejecutor(evento: dict[str, Any]) -> bool:
    metadata = evento.get("metadata")
    if isinstance(metadata, dict):
        nodo = metadata.get("langgraph_node")
        return nodo == NODO_EJECUTOR
    return False


def _extraer_delta_chat_stream(evento: dict[str, Any]) -> str:
    """Extrae texto incremental de on_chat_model_stream (v2)."""
    data = evento.get("data")
    if not isinstance(data, dict):
        return ""

    chunk = data.get("chunk")
    if chunk is None:
        return ""

    contenido = getattr(chunk, "content", None)
    if contenido is None and isinstance(chunk, dict):
        contenido = chunk.get("content")

    if isinstance(contenido, str):
        return contenido

    if isinstance(contenido, list):
        fragmentos: list[str] = []
        for parte in contenido:
            if isinstance(parte, str):
                fragmentos.append(parte)
            elif isinstance(parte, dict):
                texto = parte.get("text")
                if isinstance(texto, str):
                    fragmentos.append(texto)
            else:
                texto = getattr(parte, "text", None)
                if isinstance(texto, str):
                    fragmentos.append(texto)
        return "".join(fragmentos)

    return ""


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
        metricas_tokens=MetricasTokens(),
        estado=_serializar_valor(entrada),
    )


def _obtener_snapshot_o_404(thread_id: str):
    config = crear_config(thread_id)
    if not thread_existe_en_checkpointer(graph, config):
        if thread_id in _hilos_sin_checkpoint:
            return None, config
        raise HTTPException(status_code=404, detail=f"thread_id '{thread_id}' no encontrado.")
    return graph.get_state(config), config


def _thread_existe(thread_id: str) -> bool:
    if thread_id in _hilos_sin_checkpoint:
        return True
    config = crear_config(thread_id)
    return thread_existe_en_checkpointer(graph, config)


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
        metricas_tokens=parsear_metricas_tokens(valores.get("metricas_tokens")),
        estado=_serializar_valor(valores),
    )


def _metricas_desde_snapshot(config: dict) -> MetricasTokens:
    snapshot = graph.get_state(config)
    valores = snapshot.values or {}
    return parsear_metricas_tokens(valores.get("metricas_tokens"))


def _persistir_metricas_tokens(config: dict, acumulador: TokenAccumulator) -> MetricasTokens:
    actual = acumulador.to_metricas()
    if not actual.por_nodo:
        return _metricas_desde_snapshot(config)

    previo = _metricas_desde_snapshot(config)
    merged = acumulador.merge(previo)
    graph.update_state(config, {"metricas_tokens": merged})
    return merged


def _metricas_tokens_para_sse(config: dict) -> dict[str, Any]:
    return _serializar_valor(_metricas_desde_snapshot(config))


def _contexto_acumulado_desde_estado(config: dict) -> list[str]:
    snapshot = graph.get_state(config)
    valores = snapshot.values or {}
    acumulado = valores.get("contexto_acumulado")
    if not isinstance(acumulado, list):
        return []
    return [str(linea) for linea in acumulado]


def _inicializar_contador_contexto(thread_id: str, config: dict) -> None:
    _contexto_emitido_count[thread_id] = len(_contexto_acumulado_desde_estado(config))


def _emitir_logs_pendientes(thread_id: str, config: dict) -> list[str]:
    acumulado = _contexto_acumulado_desde_estado(config)
    emitido = _contexto_emitido_count.get(thread_id, 0)
    if emitido >= len(acumulado):
        return []

    nuevas = acumulado[emitido:]
    _contexto_emitido_count[thread_id] = len(acumulado)
    return nuevas


async def _register_sse_subscriber(thread_id: str) -> asyncio.Queue[str]:
    cola: asyncio.Queue[str] = asyncio.Queue()
    async with _sse_subscribers_lock:
        _sse_subscribers[thread_id].append(cola)
    return cola


async def _unregister_sse_subscriber(thread_id: str, cola: asyncio.Queue[str]) -> None:
    async with _sse_subscribers_lock:
        suscriptores = _sse_subscribers.get(thread_id, [])
        if cola in suscriptores:
            suscriptores.remove(cola)
        if not suscriptores and thread_id in _sse_subscribers:
            _sse_subscribers.pop(thread_id, None)


async def _broadcast_sse(thread_id: str, mensaje: str) -> None:
    buffer = _sse_event_buffers[thread_id]
    # report_delta es efímero (streaming en vivo); no bufferizar para evitar replay truncado.
    if '"type": "report_delta"' not in mensaje:
        buffer.append(mensaje)
        if len(buffer) > _SSE_BUFFER_MAX:
            del buffer[: len(buffer) - _SSE_BUFFER_MAX]

    async with _sse_subscribers_lock:
        colas = list(_sse_subscribers.get(thread_id, []))

    for cola in colas:
        await cola.put(mensaje)


def _limpiar_buffer_sse(thread_id: str) -> None:
    _sse_event_buffers.pop(thread_id, None)


def _resolver_entrada_pendiente(thread_id: str, config: dict) -> tuple[dict | None, dict]:
    """Obtiene entrada y config para una ejecución pendiente."""
    if thread_id in _hilos_sin_checkpoint:
        datos = _hilos_sin_checkpoint[thread_id]
        entrada = datos.get("entrada")
        return entrada, datos.get("config", config)

    if thread_id in _ejecuciones_pendientes:
        datos = _ejecuciones_pendientes[thread_id]
        return datos.get("entrada"), datos.get("config", config)

    raise HTTPException(
        status_code=409,
        detail="No hay ejecución pendiente para este hilo. Conecta el stream antes de ejecutar.",
    )


def _eventos_terminales_desde_snapshot(thread_id: str, config: dict) -> list[str]:
    """Emite hitl/completed si el grafo ya está en un estado terminal."""
    mensajes: list[str] = []

    if esta_interrumpido_antes_hitl(graph, config):
        snapshot = graph.get_state(config)
        valores = snapshot.values or {}
        mensajes.append(
            _format_sse(
                {
                    "type": "hitl",
                    "thread_id": thread_id,
                    "content": str(valores.get("resultado_final", "")),
                    "score_calidad": int(valores.get("score_calidad", 0) or 0),
                    "metricas_tokens": _metricas_tokens_para_sse(config),
                }
            )
        )
        return mensajes

    snapshot = graph.get_state(config)
    proximos = list(snapshot.next) if snapshot.next else []
    if not proximos:
        valores = snapshot.values or {}
        mensajes.append(
            _format_sse(
                {
                    "type": "completed",
                    "thread_id": thread_id,
                    "content": str(valores.get("resultado_final", "")),
                    "metricas_tokens": _metricas_tokens_para_sse(config),
                }
            )
        )

    return mensajes


def _producir_eventos_grafo_en_hilo(
    sync_q: queue.Queue,
    entrada: dict | None,
    config: dict,
) -> None:
    """Ejecuta astream_events en un hilo con su propio event loop (nodos sync no bloquean FastAPI)."""

    async def _correr() -> None:
        try:
            async for evento in graph.astream_events(entrada, config, version="v2"):
                sync_q.put(("event", evento))
        except Exception as exc:
            sync_q.put(("error", exc))
        finally:
            sync_q.put(("done", None))

    asyncio.run(_correr())


async def _iterar_eventos_grafo(
    entrada: dict | None,
    config: dict,
) -> AsyncIterator[dict[str, Any]]:
    """Puente thread-safe: productor en hilo dedicado, consumidor async en el loop de FastAPI."""
    sync_q: queue.Queue = queue.Queue()
    hilo = threading.Thread(
        target=_producir_eventos_grafo_en_hilo,
        args=(sync_q, entrada, config),
        daemon=True,
    )
    hilo.start()

    try:
        while True:
            kind, payload = await asyncio.to_thread(sync_q.get)
            if kind == "done":
                break
            if kind == "error":
                raise payload
            yield payload
            await asyncio.sleep(0)
    finally:
        await asyncio.to_thread(hilo.join, 5)


async def stream_grafo_events(
    thread_id: str,
    entrada: dict | None,
    config: dict,
) -> AsyncIterator[str]:
    """Generador SSE a partir de graph.astream_events (v2)."""
    _inicializar_contador_contexto(thread_id, config)
    yield _format_sse({"type": "run_started", "thread_id": thread_id})

    nodos_abiertos: set[str] = set()
    acumulador_tokens = TokenAccumulator()

    try:
        async for evento in _iterar_eventos_grafo(entrada, config):
            tipo = evento.get("event")
            nodo = _nodo_pipeline_desde_evento(evento)

            if tipo == "on_chat_model_end":
                acumulador_tokens.registrar_desde_evento(evento)

            if tipo == "on_chat_model_stream" and _evento_en_nodo_ejecutor(evento):
                delta = _extraer_delta_chat_stream(evento)
                if delta:
                    yield _format_sse(
                        {
                            "type": "report_delta",
                            "thread_id": thread_id,
                            "delta": delta,
                        }
                    )

            if tipo == "on_chain_start" and nodo and nodo not in nodos_abiertos:
                nodos_abiertos.add(nodo)
                yield _format_sse(
                    {"type": "node_start", "thread_id": thread_id, "node": nodo}
                )

            if tipo == "on_chain_end" and nodo:
                nodos_abiertos.discard(nodo)
                yield _format_sse(
                    {"type": "node_end", "thread_id": thread_id, "node": nodo}
                )
                for linea in await asyncio.to_thread(
                    _emitir_logs_pendientes, thread_id, config
                ):
                    yield _format_sse(
                        {"type": "log", "thread_id": thread_id, "line": linea}
                    )

            await asyncio.sleep(0)

        await asyncio.to_thread(_persistir_metricas_tokens, config, acumulador_tokens)

        for linea in await asyncio.to_thread(_emitir_logs_pendientes, thread_id, config):
            yield _format_sse({"type": "log", "thread_id": thread_id, "line": linea})

        for mensaje in _eventos_terminales_desde_snapshot(thread_id, config):
            yield mensaje
    except Exception as exc:
        yield _format_sse(
            {
                "type": "error",
                "thread_id": thread_id,
                "message": str(exc),
            }
        )
        raise
    finally:
        yield _format_sse({"type": "done", "thread_id": thread_id})


async def _ejecutar_grafo_async(
    thread_id: str,
    entrada: dict | None,
    config: dict,
) -> None:
    """Ejecuta el grafo y difunde eventos SSE a suscriptores conectados."""
    print(f"[{thread_id}] >> Iniciando ejecucion del grafo (astream_events)...")
    _limpiar_buffer_sse(thread_id)
    try:
        async for mensaje_sse in stream_grafo_events(thread_id, entrada, config):
            if '"type": "node_end"' in mensaje_sse or '"type": "node_start"' in mensaje_sse:
                print(f"[{thread_id}] >> {mensaje_sse.strip()}")
            await _broadcast_sse(thread_id, mensaje_sse)
            await asyncio.sleep(0)
        print(f"[{thread_id}] -- Ejecucion pausada o finalizada.")
    except Exception as exc:
        print(f"[{thread_id}] !! Error en ejecucion: {exc}")
    finally:
        _hilos_sin_checkpoint.pop(thread_id, None)
        _ejecuciones_pendientes.pop(thread_id, None)
        _runs_activos.discard(thread_id)
        _run_tasks.pop(thread_id, None)


def _lanzar_ejecucion_grafo(
    thread_id: str,
    entrada: dict | None,
    config: dict,
) -> None:
    """Programa la ejecución en el event loop sin bloquear la respuesta HTTP."""
    tarea = asyncio.create_task(
        _ejecutar_grafo_async(thread_id, entrada, config),
        name=f"grafo-{thread_id}",
    )
    _run_tasks[thread_id] = tarea

    def _limpiar_tarea(task: asyncio.Task[None]) -> None:
        _run_tasks.pop(thread_id, None)
        if task.cancelled():
            _runs_activos.discard(thread_id)

    tarea.add_done_callback(_limpiar_tarea)


async def _sse_consumer(
    thread_id: str,
    cola: asyncio.Queue[str],
) -> AsyncIterator[str]:
    """Entrega eventos SSE al cliente; heartbeat si no hay actividad."""
    try:
        yield _format_sse({"type": "connected", "thread_id": thread_id})

        buffer = list(_sse_event_buffers.get(thread_id, []))
        if buffer:
            for mensaje in buffer:
                if '"type": "report_delta"' in mensaje:
                    continue
                yield mensaje
                if '"type": "done"' in mensaje:
                    return

        if thread_id not in _runs_activos:
            try:
                snapshot, config = _obtener_snapshot_o_404(thread_id)
            except HTTPException:
                snapshot, config = None, crear_config(thread_id)

            if snapshot is not None:
                terminales = _eventos_terminales_desde_snapshot(thread_id, config)
                if terminales:
                    for mensaje in terminales:
                        yield mensaje
                    yield _format_sse({"type": "done", "thread_id": thread_id})
                    return

        while True:
            try:
                mensaje = await asyncio.wait_for(cola.get(), timeout=25.0)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
                continue

            yield mensaje
            if '"type": "done"' in mensaje:
                break
    finally:
        await _unregister_sse_subscriber(thread_id, cola)


@app.post("/api/tareas", response_model=EstadoTareaResponse, status_code=201)
async def crear_tarea(payload: CrearTareaRequest) -> EstadoTareaResponse:
    """Registra el hilo y estado inicial; la ejecución arranca con POST /ejecutar tras conectar SSE."""
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
        "config": config,
    }
    _contexto_emitido_count[thread_id] = 0

    return EstadoTareaResponse(
        thread_id=thread_id,
        esperando_feedback_humano=False,
        finalizado=False,
        solicitud=solicitud,
        proximos_nodos=["supervisor"],
        estado=_serializar_valor(entrada_inicial),
    )


@app.post("/api/tareas/{thread_id}/ejecutar")
async def ejecutar_tarea(thread_id: str) -> dict[str, str]:
    """Dispara el grafo cuando el cliente SSE ya está conectado (`connected`)."""
    if not _thread_existe(thread_id):
        raise HTTPException(status_code=404, detail=f"thread_id '{thread_id}' no encontrado.")

    async with _ejecutar_lock:
        if thread_id in _runs_activos:
            return {"status": "already_running", "thread_id": thread_id}

        config = crear_config(thread_id)
        entrada: dict | None = None

        if thread_id in _hilos_sin_checkpoint or thread_id in _ejecuciones_pendientes:
            entrada, config = _resolver_entrada_pendiente(thread_id, config)
        elif thread_existe_en_checkpointer(graph, config):
            entrada = None
        else:
            raise HTTPException(
                status_code=409,
                detail="No hay ejecución pendiente para este hilo.",
            )

        _runs_activos.add(thread_id)
        _lanzar_ejecucion_grafo(thread_id, entrada, config)

    return {"status": "started", "thread_id": thread_id}


@app.get("/api/tareas/{thread_id}", response_model=EstadoTareaResponse)
async def obtener_tarea(thread_id: str) -> EstadoTareaResponse:
    snapshot, _ = _obtener_snapshot_o_404(thread_id)
    if snapshot is None:
        return _construir_respuesta_pendiente(thread_id)
    return _construir_respuesta_estado(thread_id, snapshot)


@app.get("/api/tareas/{thread_id}/stream")
async def stream_tarea(thread_id: str) -> StreamingResponse:
    """SSE en tiempo real: nodos, logs y hitos HITL/completed (Paso 1)."""
    if not _thread_existe(thread_id):
        raise HTTPException(status_code=404, detail=f"thread_id '{thread_id}' no encontrado.")

    cola = await _register_sse_subscriber(thread_id)

    return StreamingResponse(
        _sse_consumer(thread_id, cola),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post("/api/tareas/{thread_id}/responder", response_model=EstadoTareaResponse)
async def responder_tarea(
    thread_id: str,
    payload: ResponderTareaRequest,
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
    _inicializar_contador_contexto(thread_id, config)
    _limpiar_buffer_sse(thread_id)
    _ejecuciones_pendientes[thread_id] = {
        "entrada": None,
        "config": config,
    }

    snapshot_actualizado = graph.get_state(config)
    return _construir_respuesta_estado(thread_id, snapshot_actualizado)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
