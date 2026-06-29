type CaretRect = {
  top: number
  height: number
}

function measureCaretRect(textarea: HTMLTextAreaElement): CaretRect {
  const style = window.getComputedStyle(textarea)
  const mirror = document.createElement('div')

  mirror.style.position = 'absolute'
  mirror.style.visibility = 'hidden'
  mirror.style.pointerEvents = 'none'
  mirror.style.top = '0'
  mirror.style.left = '-9999px'
  mirror.style.whiteSpace = 'pre-wrap'
  mirror.style.wordWrap = 'break-word'
  mirror.style.overflowWrap = 'break-word'
  mirror.style.overflow = 'hidden'
  mirror.style.width = `${textarea.clientWidth}px`
  mirror.style.font = style.font
  mirror.style.lineHeight = style.lineHeight
  mirror.style.letterSpacing = style.letterSpacing
  mirror.style.padding = style.padding
  mirror.style.border = style.border
  mirror.style.boxSizing = style.boxSizing

  const before = textarea.value.substring(0, textarea.selectionStart)
  const after = textarea.value.substring(textarea.selectionEnd)

  mirror.textContent = before
  const marker = document.createElement('span')
  marker.textContent = after.length > 0 ? after[0] : '\u200b'
  mirror.appendChild(marker)

  document.body.appendChild(mirror)
  const top = marker.offsetTop
  const height = marker.offsetHeight || parseFloat(style.lineHeight) || 20
  document.body.removeChild(mirror)

  return { top, height }
}

export function scrollTextareaCaretIntoView(textarea: HTMLTextAreaElement) {
  const viewport = textarea.closest<HTMLElement>(
    '[data-slot="scroll-area-viewport"]',
  )
  if (!viewport) return

  const { top, height } = measureCaretRect(textarea)
  const caretBottom = top + height
  const viewTop = viewport.scrollTop
  const viewBottom = viewTop + viewport.clientHeight
  const margin = 8

  if (caretBottom > viewBottom - margin) {
    viewport.scrollTop = caretBottom - viewport.clientHeight + margin
  } else if (top < viewTop + margin) {
    viewport.scrollTop = Math.max(0, top - margin)
  }
}
