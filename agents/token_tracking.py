"""Acumulación de uso de tokens LLM por nodo del grafo."""

from __future__ import annotations

from typing import Any

from state import MetricasTokens, UsoTokensNodo

NODOS_CON_TOKENS = frozenset({
    "supervisor",
    "ejecutor",
    "revisor",
    "consolidacion_memoria",
})


def _coercionar_entero(valor: Any) -> int:
    if valor is None:
        return 0
    try:
        return max(0, int(valor))
    except (TypeError, ValueError):
        return 0


def _usage_desde_mapping(usage: dict[str, Any]) -> tuple[int, int]:
    prompt = _coercionar_entero(
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or usage.get("prompt_token_count")
    )
    completion = _coercionar_entero(
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("completion_token_count")
        or usage.get("candidates_token_count")
    )
    return prompt, completion


def _extraer_usage_desde_output(output: Any) -> tuple[int, int]:
    if output is None:
        return 0, 0

    usage_meta = getattr(output, "usage_metadata", None)
    if isinstance(usage_meta, dict) and usage_meta:
        return _usage_desde_mapping(usage_meta)

    response_meta = getattr(output, "response_metadata", None)
    if isinstance(response_meta, dict):
        token_usage = response_meta.get("token_usage")
        if isinstance(token_usage, dict):
            return _usage_desde_mapping(token_usage)
        x_groq = response_meta.get("x_groq")
        if isinstance(x_groq, dict):
            usage = x_groq.get("usage")
            if isinstance(usage, dict):
                return _usage_desde_mapping(usage)

    if isinstance(output, dict):
        return _usage_desde_mapping(output)

    generations = getattr(output, "generations", None)
    if generations:
        for gen_list in generations:
            for gen in gen_list:
                message = getattr(gen, "message", None)
                if message is not None:
                    prompt, completion = _extraer_usage_desde_output(message)
                    if prompt or completion:
                        return prompt, completion

    return 0, 0


def extraer_tokens_desde_evento(evento: dict[str, Any]) -> tuple[int, int]:
    """Lee prompt/completion tokens de un evento `on_chat_model_end` (v2)."""
    data = evento.get("data")
    if not isinstance(data, dict):
        return 0, 0

    output = data.get("output")
    prompt, completion = _extraer_usage_desde_output(output)
    if prompt or completion:
        return prompt, completion

    chunk = data.get("chunk")
    return _extraer_usage_desde_output(chunk)


def _nodo_desde_evento(evento: dict[str, Any]) -> str | None:
    metadata = evento.get("metadata")
    if not isinstance(metadata, dict):
        return None
    nodo = metadata.get("langgraph_node")
    if isinstance(nodo, str) and nodo in NODOS_CON_TOKENS:
        return nodo
    return None


def _sumar_uso(previo: UsoTokensNodo, prompt: int, completion: int) -> UsoTokensNodo:
    total_nuevo = prompt + completion
    return previo.model_copy(
        update={
            "prompt_tokens": previo.prompt_tokens + prompt,
            "completion_tokens": previo.completion_tokens + completion,
            "total_tokens": previo.total_tokens + total_nuevo,
            "llamadas": previo.llamadas + 1,
        }
    )


def _recalcular_totales(por_nodo: dict[str, UsoTokensNodo]) -> MetricasTokens:
    return MetricasTokens(
        por_nodo=por_nodo,
        total_prompt_tokens=sum(u.prompt_tokens for u in por_nodo.values()),
        total_completion_tokens=sum(u.completion_tokens for u in por_nodo.values()),
        total_tokens=sum(u.total_tokens for u in por_nodo.values()),
    )


def parsear_metricas_tokens(raw: Any) -> MetricasTokens:
    if isinstance(raw, MetricasTokens):
        return raw
    if isinstance(raw, dict):
        try:
            return MetricasTokens.model_validate(raw)
        except Exception:
            pass
    return MetricasTokens()


class TokenAccumulator:
    """Acumula tokens de una ejecución del grafo (una pasada de astream_events)."""

    def __init__(self) -> None:
        self._por_nodo: dict[str, UsoTokensNodo] = {}

    def registrar_desde_evento(self, evento: dict[str, Any]) -> None:
        if evento.get("event") != "on_chat_model_end":
            return

        nodo = _nodo_desde_evento(evento)
        if nodo is None:
            return

        prompt, completion = extraer_tokens_desde_evento(evento)
        if prompt == 0 and completion == 0:
            return

        previo = self._por_nodo.get(nodo)
        if previo is None:
            total = prompt + completion
            self._por_nodo[nodo] = UsoTokensNodo(
                nodo=nodo,
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                llamadas=1,
            )
        else:
            self._por_nodo[nodo] = _sumar_uso(previo, prompt, completion)

    def to_metricas(self) -> MetricasTokens:
        return _recalcular_totales(dict(self._por_nodo))

    def merge(self, previo: MetricasTokens | None) -> MetricasTokens:
        actual = self.to_metricas()
        if previo is None or not previo.por_nodo:
            return actual

        combinado = dict(previo.por_nodo)
        for nodo, uso in actual.por_nodo.items():
            if nodo in combinado:
                prev = combinado[nodo]
                combinado[nodo] = UsoTokensNodo(
                    nodo=nodo,
                    prompt_tokens=prev.prompt_tokens + uso.prompt_tokens,
                    completion_tokens=prev.completion_tokens + uso.completion_tokens,
                    total_tokens=prev.total_tokens + uso.total_tokens,
                    llamadas=prev.llamadas + uso.llamadas,
                )
            else:
                combinado[nodo] = uso

        return _recalcular_totales(combinado)
