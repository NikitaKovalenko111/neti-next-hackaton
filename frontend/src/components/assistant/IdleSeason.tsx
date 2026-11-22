import { useEffect, useState, type CSSProperties } from 'react'
import blossom from '../../assets/idle-blossom.webp'
import butterfly from '../../assets/idle-butterfly.webp'
import leaf from '../../assets/idle-leaf.webp'
import snowflake from '../../assets/idle-snowflake.webp'

type Season = 'winter' | 'spring' | 'summer' | 'autumn'

const idleDelay = 20_000
const activityEvents = ['pointermove', 'pointerdown', 'keydown', 'input', 'wheel', 'scroll', 'focusin']

const fallingEffects = {
  winter: { image: snowflake, count: 10 },
  spring: { image: blossom, count: 7 },
  autumn: { image: leaf, count: 8 },
}

const fallingParticles = [
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

function currentSeason(): Season {
  const month = new Date().getMonth() + 1
  if (month >= 3 && month <= 5) return 'spring'
  if (month >= 6 && month <= 8) return 'summer'
  if (month >= 9 && month <= 11) return 'autumn'
  return 'winter'
}

function FlyingButterfly() {
  return (
    <div className="idle-butterfly-route">
      <div className="idle-butterfly">
        <img alt="" className="butterfly-wing butterfly-wing-left" draggable={false} src={butterfly} />
        <img alt="" className="butterfly-wing butterfly-wing-right" draggable={false} src={butterfly} />
        <img alt="" className="butterfly-body" draggable={false} src={butterfly} />
      </div>
    </div>
  )
}

export function IdleSeason() {
  const [season, setSeason] = useState<Season | null>(null)
  const isAnimating = season !== null

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
        setSeason(currentSeason())
      }
    }

    function recordActivity() {
      lastActivity = performance.now()
      if (timer !== undefined) return

      setSeason(null)
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

  useEffect(() => {
    if (!isAnimating) return

    // Browsers do not emit an event when the device clock changes.
    const clock = window.setInterval(
      () => setSeason((activeSeason) => activeSeason && currentSeason()),
      1_000,
    )
    return () => window.clearInterval(clock)
  }, [isAnimating])

  if (!season) return null

  if (season === 'summer') {
    return (
      <div aria-hidden="true" className="idle-season" data-season={season} key={season}>
        <FlyingButterfly />
        <FlyingButterfly />
      </div>
    )
  }

  const { image, count } = fallingEffects[season]
  return (
    <div aria-hidden="true" className="idle-season" data-season={season} key={season}>
      {fallingParticles.slice(0, count).map(([position, size, duration, delay, drift]) => (
        <img
          alt=""
          className="idle-particle"
          draggable={false}
          key={position}
          src={image}
          style={{
            left: `${position}%`,
            '--particle-size': `${size}px`,
            '--particle-duration': `${duration}s`,
            '--particle-delay': `${delay}s`,
            '--particle-drift': `${drift}px`,
          } as CSSProperties}
        />
      ))}
    </div>
  )
}
