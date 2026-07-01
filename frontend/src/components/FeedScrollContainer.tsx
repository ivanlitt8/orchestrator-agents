import { useEffect, useLayoutEffect, useRef } from 'react'

import type { FeedItem, ScreenStep } from '../types'
import { ChatFeed } from './ChatFeed'
import { ScrollArea } from './ui/scroll-area'
import {
  getScrollAreaViewport,
  isScrollAreaNearBottom,
  scrollAreaToBottom,
  scrollAreaToBottomAfterLayout,
} from '../utils/scrollArea'

type FeedScrollContainerProps = {
  step: ScreenStep
  feedItems: FeedItem[]
  logs: string[]
  currentNode: string | null
  liveReport?: string | null
}

export function FeedScrollContainer({
  step,
  feedItems,
  logs,
  currentNode,
  liveReport = null,
}: FeedScrollContainerProps) {
  const contentRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)
  const feedItemsCountRef = useRef(feedItems.length)

  useLayoutEffect(() => {
    const grewFeed = feedItems.length > feedItemsCountRef.current
    feedItemsCountRef.current = feedItems.length

    if (grewFeed) {
      stickToBottomRef.current = true
      scrollAreaToBottomAfterLayout(contentRef.current, { force: true })
      return
    }

    if (!stickToBottomRef.current) return

    scrollAreaToBottomAfterLayout(contentRef.current, { onlyIfNearBottom: true })
  }, [feedItems, logs, step, currentNode, liveReport])

  useEffect(() => {
    const viewport = getScrollAreaViewport(contentRef.current)
    if (!viewport) return

    const onScroll = () => {
      stickToBottomRef.current = isScrollAreaNearBottom(viewport)
    }

    onScroll()
    viewport.addEventListener('scroll', onScroll, { passive: true })
    return () => viewport.removeEventListener('scroll', onScroll)
  }, [step])

  useEffect(() => {
    const content = contentRef.current
    if (!content) return

    const observer = new ResizeObserver(() => {
      if (!stickToBottomRef.current) return
      scrollAreaToBottom(contentRef.current, { onlyIfNearBottom: true })
    })

    observer.observe(content)
    return () => observer.disconnect()
  }, [step])

  return (
    <ScrollArea type="auto" className="h-full w-full">
      <div ref={contentRef}>
        <ChatFeed
          step={step}
          feedItems={feedItems}
          logs={logs}
          currentNode={currentNode}
          liveReport={liveReport}
        />
      </div>
    </ScrollArea>
  )
}
