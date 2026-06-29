import type { ScreenStep } from '../types/task'
import { AGENTES_GRAFO } from '../constants'

const NODE_TO_INDEX: Record<string, number> = {
  supervisor: 0,
  investigador: 1,
  ejecutor: 2,
  revisor: 3,
  revision_humana: 4,
}

export type AgentVisualState = {
  activo: boolean
  completado: boolean
  pendiente: boolean
}

/** Índice del agente más avanzado detectado en contexto_acumulado (preparado para polling tick-a-tick). */
export function inferHighestCompletedFromLogs(logs: string[]): number {
  let highest = -1
  const texto = logs.join('\n').toLowerCase()

  for (let indice = AGENTES_GRAFO.length - 1; indice >= 0; indice -= 1) {
    const id = AGENTES_GRAFO[indice].id
    if (
      texto.includes(`[${id.charAt(0).toUpperCase()}${id.slice(1)}]`) ||
      texto.includes(`[${id}]`) ||
      texto.includes(id)
    ) {
      highest = indice
      break
    }
  }

  return highest
}

export function resolveAgentVisualStates(
  currentNode: string | null,
  step: ScreenStep,
  logs: string[],
): AgentVisualState[] {
  if (step === 'COMPLETED' || step === 'HITL_WAITING') {
    return AGENTES_GRAFO.map(() => ({
      activo: false,
      completado: true,
      pendiente: false,
    }))
  }

  if (step !== 'PROCESSING') {
    return AGENTES_GRAFO.map(() => ({
      activo: false,
      completado: false,
      pendiente: true,
    }))
  }

  if (currentNode === 'revision_humana') {
    return AGENTES_GRAFO.map(() => ({
      activo: false,
      completado: true,
      pendiente: false,
    }))
  }

  const logHighest = inferHighestCompletedFromLogs(logs)
  let activeIndex = 0

  if (currentNode) {
    const nodeIndex = NODE_TO_INDEX[currentNode]
    if (nodeIndex !== undefined && nodeIndex < AGENTES_GRAFO.length) {
      activeIndex = nodeIndex
    }
  }

  if (logHighest >= 0) {
    activeIndex = Math.max(
      activeIndex,
      Math.min(logHighest + 1, AGENTES_GRAFO.length - 1),
    )
  }

  return AGENTES_GRAFO.map((_, indice) => {
    const completado = indice < activeIndex
    const activo = indice === activeIndex
    return {
      activo,
      completado,
      pendiente: !activo && !completado,
    }
  })
}

export function resolveDisplayNode(
  currentNode: string | null,
  step: ScreenStep,
): string | null {
  if (step !== 'PROCESSING' || !currentNode) return null
  if (currentNode === 'revision_humana') return null
  return currentNode
}
