import type { StreamEvent } from '../types/task'
import { API_BASE_URL } from './api'

function parseStreamEvent(raw: string): StreamEvent | null {
  try {
    const parsed: unknown = JSON.parse(raw)
    if (
      parsed !== null &&
      typeof parsed === 'object' &&
      'type' in parsed &&
      typeof (parsed as { type: unknown }).type === 'string'
    ) {
      return parsed as StreamEvent
    }
  } catch {
    return null
  }
  return null
}

export function openTaskStream(
  threadId: string,
  onEvent: (event: StreamEvent) => void,
  onError: (error: Error) => void,
): () => void {
  const url = `${API_BASE_URL}/api/tareas/${encodeURIComponent(threadId)}/stream`
  const source = new EventSource(url)

  source.onmessage = (message) => {
    const event = parseStreamEvent(message.data)
    if (event) onEvent(event)
  }

  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED) return
    onError(new Error('Conexión SSE interrumpida'))
    source.close()
  }

  return () => {
    source.close()
  }
}
