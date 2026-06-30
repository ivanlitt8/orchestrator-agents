import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchTaskSnapshot,
  mapApiResponseToTaskState,
  sendTaskFeedback,
  startTask,
} from '../services/api'
import type {
  ApiTareaResponse,
  FeedItem,
  ScreenStep,
  TaskState,
} from '../types/task'
import { createFeedItemId } from '../utils/feedId'

const POLL_INTERVAL_MS = 6000

type UseTaskOrchestratorResult = {
  step: ScreenStep
  threadId: string | null
  solicitud: string
  feedItems: FeedItem[]
  logs: string[]
  currentNode: string | null
  report: string | undefined
  interimReport: string | undefined
  finalReport: string | undefined
  scoreCalidad: number
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

function archiveProcessingCycle(
  items: FeedItem[],
  logs: string[],
  nextStatus: ScreenStep,
  interimReport: string | undefined,
  finalReport: string | undefined,
  scoreCalidad: number,
): FeedItem[] {
  const next = [...items, { id: createFeedItemId(), kind: 'pipeline' as const, logs: [...logs] }]

  if (nextStatus === 'HITL_WAITING' && interimReport) {
    next.push({
      id: createFeedItemId(),
      kind: 'hitl_report',
      content: interimReport,
      scoreCalidad,
    })
  }

  if (nextStatus === 'COMPLETED' && finalReport) {
    next.push({
      id: createFeedItemId(),
      kind: 'completed_report',
      content: finalReport,
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
  const [report, setReport] = useState<string | undefined>()
  const [interimReport, setInterimReport] = useState<string | undefined>()
  const [finalReport, setFinalReport] = useState<string | undefined>()
  const [scoreCalidad, setScoreCalidad] = useState(0)
  const [waitingForFeedback, setWaitingForFeedback] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const threadIdRef = useRef<string | null>(null)
  const stepRef = useRef<ScreenStep>('IDLE')
  const logsRef = useRef<string[]>([])

  const stopPolling = useCallback(() => {
    if (pollingRef.current !== null) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
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
          ),
        )
      }

      setScoreCalidad(response.score_calidad)
      applyTaskState(state)
    },
    [applyTaskState],
  )

  const pollOnce = useCallback(
    async (activeThreadId: string) => {
      const snapshot = await fetchTaskSnapshot(activeThreadId)
      const state = mapApiResponseToTaskState(snapshot)
      syncFromApi(snapshot)

      if (state.status === 'HITL_WAITING' || state.status === 'COMPLETED') {
        stopPolling()
      }
    },
    [stopPolling, syncFromApi],
  )

  const startPolling = useCallback(
    (activeThreadId: string) => {
      stopPolling()
      pollingRef.current = setInterval(() => {
        void pollOnce(activeThreadId).catch((err: unknown) => {
          const message =
            err instanceof Error ? err.message : 'Error al sincronizar estado'
          setError(message)
          stopPolling()
        })
      }, POLL_INTERVAL_MS)
    },
    [pollOnce, stopPolling],
  )

  const beginPolling = useCallback(
    (activeThreadId: string) => {
      startPolling(activeThreadId)
      void pollOnce(activeThreadId).catch((err: unknown) => {
        const message =
          err instanceof Error ? err.message : 'Error al sincronizar estado'
        setError(message)
        stopPolling()
      })
    },
    [pollOnce, startPolling, stopPolling],
  )

  const resetLiveOrchestration = useCallback(() => {
    setLogs([])
    setCurrentNode(null)
    setInterimReport(undefined)
    setFinalReport(undefined)
    setReport(undefined)
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
      stopPolling()

      try {
        const { thread_id } = await startTask(prompt)
        setThreadId(thread_id)
        threadIdRef.current = thread_id

        beginPolling(thread_id)
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : 'No se pudo iniciar la tarea'
        setError(message)
        setStep('IDLE')
        stepRef.current = 'IDLE'
        setFeedItems([])
        stopPolling()
      } finally {
        setIsLoading(false)
      }
    },
    [beginPolling, resetLiveOrchestration, stopPolling],
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
      stopPolling()

      try {
        await sendTaskFeedback(activeThreadId, texto)
        beginPolling(activeThreadId)
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : 'No se pudo enviar el feedback'
        setError(message)
        setFeedItems((items) => items.filter((item) => item.id !== optimisticId))
        setStep('HITL_WAITING')
        stepRef.current = 'HITL_WAITING'
        stopPolling()
      } finally {
        setIsLoading(false)
      }
    },
    [beginPolling, resetLiveOrchestration, stopPolling],
  )

  useEffect(() => {
    threadIdRef.current = threadId
  }, [threadId])

  useEffect(() => () => stopPolling(), [stopPolling])

  return {
    step,
    threadId,
    solicitud,
    feedItems,
    logs,
    currentNode,
    report,
    interimReport,
    finalReport,
    scoreCalidad,
    waitingForFeedback,
    error,
    isLoading,
    submitPrompt,
    submitFeedback,
    setStep,
    syncFromApi,
  }
}
