const NEAR_BOTTOM_THRESHOLD_PX = 48

export function getScrollAreaViewport(
  contentEl: HTMLElement | null,
): HTMLElement | null {
  return (
    contentEl?.closest<HTMLElement>('[data-slot="scroll-area-viewport"]') ?? null
  )
}

export function isScrollAreaNearBottom(
  viewport: HTMLElement | null,
  threshold = NEAR_BOTTOM_THRESHOLD_PX,
): boolean {
  if (!viewport) return true

  const { scrollTop, scrollHeight, clientHeight } = viewport
  return scrollTop + clientHeight >= scrollHeight - threshold
}

type ScrollAreaToBottomOptions = {
  /** Solo desplaza si el viewport ya estaba cerca del fondo. */
  onlyIfNearBottom?: boolean
  /** Ignora la comprobación de proximidad al fondo. */
  force?: boolean
}

export function scrollAreaToBottom(
  contentEl: HTMLElement | null,
  options?: ScrollAreaToBottomOptions,
) {
  const viewport = getScrollAreaViewport(contentEl)
  if (!viewport) return

  if (options?.onlyIfNearBottom && !options.force) {
    if (!isScrollAreaNearBottom(viewport)) return
  }

  viewport.scrollTop = viewport.scrollHeight - viewport.clientHeight
}

export function scrollAreaToBottomAfterLayout(
  contentEl: HTMLElement | null,
  options?: ScrollAreaToBottomOptions,
) {
  requestAnimationFrame(() => {
    scrollAreaToBottom(contentEl, options)
    requestAnimationFrame(() => scrollAreaToBottom(contentEl, options))
  })
}
