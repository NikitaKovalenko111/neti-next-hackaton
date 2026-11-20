import { AssistantIcon } from '../assistant/AssistantIcon'
import { ThemeToggle } from './ThemeToggle'

export const universityUrl = 'https://uust.ru/'

export function ProjectHeader() {
  return (
    <header className="topbar">
      <div className="topbar-context">
        <AssistantIcon name="chat" />
        <span>Университетский помощник</span>
      </div>
      <div className="topbar-actions">
        <a
          aria-label="Сайт УУНиТ"
          className="university-link"
          href={universityUrl}
          rel="noreferrer"
          target="_blank"
        >
          <AssistantIcon name="globe" />
          <span>Сайт УУНиТ</span>
        </a>
        <ThemeToggle />
      </div>
    </header>
  )
}
