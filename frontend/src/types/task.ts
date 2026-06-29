export type ScreenStep = 'IDLE' | 'PROCESSING' | 'HITL_WAITING' | 'COMPLETED'

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
