import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from state import (
    EstadoSubtarea,
    EvaluacionRevisor,
    ExtraccionBusquedaFeedbackHumano,
    State,
    reabrir_subtarea_ejecutor,
)

load_dotenv()

REVISOR_MODEL = "gemini-3-flash-preview"
EXTRACTOR_BUSQUEDA_MODEL = "gemini-3-flash-preview"
SCORE_MINIMO_APROBACION = 4
MAX_CARACTERES_CONTEXTO_EXTRACTOR = 2500

PROMPT_SISTEMA_EXTRACTOR_BUSQUEDA = """\
Eres el clasificador de feedback humano (HITL) de un orquestador multi-agente. \
Tu única tarea es decidir si el revisor humano pide **nueva investigación web** \
o solo **corrección de redacción/formato** del informe existente.

## Entradas
1. Solicitud original del usuario (contexto global).
2. Resumen del contexto ya investigado (hallazgos Tavily previos).
3. Feedback textual del revisor humano.

## Criterio: `necesita_nueva_busqueda = True`
Marca True SOLO cuando el feedback exige **incorporar datos nuevos, actuales o verificables** \
del mundo real que **no están** en el contexto acumulado, por ejemplo:
- Pedir buscar/investigar/averiguar hechos, cifras, precios, noticias, estadísticas.
- Señalar información factual faltante que requiere fuentes externas frescas.
- Solicitar ampliar el informe con datos de un tema concreto no cubierto aún.

## Criterio: `necesita_nueva_busqueda = False`
Marca False cuando el feedback es **puramente editorial**, sin pedir datos externos nuevos:
- Cambiar título, tono, longitud, orden de secciones o estilo.
- Acortar, resumir, simplificar o reformular texto existente.
- Corregir ortografía, gramática o formato Markdown.
- Pedir más claridad o profesionalismo sin indicar qué dato factual falta.

## Reglas para `nueva_query_busqueda`
- Si `necesita_nueva_busqueda` es False → deja `nueva_query_busqueda` vacío.
- Si es True → redacta UNA query concisa (máx. ~15 palabras), optimizada para Tavily/Google.
- Enfócate en lo que falta según el feedback; **no repitas** temas ya cubiertos \
en el contexto acumulado.
- No copies el feedback literal: destila la intención de búsqueda en lenguaje de consulta.

Responde únicamente mediante el esquema estructurado solicitado.
"""

PROMPT_SISTEMA = """\
Eres el Revisor Técnico de un sistema de orquestación multi-agente. Tu responsabilidad \
es evaluar el informe del Ejecutor ANTES de la revisión humana final.

## Entradas que recibirás
1. Solicitud original del usuario.
2. Plan de subtareas con agentes asignados.
3. Contexto acumulado (incluye hallazgos reales del Investigador con URLs y extractos).
4. Resultado final redactado por el Ejecutor.

## Criterios de evaluación (obligatorios)
1. **Completitud:** ¿El informe responde todas las subtareas del plan y la solicitud original?
2. **Rigor técnico:** ¿Usa datos reales del contexto (URLs, cifras, extractos de Tavily) \
   o contiene vaguedades, generalidades o posibles alucinaciones?
3. **Formato:** ¿El Markdown es limpio, profesional, bien estructurado y fácil de leer?

## Reglas de decisión
- `aprobado_tecnicamente` solo puede ser True si los tres criterios se cumplen y \
`score_calidad >= 4`.
- Si rechazas, lista en `criterios_incumplidos` los criterios fallidos \
(ej: "Completitud", "Rigor técnico", "Formato").
- `feedback_interno` debe ser accionable para el Ejecutor: indica qué corregir con precisión.
- Si el fallo en Completitud o Rigor técnico se debe a datos duros faltantes que \
requieren internet, marca `necesita_nueva_busqueda=True` y escribe en \
`nueva_query_busqueda` la frase exacta de búsqueda para Tavily.
- Si el fallo es solo de redacción o formato, deja `necesita_nueva_busqueda=False`.
- Responde únicamente mediante el esquema estructurado solicitado.
"""


