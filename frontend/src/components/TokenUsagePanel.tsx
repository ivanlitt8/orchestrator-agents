import type { MetricasTokens } from '../types/task'
import { formatTokens } from '../utils/formatTokens'

const ETIQUETAS_NODO: Record<string, string> = {
  supervisor: 'Supervisor',
  ejecutor: 'Ejecutor',
  revisor: 'Revisor',
  consolidacion_memoria: 'Memoria',
}

const ORDEN_NODOS = [
  'supervisor',
  'ejecutor',
  'revisor',
  'consolidacion_memoria',
] as const

type TokenUsagePanelProps = {
  metricas: MetricasTokens
  variant?: 'hitl' | 'completed'
}

export function TokenUsagePanel({
  metricas,
  variant = 'hitl',
}: TokenUsagePanelProps) {
  if (metricas.total_tokens <= 0) return null

  const nodos = ORDEN_NODOS.map((id) => metricas.por_nodo[id]).filter(
    (uso): uso is NonNullable<typeof uso> =>
      uso !== undefined && uso.total_tokens > 0,
  )

  const borderClass =
    variant === 'completed'
      ? 'border-emerald-500/20 bg-emerald-500/5'
      : 'border-violet-500/20 bg-violet-500/5'

  return (
    <div className={`mt-4 rounded-lg border px-3 py-2.5 ${borderClass}`}>
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
        Uso de tokens LLM
      </p>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-300">
        <span>
          Total{' '}
          <span className="font-mono text-slate-100">
            {formatTokens(metricas.total_tokens)}
          </span>
        </span>
        <span className="text-slate-500">
          ↑ {formatTokens(metricas.total_prompt_tokens)} prompt · ↓{' '}
          {formatTokens(metricas.total_completion_tokens)} completion
        </span>
      </div>
      {nodos.length > 0 && (
        <ul className="mt-2 space-y-1 border-t border-slate-800/60 pt-2">
          {nodos.map((uso) => (
            <li
              key={uso.nodo}
              className="flex items-center justify-between gap-2 text-[11px] text-slate-400"
            >
              <span>{ETIQUETAS_NODO[uso.nodo] ?? uso.nodo}</span>
              <span className="font-mono text-slate-300">
                {formatTokens(uso.total_tokens)}
                {uso.llamadas > 1 ? ` · ${uso.llamadas}×` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
