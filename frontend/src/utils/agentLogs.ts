import { AGENTES_GRAFO } from '../constants'

const EXTRA_TAGS = ['hitl', 'memoria'] as const

function logMatchesAgent(line: string, agentId: string): boolean {
  const lower = line.toLowerCase()
  const label = agentId.charAt(0).toUpperCase() + agentId.slice(1)
  return lower.includes(`[${label}]`) || lower.includes(`[${agentId}]`)
}

function hasAnyAgentTag(line: string): boolean {
  return (
    AGENTES_GRAFO.some((agente) => logMatchesAgent(line, agente.id)) ||
    EXTRA_TAGS.some((tag) => line.toLowerCase().includes(`[${tag}]`))
  )
}

/** Filtra líneas de `contexto_acumulado` que pertenecen a un agente del pipeline. */
export function filterLogsForAgent(logs: string[], agentId: string): string[] {
  return logs.filter((line) => {
    if (logMatchesAgent(line, agentId)) return true
    // Análisis del plan sin prefijo explícito → Supervisor
    if (agentId === 'supervisor' && !hasAnyAgentTag(line)) return true
    return false
  })
}