def _resumir_contexto_para_extractor(contexto_acumulado: list[str]) -> str:
    """Condensa el contexto acumulado para el extractor sin enviar textos completos."""
    if not contexto_acumulado:
        return "(sin contexto investigado previo)"

    resumen_partes: list[str] = []
    caracteres_usados = 0

    for indice, fragmento in enumerate(contexto_acumulado, start=1):
        texto = " ".join(fragmento.split())
        if not texto:
            continue

        primera_linea = texto.split(". ", 1)[0].strip()
        if len(primera_linea) > 180:
            primera_linea = primera_linea[:177].rstrip() + "..."

        entrada = f"{indice}. {primera_linea}"
        if caracteres_usados + len(entrada) > MAX_CARACTERES_CONTEXTO_EXTRACTOR:
            resumen_partes.append("... (contexto truncado por límite de resumen)")
            break

        resumen_partes.append(entrada)
        caracteres_usados += len(entrada) + 1

    return "\n".join(resumen_partes) if resumen_partes else "(sin contexto investigado previo)"


def _normalizar_extraccion_busqueda(
    extraccion: ExtraccionBusquedaFeedbackHumano,
) -> tuple[bool, str]:
    """Valida la salida estructurada del extractor antes de enrutar el grafo."""
    if not extraccion.necesita_nueva_busqueda:
        return False, ""

    query = extraccion.nueva_query_busqueda.strip()
    if not query:
        return False, ""

    return True, query


def _construir_mensaje_extractor_busqueda(
    feedback: str,
    *,
    solicitud: str,
    contexto_acumulado: list[str],
) -> str:
    contexto_resumido = _resumir_contexto_para_extractor(contexto_acumulado)
    return (
        f"## Solicitud original\n{solicitud.strip() or '(no especificada)'}\n\n"
        f"## Contexto ya investigado (resumen)\n{contexto_resumido}\n\n"
        f"## Feedback del revisor humano\n{feedback.strip()}"
    )


def detectar_necesidad_busqueda_humana(
    feedback: str,
    *,
    solicitud: str = "",
    contexto_acumulado: list[str] | None = None,
) -> tuple[bool, str]:
    """Clasifica el feedback humano con Gemini Structured Output."""
    texto = feedback.strip()
    if not texto:
        return False, ""

    extractor = _obtener_extractor_busqueda_humana()
    resultado = extractor.invoke(
        [
            SystemMessage(content=PROMPT_SISTEMA_EXTRACTOR_BUSQUEDA),
            HumanMessage(
                content=_construir_mensaje_extractor_busqueda(
                    texto,
                    solicitud=solicitud,
                    contexto_acumulado=contexto_acumulado or [],
                )
            ),
        ]
    )
    extraccion = (
        resultado
        if isinstance(resultado, ExtraccionBusquedaFeedbackHumano)
        else ExtraccionBusquedaFeedbackHumano.model_validate(resultado)
    )
    return _normalizar_extraccion_busqueda(extraccion)


def _obtener_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta la variable de entorno GEMINI_API_KEY. "
            "Configúrala en el archivo .env antes de ejecutar el Revisor."
        )
    return api_key


@lru_cache(maxsize=1)
def _obtener_extractor_busqueda_humana():
    llm = ChatGoogleGenerativeAI(
        model=EXTRACTOR_BUSQUEDA_MODEL,
        api_key=_obtener_api_key(),
        temperature=0.0,
    )
    return llm.with_structured_output(
        ExtraccionBusquedaFeedbackHumano,
        method="json_schema",
    )


@lru_cache(maxsize=1)
def _obtener_evaluador():
    llm = ChatGoogleGenerativeAI(
        model=REVISOR_MODEL,
        api_key=_obtener_api_key(),
        temperature=0.1,
    )
    return llm.with_structured_output(EvaluacionRevisor, method="json_schema")


def _formatear_plan(plan: list) -> str:
    if not plan:
        return "(sin plan registrado)"
    lineas = []
    for subtarea in plan:
        agente = (
            subtarea.agente_asignado.value
            if hasattr(subtarea.agente_asignado, "value")
            else str(subtarea.agente_asignado)
        )
        estado = (
            subtarea.estado.value
            if hasattr(subtarea.estado, "value")
            else str(subtarea.estado)
        )
        lineas.append(
            f"- [{subtarea.id}] ({agente}, {estado}): {subtarea.descripcion}"
        )
    return "\n".join(lineas)


def _construir_mensaje_evaluacion(state: State) -> str:
    contexto = (
        "\n\n---\n\n".join(state.contexto_acumulado)
        if state.contexto_acumulado
        else "(sin contexto acumulado)"
    )
    return (
        f"## Solicitud original\n{state.solicitud.strip()}\n\n"
        f"## Plan de subtareas\n{_formatear_plan(state.plan)}\n\n"
        f"## Contexto acumulado\n{contexto}\n\n"
        f"## Resultado final del Ejecutor\n{state.resultado_final.strip()}"
    )


