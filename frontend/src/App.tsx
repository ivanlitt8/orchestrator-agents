import { useEffect, useState } from 'react'
import { AnimatePresence, LayoutGroup, motion } from 'framer-motion'
import type { ScreenStep } from './types'
import { Header } from './components/Header'
import { Sidebar } from './components/Sidebar'
import { ChatComposer } from './components/ChatComposer'
// import { DevStepToolbar } from './components/DevStepToolbar'
import { FeedScrollContainer } from './components/FeedScrollContainer'
import { OrchestratorAvatar } from './components/OrchestratorAvatar'
import { useTaskOrchestrator } from './hooks/useTaskOrchestrator'

function App() {
  const {
    step: orchestratorStep,
    solicitud,
    feedItems,
    logs,
    currentNode,
    liveReport,
    error,
    isLoading,
    submitPrompt,
    submitFeedback,
  } = useTaskOrchestrator()

  const [devStepOverride] = useState<ScreenStep | null>(null)
  const [mensaje, setMensaje] = useState('')
  const [promptDraft, setPromptDraft] = useState('')

  const step = devStepOverride ?? orchestratorStep
  const isImmersive = step !== 'IDLE'

  useEffect(() => {
    if (orchestratorStep === 'HITL_WAITING') {
      setMensaje('')
    }
  }, [orchestratorStep])

  const handleSubmitHero = () => {
    void submitPrompt(promptDraft)
    setPromptDraft('')
  }

  const handleSubmitDock = () => {
    if (!mensaje.trim() || step !== 'HITL_WAITING') return
    void submitFeedback(mensaje).then(() => setMensaje(''))
  }

  const composerValue = isImmersive ? mensaje : promptDraft
  const composerOnChange = isImmersive ? setMensaje : setPromptDraft
  const composerOnSubmit = isImmersive ? handleSubmitDock : handleSubmitHero
  const composerDisabled = isLoading && devStepOverride === null

  return (
    <LayoutGroup id="orchestrator-chat">
      <div className="flex h-screen flex-col overflow-hidden bg-slate-950 font-sans text-slate-100">
        <Header step={step} />

        {error && (
          <div className="border-b border-red-500/30 bg-red-500/10 px-4 py-2 text-center text-xs text-red-200">
            {error}
          </div>
        )}

        <div className="relative flex min-h-0 flex-1">
          <AnimatePresence>
            {isImmersive && <Sidebar tituloActual={solicitud} />}
          </AnimatePresence>

          <div className="flex min-w-0 flex-1 flex-col">
            {isImmersive ? (
              <>
                <motion.main
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.3, delay: 0.1 }}
                  className="min-h-0 flex-1"
                >
                  <FeedScrollContainer
                    step={step}
                    feedItems={feedItems}
                    logs={logs}
                    currentNode={currentNode}
                    liveReport={liveReport}
                  />
                </motion.main>
                <div className="shrink-0 border-t border-slate-800/80 bg-slate-950/90 backdrop-blur-md">
                  <div className="mx-auto flex w-full max-w-3xl items-end gap-2 px-4">
                    {/* {showDockAvatar && (
                      <OrchestratorAvatar step={step} placement="dock" />
                    )} */}
                    <div className="min-w-0 flex-1">
                      <ChatComposer
                        step={step}
                        value={composerValue}
                        onChange={composerOnChange}
                        onSubmit={composerOnSubmit}
                        variant="dock"
                        disabled={composerDisabled}
                      />
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center px-6 pb-24">
                <div className="flex w-full max-w-2xl flex-col items-center">
                  <OrchestratorAvatar step={step} placement="idle" />
                  <ChatComposer
                    step={step}
                    value={composerValue}
                    onChange={composerOnChange}
                    onSubmit={composerOnSubmit}
                    variant="hero"
                    disabled={composerDisabled}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
{/* 
        {import.meta.env.DEV && (
          <DevStepToolbar step={step} onStepChange={setDevStepOverride} />
        )} */}
      </div>
    </LayoutGroup>
  )
}

export default App
