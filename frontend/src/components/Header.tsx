import { Sparkles } from 'lucide-react'
import type { ScreenStep } from '../types'
import { STEP_INDICATOR, STEP_LABELS } from '../constants'

export function Header({ step }: { step: ScreenStep }) {
  return (
    <header className="relative z-20 shrink-0 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md">
      <div className="flex items-center justify-between px-5 py-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/15 ring-1 ring-violet-500/30">
            <Sparkles className="h-4 w-4 text-violet-400" />
          </div>
          <h1 className="text-base font-semibold tracking-tight text-slate-100">
            Agentic Orchestrator
          </h1>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-slate-700/80 bg-slate-800/60 px-3 py-1 text-xs text-slate-300">
          <span
            className={`h-2 w-2 rounded-full ${STEP_INDICATOR[step]}`}
            aria-hidden
          />
          <span>{STEP_LABELS[step]}</span>
        </div>
      </div>
    </header>
  )
}
