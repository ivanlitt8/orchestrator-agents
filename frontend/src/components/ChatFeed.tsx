import { motion } from 'framer-motion'
import {
  Bot,
  CheckCircle2,
  Loader2,
  Terminal,
  User,
} from 'lucide-react'
import type { ScreenStep } from '../types'
import { AGENTES_GRAFO } from '../constants'
import { MarkdownReport } from './MarkdownReport'
import { OrchestratorAvatar } from './OrchestratorAvatar'
import { ScrollArea } from './ui/scroll-area'
import {
  resolveAgentVisualStates,
  resolveDisplayNode,
} from '../utils/pipelineProgress'

const fadeUp = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] as const },
}

function FeedBlock({
  children,
  className = '',
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <motion.div {...fadeUp} className={`max-w-3xl ${className}`}>
      {children}
    </motion.div>
  )
}

function UserMessage({ text }: { text: string }) {
  return (
    <FeedBlock className="ml-auto">
      <div className="flex justify-end gap-3">
        <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-violet-600/90 px-4 py-3 text-sm leading-relaxed text-white shadow-lg shadow-violet-950/30">
          {text}
        </div>
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-800 ring-1 ring-slate-700">
          <User className="h-4 w-4 text-slate-300" />
        </div>
      </div>
    </FeedBlock>
  )
}

function ProcessingBlock({
  step,
  currentNode,
  logs,
}: {
  step: ScreenStep
  currentNode: string | null
  logs: string[]
}) {
  const agentStates = resolveAgentVisualStates(currentNode, step, logs)
  const displayNode = resolveDisplayNode(currentNode, step)

  return (
    <FeedBlock>
      <div className="flex items-start gap-2">
        {step === 'PROCESSING' && (
          <OrchestratorAvatar step={step} placement="processing" />
        )}
        <div className="flex min-w-0 flex-1 gap-3">
          {step !== 'PROCESSING' && (
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-800 ring-1 ring-slate-700">
              <Bot className="h-4 w-4 text-violet-400" />
            </div>
          )}
          <div className="min-w-0 flex-1 overflow-hidden rounded-2xl rounded-tl-md border border-slate-800 bg-slate-900/60">
          <div className="border-b border-slate-800 px-4 py-3">
            <div className="flex items-center gap-2">
              {step === 'PROCESSING' ? (
                <Loader2 className="h-4 w-4 animate-spin text-amber-400" />
              ) : (
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              )}
              <span className="text-sm font-medium text-slate-200">
                {step === 'PROCESSING'
                  ? 'Orquestación en curso'
                  : 'Pipeline completado'}
              </span>
              {displayNode && (
                <span className="ml-auto font-mono text-[11px] text-slate-500">
                  {displayNode}
                </span>
              )}
            </div>
          </div>
          <ul className="space-y-0 divide-y divide-slate-800/80 px-2 py-1">
            {AGENTES_GRAFO.map((agente, indice) => {
              const { activo, completado } = agentStates[indice]
              return (
                <li
                  key={agente.id}
                  className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm"
                >
                  <span
                    className={`h-2 w-2 rounded-full ${
                      activo
                        ? 'animate-pulse bg-amber-400'
                        : completado
                          ? 'bg-emerald-400'
                          : 'bg-slate-600'
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <span className="text-slate-200">{agente.label}</span>
                    <span className="ml-2 text-xs text-slate-500">
                      {agente.desc}
                    </span>
                  </div>
                  {activo && (
                    <span className="text-xs text-amber-300/90">activo</span>
                  )}
                </li>
              )
            })}
          </ul>
          <div className="border-t border-slate-800 bg-slate-950/80 px-4 py-3">
            <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              <Terminal className="h-3 w-3" />
              Logs técnicos
            </div>
            <ScrollArea className="max-h-28 rounded-lg border border-slate-800/60 bg-slate-950/50">
              <div className="space-y-0.5 px-3 py-2 font-mono text-[11px] leading-relaxed text-slate-500">
                {logs.length > 0 ? (
                  logs.map((linea, i) => (
                    <div key={`${linea}-${i}`} className="truncate">
                      {linea}
                    </div>
                  ))
                ) : (
                  <div className="text-slate-600 italic">
                    Esperando eventos del grafo…
                  </div>
                )}
              </div>
            </ScrollArea>
          </div>
        </div>
        </div>
      </div>
    </FeedBlock>
  )
}

function HitlReportBlock({
  content,
  scoreCalidad,
}: {
  content: string
  scoreCalidad: number
}) {
  return (
    <FeedBlock>
      <div className="flex gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-800 ring-1 ring-violet-500/30">
          <Bot className="h-4 w-4 text-violet-400" />
        </div>
        <div className="min-w-0 flex-1 overflow-hidden rounded-2xl rounded-tl-md border border-violet-500/25 bg-violet-500/5">
          <div className="border-b border-violet-500/20 px-4 py-3">
            <p className="text-sm font-medium text-slate-100">
              Informe preliminar generado
            </p>
            <p className="text-xs text-slate-500">
              Score técnico {scoreCalidad > 0 ? `${scoreCalidad}/5` : 'N/A'} ·
              Pendiente de tu revisión
            </p>
          </div>
          <div className="p-4">
            <MarkdownReport content={content} />
          </div>
        </div>
      </div>
    </FeedBlock>
  )
}

function CompletedBlock({ content }: { content: string }) {
  return (
    <FeedBlock>
      <div className="flex gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500/20 ring-1 ring-emerald-500/40">
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
        </div>
        <div className="min-w-0 flex-1 overflow-hidden rounded-2xl rounded-tl-md border border-emerald-500/30 bg-emerald-500/5">
          <div className="border-b border-emerald-500/20 px-4 py-3">
            <p className="text-sm font-semibold text-emerald-100">
              Informe aprobado y consolidado
            </p>
            <p className="text-xs text-emerald-200/60">
              Memoria indexada · Flujo completado
            </p>
          </div>
          <div className="p-4">
            <MarkdownReport content={content} variant="premium" />
          </div>
        </div>
      </div>
    </FeedBlock>
  )
}

type ChatFeedProps = {
  step: ScreenStep
  solicitud: string
  logs: string[]
  currentNode: string | null
  interimReport?: string
  finalReport?: string
  scoreCalidad: number
}

export function ChatFeed({
  step,
  solicitud,
  logs,
  currentNode,
  interimReport,
  finalReport,
  scoreCalidad,
}: ChatFeedProps) {
  const sessionActive = step !== 'IDLE'

  if (!sessionActive) return null

  const informeHitl = interimReport ?? finalReport

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-6 pb-8">
      {solicitud.trim() && <UserMessage text={solicitud} />}
      {(step === 'PROCESSING' ||
        step === 'HITL_WAITING' ||
        step === 'COMPLETED') && (
        <ProcessingBlock step={step} currentNode={currentNode} logs={logs} />
      )}
      {(step === 'HITL_WAITING' || step === 'COMPLETED') && informeHitl && (
        <HitlReportBlock content={informeHitl} scoreCalidad={scoreCalidad} />
      )}
      {step === 'COMPLETED' && finalReport && (
        <CompletedBlock content={finalReport} />
      )}
    </div>
  )
}
