import { motion } from 'framer-motion'
import { History, MessageSquarePlus } from 'lucide-react'

type SidebarProps = {
  tituloActual?: string
}

const HISTORIAL_MOCK = [
  'Cafeterías de especialidad Mar del Plata',
  'Precios Starlink Argentina 2026',
  'Análisis fintech LatAm',
]

export function Sidebar({ tituloActual }: SidebarProps) {
  return (
    <motion.aside
      initial={{ x: -260, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: -260, opacity: 0 }}
      transition={{ type: 'spring', damping: 28, stiffness: 240 }}
      className="flex h-full w-[260px] shrink-0 flex-col border-r border-slate-800/90 bg-slate-950/95"
    >
      <div className="border-b border-slate-800/80 p-4">
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-xl border border-slate-700/80 bg-slate-900/80 px-3 py-2.5 text-sm text-slate-300 transition hover:border-violet-500/40 hover:text-slate-100"
        >
          <MessageSquarePlus className="h-4 w-4 text-violet-400" />
          Nueva consulta
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        <p className="mb-2 flex items-center gap-1.5 px-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          <History className="h-3 w-3" />
          Historial
        </p>
        <ul className="space-y-1">
          {tituloActual && (
            <li className="rounded-lg bg-violet-500/10 px-3 py-2 text-xs text-violet-200 ring-1 ring-violet-500/25">
              {tituloActual.length > 48
                ? `${tituloActual.slice(0, 48)}…`
                : tituloActual}
            </li>
          )}
          {HISTORIAL_MOCK.map((item) => (
            <li
              key={item}
              className="cursor-pointer rounded-lg px-3 py-2 text-xs text-slate-400 transition hover:bg-slate-800/60 hover:text-slate-200"
            >
              {item}
            </li>
          ))}
        </ul>
      </div>
    </motion.aside>
  )
}
