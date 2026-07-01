import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createTask,
  fetchTaskSnapshot,
  mapApiResponseToTaskState,
  runTask,
  sendTaskFeedback,
} from '../services/api'
import { openTaskStream } from '../services/taskStream'
import type {
  ApiTareaResponse,
  FeedItem,
  MetricasTokens,
  ScreenStep,
  StreamEvent,
  TaskState,
} from '../types/task'
import { METRICAS_TOKENS_VACIAS } from '../types/task'
import { createFeedItemId } from '../utils/feedId'

type BeginStreamOptions = {
  /** Tras `connected`, llama POST /ejecutar (nueva tarea o post-feedback). */
  triggerExecute?: boolean
  /** Omite GET bootstrap (la tarea acaba de crearse). */
  skipBootstrap?: boolean
}

type UseTaskOrchestratorResult = {
  step: ScreenStep
  threadId: string | null
  solicitud: string
  feedItems: FeedItem[]
  logs: string[]
  currentNode: string | null
  liveReport: string | null
  report: string | undefined
  interimReport: string | undefined
  finalReport: string | undefined
  scoreCalidad: number
  metricasTokens: MetricasTokens
  waitingForFeedback: boolean
  error: string | null
  isLoading: boolean
  submitPrompt: (text: string) => Promise<void>
  submitFeedback: (feedback: string) => Promise<void>
  setStep: (step: ScreenStep) => void
  syncFromApi: (response: ApiTareaResponse) => void
}

function reportFromTaskState(state: TaskState): string | undefined {
  return state.final_report ?? state.interim_report
}

function resolveArchivedReportContent(
  serverContent: string,
  liveReport: string | null,
): string {
  const server = serverContent.trim()
  const live = (liveReport ?? '').trim()
  if (server && (!live || server.length >= live.length)) return serverContent
  if (live) return liveReport as string
  return serverContent
}

function metricasFromApi(raw: ApiTareaResponse['metricas_tokens']): MetricasTokens {
  if (!raw) return METRICAS_TOKENS_VACIAS
  return {
    por_nodo: raw.por_nodo ?? {},
    total_prompt_tokens: raw.total_prompt_tokens ?? 0,
    total_completion_tokens: raw.total_completion_tokens ?? 0,
    total_tokens: raw.total_tokens ?? 0,
  }
}

function archiveProcessingCycle(
  items: FeedItem[],
  logs: string[],
  nextStatus: ScreenStep,
  interimReport: string | undefined,
  finalReport: string | undefined,
  scoreCalidad: number,
  liveReport: string | null = null,
  metricasTokens: MetricasTokens = METRICAS_TOKENS_VACIAS,
): FeedItem[] {
  const next = [...items, { id: createFeedItemId(), kind: 'pipeline' as const, logs: [...logs] }]

  const interimContent = resolveArchivedReportContent(
    interimReport ?? '',
    liveReport,
  )
  const finalContent = resolveArchivedReportContent(finalReport ?? '', liveReport)

  if (nextStatus === 'HITL_WAITING' && interimContent.trim()) {
    next.push({
      id: createFeedItemId(),
      kind: 'hitl_report',
      content: interimContent,
      scoreCalidad,
      metricasTokens,
    })
  }

  if (nextStatus === 'COMPLETED' && finalContent.trim()) {
    next.push({
      id: createFeedItemId(),
      kind: 'completed_report',
      content: finalContent,
      metricasTokens,
    })
  }

  return next
}

