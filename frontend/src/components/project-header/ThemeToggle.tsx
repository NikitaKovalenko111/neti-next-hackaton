import { useEffect, useState } from 'react'
import { AssistantIcon } from '../assistant/AssistantIcon'

const darkPreference = '(prefers-color-scheme: dark)'

export function ThemeToggle() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme)
  const [systemDark, setSystemDark] = useState(() => window.matchMedia(darkPreference).matches)
  const isDark = theme === undefined ? systemDark : theme === 'dark'

  useEffect(() => {
    const preference = window.matchMedia(darkPreference)
    const syncPreference = () => setSystemDark(preference.matches)

    preference.addEventListener('change', syncPreference)
    syncPreference()
    return () => preference.removeEventListener('change', syncPreference)
  }, [])

  useEffect(() => {
    const canvas = getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim()
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', canvas)
  }, [isDark])

  function toggleTheme() {
    const nextTheme = isDark ? 'light' : 'dark'
    document.documentElement.dataset.theme = nextTheme
    setTheme(nextTheme)
    try {
      window.localStorage.setItem('uust-theme', nextTheme)
    } catch {
      // The theme still applies in this tab if storage is unavailable.
    }
  }

  return (
    <button
      aria-label="Тёмная тема"
      aria-pressed={isDark}
      className="theme-toggle"
      onClick={toggleTheme}
      title={isDark ? 'Включить светлую тему' : 'Включить тёмную тему'}
      type="button"
    >
      <AssistantIcon name={isDark ? 'sun' : 'moon'} />
    </button>
  )
}
