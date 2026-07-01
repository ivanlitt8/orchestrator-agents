export type ScreenStep = 'IDLE' | 'PROCESSING' | 'HITL_WAITING' | 'COMPLETED'

export type FeedUserItem = {
  id: string
  kind: 'user'
  text: string
}

export type FeedPipelineItem = {
  id: string
  kind: 'pipeline'
  logs: string[]
}

export type FeedHitlReportItem = {
  id: string
  kind: 'hitl_report'
  content: string
  scoreCalidad: number
  metricasTokens?: MetricasTokens
}

export type FeedCompletedReportItem = {
  id: string
  kind: 'completed_report'
  content: string
  metricasTokens?: MetricasTokens
}

export type FeedItem =
  | FeedUserItem
  | FeedPipelineItem
  | FeedHitlReportItem
  | FeedCompletedReportItem

export type UsoTokensNodo = {
  nodo: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  llamadas: number
}

export type MetricasTokens = {
  por_nodo: Record<string, UsoTokensNodo>
  total_prompt_tokens: number
  total_completion_tokens: number
  total_tokens: number
}

export const METRICAS_TOKENS_VACIAS: MetricasTokens = {
  por_nodo: {},
  total_prompt_tokens: 0,
  total_completion_tokens: 0,
  total_tokens: 0,
}

export interface TaskState {
  thread_id: string
  status: ScreenStep
  current_node: string | null
  logs: string[]
  interim_report?: string
  final_report?: string
  waiting_for_feedback: boolean
}

/** Respuesta cruda de la API FastAPI (`EstadoTareaResponse`). */
export interface ApiTareaResponse {
  thread_id: string
  esperando_feedback_humano: boolean
  finalizado: boolean
  solicitud: string
  resultado_final: string
  score_calidad: number
  aprobado_tecnicamente: boolean
  aprobado_por_humano: boolean
  intentos_ejecucion: number
  intentos_busqueda: number
  proximos_nodos: string[]
  metricas_tokens?: MetricasTokens
  estado: {
    contexto_acumulado?: string[]
    [key: string]: unknown
  }
}

/** Eventos SSE emitidos por GET /api/tareas/{thread_id}/stream */
export type StreamEvent =
  | { type: 'connected'; thread_id: string }
  | { type: 'run_started'; thread_id: string }
  | { type: 'node_start'; thread_id: string; node: string }
  | { type: 'node_end'; thread_id: string; node: string }
  | { type: 'log'; thread_id: string; line: string }
  | { type: 'report_delta'; thread_id: string; delta: string }
  | {
      type: 'hitl'
      thread_id: string
      content: string
      score_calidad: number
      metricas_tokens?: MetricasTokens
    }
  | {
      type: 'completed'
      thread_id: string
      content: string
      metricas_tokens?: MetricasTokens
    }
  | { type: 'error'; thread_id: string; message: string }
  | { type: 'done'; thread_id: string }