export function useTaskOrchestrator(): UseTaskOrchestratorResult {
  const [step, setStep] = useState<ScreenStep>('IDLE')
  const [threadId, setThreadId] = useState<string | null>(null)
  const [solicitud, setSolicitud] = useState('')
  const [feedItems, setFeedItems] = useState<FeedItem[]>([])
  const [logs, setLogs] = useState<string[]>([])
  const [currentNode, setCurrentNode] = useState<string | null>(null)
  const [liveReport, setLiveReport] = useState<string | null>(null)
  const [report, setReport] = useState<string | undefined>()
  const [interimReport, setInterimReport] = useState<string | undefined>()
  const [finalReport, setFinalReport] = useState<string | undefined>()
  const [scoreCalidad, setScoreCalidad] = useState(0)
  const [metricasTokens, setMetricasTokens] = useState<MetricasTokens>(
    METRICAS_TOKENS_VACIAS,
  )
  const [waitingForFeedback, setWaitingForFeedback] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const streamCloseRef = useRef<(() => void) | null>(null)
  const executeTriggeredRef = useRef(false)
  const threadIdRef = useRef<string | null>(null)
  const stepRef = useRef<ScreenStep>('IDLE')
  const logsRef = useRef<string[]>([])
  const liveReportRef = useRef<string | null>(null)

  const closeStream = useCallback(() => {
    streamCloseRef.current?.()
    streamCloseRef.current = null
    executeTriggeredRef.current = false
  }, [])

  const applyTaskState = useCallback((state: TaskState) => {
    setStep(state.status)
    setLogs(state.logs)
    setCurrentNode(state.current_node)
    setInterimReport(state.interim_report)
    setFinalReport(state.final_report)
    setReport(reportFromTaskState(state))
    setWaitingForFeedback(state.waiting_for_feedback)
    stepRef.current = state.status
    logsRef.current = state.logs
  }, [])

  const bootstrapFromApi = useCallback(
    (response: ApiTareaResponse) => {
      setScoreCalidad(response.score_calidad)
      setMetricasTokens(metricasFromApi(response.metricas_tokens))
      applyTaskState(mapApiResponseToTaskState(response))
    },
    [applyTaskState],
  )

  const syncFromApi = useCallback(
    (response: ApiTareaResponse) => {
      const state = mapApiResponseToTaskState(response)
      const prevStep = stepRef.current
      const snapshotLogs = [...logsRef.current]

      if (
        prevStep === 'PROCESSING' &&
        (state.status === 'HITL_WAITING' || state.status === 'COMPLETED')
      ) {
        setFeedItems((items) =>
          archiveProcessingCycle(
            items,
            snapshotLogs,
            state.status,
            state.interim_report,
            state.final_report,
            response.score_calidad,
            null,
            metricasFromApi(response.metricas_tokens),
          ),
        )
      }

      setScoreCalidad(response.score_calidad)
      setMetricasTokens(metricasFromApi(response.metricas_tokens))
      applyTaskState(state)
    },
    [applyTaskState],
  )

  const triggerRunIfNeeded = useCallback(async (activeThreadId: string) => {
    if (executeTriggeredRef.current) return
    executeTriggeredRef.current = true
    await runTask(activeThreadId)
  }, [])

  const applyStreamEvent = useCallback(
    (event: StreamEvent, options?: BeginStreamOptions) => {
      switch (event.type) {
        case 'connected':
          if (options?.triggerExecute) {
            void triggerRunIfNeeded(event.thread_id).catch((err: unknown) => {
              const message =
                err instanceof Error ? err.message : 'No se pudo iniciar el grafo'
              setError(message)
              closeStream()
            })
          }
          break

        case 'run_started':
          setStep('PROCESSING')
          stepRef.current = 'PROCESSING'
          setLiveReport(null)
          liveReportRef.current = null
          break

        case 'node_start':
          setCurrentNode(event.node)
          break

        case 'node_end':
          break

        case 'log':
          setLogs((prev) => {
            if (prev.includes(event.line)) return prev
            const next = [...prev, event.line]
            logsRef.current = next
            return next
          })
          break

        case 'report_delta':
          if (stepRef.current !== 'PROCESSING') break
          setLiveReport((prev) => {
            const next = (prev ?? '') + event.delta
            liveReportRef.current = next
            return next
          })
          break

        case 'hitl': {
          const snapshotLogs = [...logsRef.current]
          const archivedReport = liveReportRef.current
          const interimContent = resolveArchivedReportContent(
            event.content,
            archivedReport,
          )
          const metricas = metricasFromApi(event.metricas_tokens)
          if (stepRef.current === 'PROCESSING') {
            setFeedItems((items) =>
              archiveProcessingCycle(
                items,
                snapshotLogs,
                'HITL_WAITING',
                interimContent,
                undefined,
                event.score_calidad,
                null,
                metricas,
              ),
            )
          }
          setScoreCalidad(event.score_calidad)
          setMetricasTokens(metricas)
          setInterimReport(interimContent)
          setFinalReport(undefined)
          setReport(interimContent)
          setWaitingForFeedback(true)
          setStep('HITL_WAITING')
          stepRef.current = 'HITL_WAITING'
          setLiveReport(null)
          liveReportRef.current = null
          break
        }

        case 'completed': {
          const snapshotLogs = [...logsRef.current]
          const archivedReport = liveReportRef.current
          const finalContent = resolveArchivedReportContent(
            event.content,
            archivedReport,
          )
          const metricas = metricasFromApi(event.metricas_tokens)
          if (stepRef.current === 'PROCESSING') {
            setFeedItems((items) =>
              archiveProcessingCycle(
                items,
                snapshotLogs,
                'COMPLETED',
                undefined,
                finalContent,
                0,
                null,
                metricas,
              ),
            )
          }
          setMetricasTokens(metricas)
          setFinalReport(finalContent)
          setInterimReport(undefined)
          setReport(finalContent)
          setWaitingForFeedback(false)
          setStep('COMPLETED')
          stepRef.current = 'COMPLETED'
          setLiveReport(null)
          liveReportRef.current = null
          break
        }

        case 'error':
          setError(event.message)
          closeStream()
          break

        case 'done':
          closeStream()
          break

        default:
          break
      }
    },
    [closeStream, triggerRunIfNeeded],
  )

  const beginStream = useCallback(
    async (activeThreadId: string, options: BeginStreamOptions = {}) => {
      closeStream()

      if (!options.skipBootstrap) {
        try {
          const snapshot = await fetchTaskSnapshot(activeThreadId)
          bootstrapFromApi(snapshot)
          const { status } = mapApiResponseToTaskState(snapshot)
          if (status === 'HITL_WAITING' || status === 'COMPLETED') {
            return
          }
        } catch (err: unknown) {
          const message =
            err instanceof Error ? err.message : 'Error al sincronizar estado'
          setError(message)
          return
        }
      }

      const streamOptions = options
      streamCloseRef.current = openTaskStream(
        activeThreadId,
        (event) => applyStreamEvent(event, streamOptions),
        (err) => {
          setError(err.message)
          closeStream()
        },
      )
    },
    [applyStreamEvent, bootstrapFromApi, closeStream],
  )

  const resetLiveOrchestration = useCallback(() => {
    setLogs([])
    setCurrentNode(null)
    setLiveReport(null)
    liveReportRef.current = null
    setInterimReport(undefined)
    setFinalReport(undefined)
    setReport(undefined)
    setMetricasTokens(METRICAS_TOKENS_VACIAS)
    logsRef.current = []
  }, [])

  const submitPrompt = useCallback(
    async (text: string) => {
      const prompt = text.trim()
      if (!prompt) return

      setError(null)
      setIsLoading(true)
      setSolicitud(prompt)
      setFeedItems([{ id: createFeedItemId(), kind: 'user', text: prompt }])
      setStep('PROCESSING')
      stepRef.current = 'PROCESSING'
      resetLiveOrchestration()
      closeStream()

      try {
        const snapshot = await createTask(prompt)
        const { thread_id } = snapshot
        setThreadId(thread_id)
        threadIdRef.current = thread_id
        bootstrapFromApi(snapshot)

        await beginStream(thread_id, {
          triggerExecute: true,
          skipBootstrap: true,
        })
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : 'No se pudo iniciar la tarea'
        setError(message)
        setStep('IDLE')
        stepRef.current = 'IDLE'
        setFeedItems([])
        closeStream()
      } finally {
        setIsLoading(false)
      }
    },
    [beginStream, bootstrapFromApi, closeStream, resetLiveOrchestration],
  )

  const submitFeedback = useCallback(
    async (feedback: string) => {
      const texto = feedback.trim()
      const activeThreadId = threadIdRef.current
      if (!texto || !activeThreadId) return

      const optimisticId = createFeedItemId()

      setError(null)
      setIsLoading(true)
      setFeedItems((items) => [
        ...items,
        { id: optimisticId, kind: 'user', text: texto },
      ])
      setStep('PROCESSING')
      stepRef.current = 'PROCESSING'
      resetLiveOrchestration()
      closeStream()

      try {
        await sendTaskFeedback(activeThreadId, texto)
        await beginStream(activeThreadId, {
          triggerExecute: true,
          skipBootstrap: true,
        })
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : 'No se pudo enviar el feedback'
        setError(message)
        setFeedItems((items) => items.filter((item) => item.id !== optimisticId))
        setStep('HITL_WAITING')
        stepRef.current = 'HITL_WAITING'
        closeStream()
      } finally {
        setIsLoading(false)
      }
    },
    [beginStream, closeStream, resetLiveOrchestration],
  )

  useEffect(() => {
    threadIdRef.current = threadId
  }, [threadId])

  useEffect(() => () => closeStream(), [closeStream])

  return {
    step,
    threadId,
    solicitud,
    feedItems,
    logs,
    currentNode,
    liveReport,
    report,
    interimReport,
    finalReport,
    scoreCalidad,
    metricasTokens,
    waitingForFeedback,
    error,
    isLoading,
    submitPrompt,
    submitFeedback,
    setStep,
    syncFromApi,
  }
}
