import { useCallback, useLayoutEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { ArrowUp, Play } from 'lucide-react'
import type { ScreenStep } from '../types'
import { EJEMPLO_SOLICITUD } from '../constants'
import { cn } from '../lib/utils'
import { scrollTextareaCaretIntoView } from '../utils/textareaCaret'
import { ScrollArea } from './ui/scroll-area'

type ChatComposerProps = {
  step: ScreenStep
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  variant: 'hero' | 'dock'
  disabled?: boolean
}

function getPlaceholder(step: ScreenStep, variant: 'hero' | 'dock'): string {
  if (variant === 'hero') return EJEMPLO_SOLICITUD
  if (step === 'HITL_WAITING') {
    return "Escribe 'sí' para aprobar o indica tus correcciones..."
  }
  if (step === 'COMPLETED') return 'Inicia una nueva consulta desde el sidebar…'
  if (step === 'PROCESSING') return 'Orquestación en curso…'
  return 'Escribe tu mensaje…'
}

function isInputDisabled(
  step: ScreenStep,
  variant: 'hero' | 'dock',
  disabled?: boolean,
): boolean {
  if (disabled) return true
  if (variant === 'hero') return false
  return step === 'PROCESSING' || step === 'COMPLETED'
}

export function ChatComposer({
  step,
  value,
  onChange,
  onSubmit,
  variant,
  disabled: disabledProp,
}: ChatComposerProps) {
  const disabled = isInputDisabled(step, variant, disabledProp)
  const isHero = variant === 'hero'
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const syncTextareaLayout = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${el.scrollHeight}px`
    scrollTextareaCaretIntoView(el)
  }, [])

  useLayoutEffect(() => {
    syncTextareaLayout()
  }, [value, variant, syncTextareaLayout])

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value)
    requestAnimationFrame(syncTextareaLayout)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !disabled && value.trim()) {
      e.preventDefault()
      onSubmit()
    }
  }

  const handleCaretMove = () => {
    requestAnimationFrame(syncTextareaLayout)
  }

  return (
    <motion.div
      layoutId="chat-composer"
      transition={{ type: 'spring', damping: 30, stiffness: 280 }}
      className={
        isHero
          ? 'w-full max-w-2xl'
          : 'mx-auto w-full max-w-3xl px-4 pb-4 pt-2'
      }
    >
      {isHero && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 space-y-2 text-center"
        >
          <h2 className="text-3xl font-semibold tracking-tight text-slate-50">
            ¿Qué necesitas investigar hoy?
          </h2>
          <p className="text-sm text-slate-400">
            Un feed continuo de orquestación multi-agente
          </p>
        </motion.div>
      )}

      <div
        className={`overflow-hidden rounded-2xl border bg-slate-900/80 shadow-xl backdrop-blur-sm ${
          isHero
            ? 'border-slate-700/80 shadow-black/20'
            : 'border-slate-700/60 shadow-black/40 ring-1 ring-slate-800/80'
        }`}
      >
        <ScrollArea
          type="auto"
          className={cn('w-full', isHero ? 'h-36' : 'h-24')}
        >
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onKeyUp={handleCaretMove}
            onClick={handleCaretMove}
            onSelect={handleCaretMove}
            disabled={disabled}
            placeholder={getPlaceholder(step, variant)}
            rows={isHero ? 5 : 2}
            className={cn(
              'block w-full resize-none overflow-hidden bg-transparent px-4 pr-3 text-sm leading-relaxed whitespace-pre-wrap break-words text-slate-100 placeholder:text-slate-500 outline-none disabled:cursor-not-allowed disabled:opacity-50',
              isHero ? 'min-h-[7.5rem] py-4' : 'min-h-[3.25rem] py-3',
            )}
          />
        </ScrollArea>
        <div
          className={`flex items-center justify-between border-t border-slate-800/80 px-3 ${
            isHero ? 'py-3' : 'py-2'
          }`}
        >
          <span className="text-[11px] text-slate-500">
            {isHero ? 'Enter para iniciar' : 'Shift+Enter nueva línea'}
          </span>
          <button
            type="button"
            onClick={onSubmit}
            disabled={disabled || !value.trim()}
            className={`flex items-center justify-center gap-2 rounded-xl bg-violet-600 font-medium text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40 ${
              isHero ? 'px-4 py-2 text-sm' : 'h-9 w-9 p-0'
            }`}
          >
            {isHero ? (
              <>
                <Play className="h-4 w-4" />
                Iniciar
              </>
            ) : (
              <ArrowUp className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
    </motion.div>
  )
}
