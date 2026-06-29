import ReactMarkdown from 'react-markdown'

const markdownComponents = {
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="mb-3 mt-1 text-lg font-semibold text-slate-50">{children}</h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="mb-2 mt-4 text-sm font-semibold text-slate-200">{children}</h3>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="mb-3 leading-relaxed text-slate-300">{children}</p>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold text-slate-100">{children}</strong>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="mb-3 list-decimal space-y-1 pl-5 text-slate-300">{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="leading-relaxed">{children}</li>
  ),
}

export function MarkdownReport({
  content,
  variant = 'default',
}: {
  content: string
  variant?: 'default' | 'premium'
}) {
  return (
    <div
      className={
        variant === 'premium'
          ? 'rounded-xl border border-slate-700/50 bg-slate-900/40 p-5 text-sm'
          : 'text-sm'
      }
    >
      <ReactMarkdown components={markdownComponents}>{content}</ReactMarkdown>
    </div>
  )
}
