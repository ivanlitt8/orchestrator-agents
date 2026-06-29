import { useCallback, useState } from 'react'
import { motion } from 'framer-motion'
import { useRive } from '@rive-app/react-canvas'
import type { ScreenStep } from '../types'

export type AvatarPlacement = 'idle' | 'processing' | 'dock'

const SPRING_LAYOUT = {
  type: 'spring' as const,
  stiffness: 140,
  damping: 12,
  mass: 0.8,
}

const SPRING_MAGNETIC = {
  type: 'spring' as const,
  stiffness: 220,
  damping: 18,
  mass: 0.4,
}

const SIZE_BY_PLACEMENT: Record<AvatarPlacement, number> = {
  idle: 150,
  processing: 52,
  dock: 64,
}

type OrchestratorAvatarProps = {
  step: ScreenStep
  placement: AvatarPlacement
}

function RiveCanvas({ size }: { size: number }) {
  const { RiveComponent } = useRive({
    src: '/orchestrator.riv',
    autoplay: true,
    animations: ['Idle', 'Floating'],
  })

  return (
    <div
      className="pointer-events-none relative"
      style={{ width: size, height: size }}
    >
      <div
        className="absolute inset-0 rounded-full bg-violet-500/20 blur-2xl"
        aria-hidden
      />
      <RiveComponent className="relative h-full w-full drop-shadow-[0_8px_24px_rgba(139,92,246,0.35)]" />
    </div>
  )
}

export function OrchestratorAvatar({ placement }: OrchestratorAvatarProps) {
  const size = SIZE_BY_PLACEMENT[placement]
  const [magnetic, setMagnetic] = useState({ x: 0, y: 0 })

  const handleMouseMove = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (placement !== 'idle') return

      const rect = event.currentTarget.getBoundingClientRect()
      const centerX = rect.left + rect.width / 2
      const centerY = rect.top + rect.height / 2
      const offsetX = (event.clientX - centerX) / (rect.width / 2)
      const offsetY = (event.clientY - centerY) / (rect.height / 2)

      setMagnetic({
        x: Math.max(-10, Math.min(10, offsetX * 10)),
        y: Math.max(-10, Math.min(10, offsetY * 10)),
      })
    },
    [placement],
  )

  const handleMouseLeave = useCallback(() => {
    setMagnetic({ x: 0, y: 0 })
  }, [])

  if (placement === 'idle') {
    return (
      <div
        className="mb-3 flex w-full max-w-2xl justify-center py-6"
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        <motion.div layoutId="orchestrator-pet" transition={SPRING_LAYOUT}>
          <motion.div
            animate={{ x: magnetic.x, y: magnetic.y }}
            transition={SPRING_MAGNETIC}
          >
            <RiveCanvas size={size} />
          </motion.div>
        </motion.div>
      </div>
    )
  }

  if (placement === 'processing') {
    return (
      <motion.div
        layoutId="orchestrator-pet"
        transition={SPRING_LAYOUT}
        className="shrink-0 self-start pt-0.5"
      >
        <RiveCanvas size={size} />
      </motion.div>
    )
  }

  return (
    <motion.div
      layoutId="orchestrator-pet"
      transition={SPRING_LAYOUT}
      className="shrink-0 self-end pb-5"
    >
      <RiveCanvas size={size} />
    </motion.div>
  )
}
