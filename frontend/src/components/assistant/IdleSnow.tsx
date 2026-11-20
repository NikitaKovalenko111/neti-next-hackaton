import { useEffect, useState, type CSSProperties } from 'react'
import snowflake from '../../assets/idle-snowflake.webp'

const idleDelay = 20_000
const activityEvents = ['pointermove', 'pointerdown', 'keydown', 'input', 'wheel', 'scroll', 'focusin']

const flakes = [
  [9, 34, 16, 0, -22],
  [46, 24, 19, .25, 28],
  [86, 39, 15, .6, -30],
  [23, 27, 22, 1.2, 47],
  [68, 32, 18, 1.8, -45],
  [33, 21, 17, 2.5, -24],
  [95, 23, 23, 3.1, -31],
  [58, 35, 21, 4, 34],
  [15, 19, 20, 5.4, 36],
  [77, 28, 24, 6.3, 26],
] as const

export function IdleSnow() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    let lastActivity = performance.now()
    let timer: number | undefined

    function checkIdle() {
      timer = undefined
      if (document.hidden || reducedMotion.matches) return

      const remaining = idleDelay - (performance.now() - lastActivity)
      if (remaining > 0) {
        timer = window.setTimeout(checkIdle, remaining)
      } else {
        setVisible(true)
      }
    }

    function recordActivity() {
      lastActivity = performance.now()
      if (timer !== undefined) return

      setVisible(false)
      if (!document.hidden && !reducedMotion.matches) {
        timer = window.setTimeout(checkIdle, idleDelay)
      }
    }

    function resetTimer() {
      window.clearTimeout(timer)
      timer = undefined
      recordActivity()
    }

    activityEvents.forEach((event) => {
      window.addEventListener(event, recordActivity, { capture: true, passive: true })
    })
    document.addEventListener('visibilitychange', resetTimer)
    reducedMotion.addEventListener('change', resetTimer)
    recordActivity()

    return () => {
      window.clearTimeout(timer)
      activityEvents.forEach((event) => window.removeEventListener(event, recordActivity, true))
      document.removeEventListener('visibilitychange', resetTimer)
      reducedMotion.removeEventListener('change', resetTimer)
    }
  }, [])

  if (!visible) return null

  return (
    <div aria-hidden="true" className="idle-snow">
      {flakes.map(([position, size, duration, delay, drift]) => (
        <img
          alt=""
          className="idle-snowflake"
          draggable={false}
          key={position}
          src={snowflake}
          style={{
            left: `${position}%`,
            '--flake-size': `${size}px`,
            '--flake-duration': `${duration}s`,
            '--flake-delay': `${delay}s`,
            '--flake-drift': `${drift}px`,
          } as CSSProperties}
        />
      ))}
    </div>
  )
}
