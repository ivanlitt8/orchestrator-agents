export function scrollAreaToBottom(contentEl: HTMLElement | null) {
  if (!contentEl) return

  const viewport = contentEl.closest<HTMLElement>(
    '[data-slot="scroll-area-viewport"]',
  )
  if (!viewport) return

  viewport.scrollTop = viewport.scrollHeight - viewport.clientHeight
}
