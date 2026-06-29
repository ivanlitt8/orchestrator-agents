import type { ScreenStep } from '../types'

export function DevStepToolbar({
  step,
  onStepChange,
}: {
  step: ScreenStep
  onStepChange: (step: ScreenStep) => void
}) {
  const botones: { label: string; value: ScreenStep }[] = [
    { label: 'IDLE', value: 'IDLE' },
    { label: 'PROCESSING', value: 'PROCESSING' },
    { label: 'HITL', value: 'HITL_WAITING' },
    { label: 'COMPLETED', value: 'COMPLETED' },
  ]

  return (
    <footer className="pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex justify-center px-4">
      <div className="pointer-events-auto flex items-center gap-1 rounded-full border border-slate-700/80 bg-slate-950/95 px-2 py-1.5 shadow-xl shadow-black/50 backdrop-blur-md">
        <span className="px-2 text-[10px] font-medium uppercase tracking-wider text-slate-500">
          Dev
        </span>
        {botones.map(({ label, value }) => (
          <button
            key={value}
            type="button"
            onClick={() => onStepChange(value)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              step === value
                ? 'bg-violet-600 text-white'
                : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
    </footer>
  )
}
