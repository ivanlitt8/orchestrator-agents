import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { useTypewriterWords } from '../hooks/useTypewriterWords'
import { cn } from '../lib/utils'

type MarkdownReportRendererProps = {
  content: string
  variant?: 'default' | 'premium'
  /** Desactivar en historial ya archivado para evitar re-animar al remontar. */
  enableTypewriter?: boolean
}

const proseClasses = cn(
  'prose prose-invert max-w-3xl',
  'prose-headings:font-semibold prose-headings:text-slate-50',
  'prose-h2:mb-3 prose-h2:mt-1 prose-h2:text-lg',
  'prose-h3:mb-2 prose-h3:mt-4 prose-h3:text-sm prose-h3:text-slate-200',
  'prose-p:mb-3 prose-p:leading-relaxed prose-p:text-slate-300',
  'prose-strong:font-semibold prose-strong:text-slate-100',
  'prose-ol:mb-3 prose-ol:list-decimal prose-ol:space-y-1 prose-ol:pl-5',
  'prose-li:leading-relaxed prose-li:text-slate-300',
)

export function MarkdownReportRenderer({
  content,
  variant = 'default',
  enableTypewriter = true,
}: MarkdownReportRendererProps) {
  const { displayed, isComplete } = useTypewriterWords(content, {
    enabled: enableTypewriter,
  })

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: isComplete ? 1 : 0.94 }}
      transition={{
        opacity: { duration: isComplete ? 0.45 : 0.18, ease: [0.22, 1, 0.36, 1] },
        y: { duration: 0.45, ease: [0.22, 1, 0.36, 1] },
      }}
      className={cn(
        proseClasses,
        variant === 'premium' &&
          'rounded-xl border border-slate-700/50 bg-slate-900/40 p-5 text-sm',
        variant === 'default' && 'text-sm',
      )}
    >
      <motion.div
        key={displayed.length}
        initial={{ opacity: 0.55 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.22, ease: 'easeOut' }}
      >
        <ReactMarkdown>{displayed}</ReactMarkdown>
      </motion.div>
      {!isComplete && (
        <span
          className="ml-0.5 inline-block h-[1.1em] w-0.5 translate-y-px animate-pulse bg-violet-400/90 align-middle"
          aria-hidden
        />
      )}
    </motion.div>
  )
}