def evaluar_informe(state: State) -> EvaluacionRevisor:
    """Evalúa técnicamente el informe con Gemini Structured Output."""
    evaluador = _obtener_evaluador()
    resultado = evaluador.invoke(
        [
            SystemMessage(content=PROMPT_SISTEMA),
            HumanMessage(content=_construir_mensaje_evaluacion(state)),
        ]
    )
    evaluacion = (
        resultado
        if isinstance(resultado, EvaluacionRevisor)
        else EvaluacionRevisor.model_validate(resultado)
    )

    if evaluacion.score_calidad < SCORE_MINIMO_APROBACION:
        evaluacion = evaluacion.model_copy(update={"aprobado_tecnicamente": False})

    if evaluacion.criterios_incumplidos and evaluacion.aprobado_tecnicamente:
        evaluacion = evaluacion.model_copy(update={"aprobado_tecnicamente": False})

    if evaluacion.necesita_nueva_busqueda and not evaluacion.nueva_query_busqueda.strip():
        evaluacion = evaluacion.model_copy(update={"necesita_nueva_busqueda": False})

    return evaluacion


def _destino_rechazo_mensaje(necesita_busqueda: bool) -> str:
    if necesita_busqueda:
        return "Re-enrutando al investigador para nueva búsqueda web."
    return "Re-enrutando al ejecutor."


def nodo_revisor(state: State) -> dict:
    """Revisión técnica automática con salida estructurada."""
    subtareas_pendientes = [
        t for t in state.plan if t.estado != EstadoSubtarea.COMPLETADA
    ]
    if subtareas_pendientes or not state.resultado_final.strip():
        return {
            "aprobado_tecnicamente": False,
            "score_calidad": 1,
            "criterios_incumplidos": ["Completitud"],
            "feedback_interno": (
                "El informe está incompleto o faltan subtareas por completar. "
                "Genera un resultado final que responda la solicitud y cumpla el plan."
            ),
            "necesita_nueva_busqueda": False,
            "nueva_query_busqueda": "",
            "contexto_acumulado": state.contexto_acumulado
            + ["[Revisor] Rechazo técnico: plan incompleto o informe vacío."],
            "plan": reabrir_subtarea_ejecutor(state.plan),
        }

    evaluacion = evaluar_informe(state)

    if evaluacion.aprobado_tecnicamente:
        return {
            "aprobado_tecnicamente": True,
            "score_calidad": evaluacion.score_calidad,
            "criterios_incumplidos": [],
            "feedback_interno": "",
            "necesita_nueva_busqueda": False,
            "nueva_query_busqueda": "",
            "contexto_acumulado": state.contexto_acumulado
            + [
                f"[Revisor] Aprobación técnica (score {evaluacion.score_calidad}/5). "
                "Pendiente revisión humana."
            ],
        }

    necesita_busqueda = evaluacion.necesita_nueva_busqueda
    return {
        "aprobado_tecnicamente": False,
        "score_calidad": evaluacion.score_calidad,
        "criterios_incumplidos": evaluacion.criterios_incumplidos,
        "feedback_interno": evaluacion.feedback_interno,
        "necesita_nueva_busqueda": necesita_busqueda,
        "nueva_query_busqueda": (
            evaluacion.nueva_query_busqueda.strip() if necesita_busqueda else ""
        ),
        "plan": reabrir_subtarea_ejecutor(state.plan),
        "contexto_acumulado": state.contexto_acumulado
        + [
            f"[Revisor] Rechazo técnico (score {evaluacion.score_calidad}/5). "
            f"Criterios incumplidos: {', '.join(evaluacion.criterios_incumplidos) or 'N/A'}. "
            f"{_destino_rechazo_mensaje(necesita_busqueda)}"
        ],
    }


def nodo_revision_humana(state: State) -> dict:
    """Consolida la decisión humana tras la aprobación técnica."""
    if state.aprobado_por_humano:
        return {
            "necesita_nueva_busqueda": False,
            "nueva_query_busqueda": "",
            "contexto_acumulado": state.contexto_acumulado
            + ["[HITL] Informe aprobado por el humano. Procediendo a consolidación de memoria."],
        }

    if state.feedback_revisor.strip():
        necesita_busqueda = state.necesita_nueva_busqueda
        return {
            "contexto_acumulado": state.contexto_acumulado
            + [
                "[HITL] Informe rechazado por el humano. "
                f"Feedback: {state.feedback_revisor.strip()}. "
                f"{_destino_rechazo_mensaje(necesita_busqueda)}"
            ],
        }

    return {}
