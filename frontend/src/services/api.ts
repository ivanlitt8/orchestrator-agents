import type { ApiTareaResponse, ScreenStep, TaskState } from '../types/task'

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

function inferScreenStep(response: ApiTareaResponse): ScreenStep {
  if (response.finalizado) return 'COMPLETED'
  if (response.esperando_feedback_humano) return 'HITL_WAITING'
  return 'PROCESSING'
}

function extractLogs(estado: ApiTareaResponse['estado']): string[] {
  const acumulado = estado?.contexto_acumulado
  if (Array.isArray(acumulado) && acumulado.length > 0) {
    return acumulado.map(String)
  }
  return []
}

export function mapApiResponseToTaskState(
  response: ApiTareaResponse,
): TaskState {
  const status = inferScreenStep(response)
  const logs = extractLogs(response.estado)
  const informe = response.resultado_final.trim()

  return {
    thread_id: response.thread_id,
    status,
    current_node: response.proximos_nodos[0] ?? null,
    logs,
    interim_report:
      status === 'HITL_WAITING' || (status === 'PROCESSING' && informe)
        ? informe || undefined
        : undefined,
    final_report: status === 'COMPLETED' ? informe || undefined : undefined,
    waiting_for_feedback: response.esperando_feedback_humano,
  }
}

async function requestJson<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    const detalle = await response.text()
    throw new Error(
      `Error API ${response.status}${detalle ? `: ${detalle}` : ''}`,
    )
  }

  return response.json() as Promise<T>
}

export async function createTask(prompt: string): Promise<ApiTareaResponse> {
  return requestJson<ApiTareaResponse>('/api/tareas', {
    method: 'POST',
    body: JSON.stringify({ solicitud: prompt.trim() }),
  })
}

/** @deprecated Usar createTask + runTask tras conectar SSE */
export async function startTask(
  prompt: string,
): Promise<{ thread_id: string }> {
  const data = await createTask(prompt)
  return { thread_id: data.thread_id }
}

export async function runTask(threadId: string): Promise<void> {
  await requestJson<{ status: string; thread_id: string }>(
    `/api/tareas/${encodeURIComponent(threadId)}/ejecutar`,
    { method: 'POST' },
  )
}

export async function fetchTaskSnapshot(
  threadId: string,
): Promise<ApiTareaResponse> {
  return requestJson<ApiTareaResponse>(
    `/api/tareas/${encodeURIComponent(threadId)}`,
  )
}

export async function getTaskStatus(threadId: string): Promise<TaskState> {
  const data = await fetchTaskSnapshot(threadId)
  return mapApiResponseToTaskState(data)
}

export async function sendTaskFeedback(
  threadId: string,
  feedback: string,
): Promise<{ success: boolean }> {
  await requestJson<ApiTareaResponse>(
    `/api/tareas/${encodeURIComponent(threadId)}/responder`,
    {
      method: 'POST',
      body: JSON.stringify({ feedback: feedback.trim() }),
    },
  )
  return { success: true }
}
