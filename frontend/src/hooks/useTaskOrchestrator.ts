import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchTaskSnapshot,
  mapApiResponseToTaskState,
  sendTaskFeedback,
  startTask,
} from '../services/api'
import type { ApiTareaResponse, ScreenStep, TaskState } from '../types/task'

const POLL_INTERVAL_MS = 6000

type UseTaskOrchestratorResult = {
  step: ScreenStep
  threadId: string | null
  solicitud: string
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

export function useTaskOrchestrator(): UseTaskOrchestratorResult {
  const [step, setStep] = useState<ScreenStep>('IDLE')
  const [threadId, setThreadId] = useState<string | null>(null)
  const [solicitud, setSolicitud] = useState('')
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
  }, [])

  const syncFromApi = useCallback(
    (response: ApiTareaResponse) => {
      setScoreCalidad(response.score_calidad)
      applyTaskState(mapApiResponseToTaskState(response))
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

  const submitPrompt = useCallback(
    async (text: string) => {
      const prompt = text.trim()
      if (!prompt) return

      setError(null)
      setIsLoading(true)
      setSolicitud(prompt)
      setStep('PROCESSING')
      setLogs([])
      setCurrentNode(null)
      setInterimReport(undefined)
      setFinalReport(undefined)
      setReport(undefined)
      stopPolling()

      try {
        const { thread_id } = await startTask(prompt)
        setThreadId(thread_id)
        threadIdRef.current = thread_id

        // El polling es la única fuente de verdad del estado remoto.
        beginPolling(thread_id)
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : 'No se pudo iniciar la tarea'
        setError(message)
        setStep('IDLE')
        stopPolling()
      } finally {
        setIsLoading(false)
      }
    },
    [beginPolling, stopPolling],
  )

  const submitFeedback = useCallback(
    async (feedback: string) => {
      const texto = feedback.trim()
      const activeThreadId = threadIdRef.current
      if (!texto || !activeThreadId) return

      setError(null)
      setIsLoading(true)
      setStep('PROCESSING')
      stopPolling()

      try {
        await sendTaskFeedback(activeThreadId, texto)
        beginPolling(activeThreadId)
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : 'No se pudo enviar el feedback'
        setError(message)
        setStep('HITL_WAITING')
        stopPolling()
      } finally {
        setIsLoading(false)
      }
    },
    [beginPolling, stopPolling],
  )

  useEffect(() => {
    threadIdRef.current = threadId
  }, [threadId])

  useEffect(() => () => stopPolling(), [stopPolling])

  return {
    step,
    threadId,
    solicitud,
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
