import { useEffect, useState } from 'react'

type UseTypewriterWordsOptions = {
  enabled?: boolean
  msPerWord?: number
}

export function useTypewriterWords(
  text: string,
  { enabled = true, msPerWord = 42 }: UseTypewriterWordsOptions = {},
) {
  const [displayed, setDisplayed] = useState(enabled ? '' : text)
  const [isComplete, setIsComplete] = useState(!enabled)

  useEffect(() => {
    if (!enabled) {
      setDisplayed(text)
      setIsComplete(true)
      return
    }

    if (!text) {
      setDisplayed('')
      setIsComplete(true)
      return
    }

    const tokens = text.match(/\S+\s*/g) ?? []
    if (tokens.length === 0) {
      setDisplayed('')
      setIsComplete(true)
      return
    }

    let index = 0
    setDisplayed('')
    setIsComplete(false)

    const timer = window.setInterval(() => {
      index += 1
      if (index >= tokens.length) {
        setDisplayed(text)
        setIsComplete(true)
        window.clearInterval(timer)
        return
      }
      setDisplayed(tokens.slice(0, index).join(''))
    }, msPerWord)

    return () => window.clearInterval(timer)
  }, [text, enabled, msPerWord])

  return { displayed, isComplete }
}
