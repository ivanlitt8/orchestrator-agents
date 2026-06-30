import { useLayoutEffect, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Bot, CheckCircle2, Loader2, User } from 'lucide-react'
import type { FeedItem, ScreenStep } from '../types'
import { AGENTES_GRAFO } from '../constants'
import { MarkdownReportRenderer } from './MarkdownReportRenderer'
import { OrchestratorAvatar } from './OrchestratorAvatar'
import { ScrollArea } from './ui/scroll-area'
import { filterLogsForAgent } from '../utils/agentLogs'
import {
  resolveAgentVisualStates,
  resolveDisplayNode,
} from '../utils/pipelineProgress'
import { scrollAreaToBottom } from '../utils/scrollArea'

const fadeUp = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] as const },
}

const accordionTransition = {
  duration: 0.28,
  ease: [0.22, 1, 0.36, 1] as const,
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

function AgentLogsPanel({
  logs,
  autoScroll = false,
}: {
  logs: string[]
  autoScroll?: boolean
}) {
  const contentRef = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    if (autoScroll) scrollAreaToBottom(contentRef.current)
  }, [logs, autoScroll])

  if (logs.length === 0) {
    return (
      <p className="px-3 py-2 font-mono text-[11px] italic text-slate-600">
        Esperando eventos del grafo…
      </p>
    )
  }

  return (
    <ScrollArea
      type="auto"
      className="max-h-28 w-full rounded-md border border-slate-800/50 bg-slate-950/60"
    >
      <div
        ref={contentRef}
        className="space-y-0.5 px-3 py-2 pr-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words text-slate-500"
      >
        {logs.map((linea, i) => (
          <div key={`${linea}-${i}`}>{linea}</div>
        ))}
      </div>
    </ScrollArea>
  )
}

function ProcessingBlock({
  step,
  currentNode,
  logs,
  frozen = false,
}: {
  step: ScreenStep
  currentNode: string | null
  logs: string[]
  frozen?: boolean
}) {
  const visualStep = frozen ? 'HITL_WAITING' : step
  const agentStates = resolveAgentVisualStates(currentNode, visualStep, logs)
  const displayNode = frozen ? null : resolveDisplayNode(currentNode, step)
  const isActive = !frozen && step === 'PROCESSING'

  return (
    <FeedBlock>
      <div className="flex items-start gap-2">
        {isActive && (
          <OrchestratorAvatar step={step} placement="processing" />
        )}
        <div className="flex min-w-0 flex-1 gap-3">
          {!isActive && (
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-800 ring-1 ring-slate-700">
              <Bot className="h-4 w-4 text-violet-400" />
            </div>
          )}
          <div className="min-w-0 flex-1 overflow-hidden rounded-2xl rounded-tl-md border border-slate-800 bg-slate-900/60">
            <div className="border-b border-slate-800 px-4 py-3">
              <div className="flex items-center gap-2">
                {isActive ? (
                  <Loader2 className="h-4 w-4 animate-spin text-amber-400" />
                ) : (
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                )}
                <span className="text-sm font-medium text-slate-200">
                  {isActive ? 'Orquestación en curso' : 'Pipeline completado'}
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
                const agentLogs = filterLogsForAgent(logs, agente.id)
                const showLiveLogs = isActive && activo
                const showFrozenLogs = frozen && agentLogs.length > 0

                return (
                  <li key={agente.id} className="rounded-lg px-1 py-1">
                    <div className="flex items-center gap-3 px-2 py-2.5 text-sm">
                      <span
                        className={`h-2 w-2 shrink-0 rounded-full ${
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
                    </div>

                    <AnimatePresence initial={false}>
                      {showLiveLogs && (
                        <motion.div
                          key={`logs-live-${agente.id}`}
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={accordionTransition}
                          className="overflow-hidden px-2 pb-2"
                        >
                          <AgentLogsPanel logs={agentLogs} autoScroll />
                        </motion.div>
                      )}
                    </AnimatePresence>

                    {showFrozenLogs && (
                      <div className="overflow-hidden px-2 pb-2 opacity-80">
                        <AgentLogsPanel logs={agentLogs} />
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
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
            <MarkdownReportRenderer content={content} />
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
            <MarkdownReportRenderer content={content} variant="premium" />
          </div>
        </div>
      </div>
    </FeedBlock>
  )
}

function FeedHistoryItem({ item }: { item: FeedItem }) {
  switch (item.kind) {
    case 'user':
      return <UserMessage text={item.text} />
    case 'pipeline':
      return (
        <ProcessingBlock
          step="HITL_WAITING"
          currentNode={null}
          logs={item.logs}
          frozen
        />
      )
    case 'hitl_report':
      return (
        <HitlReportBlock
          content={item.content}
          scoreCalidad={item.scoreCalidad}
        />
      )
    case 'completed_report':
      return <CompletedBlock content={item.content} />
    default:
      return null
  }
}

type ChatFeedProps = {
  step: ScreenStep
  feedItems: FeedItem[]
  logs: string[]
  currentNode: string | null
}

export function ChatFeed({
  step,
  feedItems,
  logs,
  currentNode,
}: ChatFeedProps) {
  if (step === 'IDLE') return null

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-6 pb-8">
      {feedItems.map((item) => (
        <FeedHistoryItem key={item.id} item={item} />
      ))}
      {step === 'PROCESSING' && (
        <ProcessingBlock
          step="PROCESSING"
          currentNode={currentNode}
          logs={logs}
        />
      )}
    </div>
  )
}
