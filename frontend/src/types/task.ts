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
}

export type FeedCompletedReportItem = {
  id: string
  kind: 'completed_report'
  content: string
}

export type FeedItem =
  | FeedUserItem
  | FeedPipelineItem
  | FeedHitlReportItem
  | FeedCompletedReportItem

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
  estado: {
    contexto_acumulado?: string[]
    [key: string]: unknown
  }
}
