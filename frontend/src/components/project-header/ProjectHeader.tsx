import { AssistantIcon } from '../assistant/AssistantIcon'
import { ThemeToggle } from './ThemeToggle'
import { UniversityMark } from './UniversityMark'

export const universityUrl = 'https://uust.ru/'

export function ProjectHeader({ profileLabel, onNewChat }: {
  profileLabel: string
  onNewChat: () => void
}) {
  return (
    <header className="topbar">
      <div className="topbar-inner content-width">
        <a
          aria-label="Уфимский университет науки и технологий — официальный сайт"
          className="brand"
          href={universityUrl}
          rel="noreferrer"
          target="_blank"
        >
          <UniversityMark className="brand-symbol" />
          <span>УУНиТ</span>
        </a>
        <button className="new-chat-button" onClick={onNewChat} type="button">
          <AssistantIcon name="plus" />
          Новый диалог
        </button>
        <div className="profile-status" role="status">{profileLabel}</div>
        <ThemeToggle />
      </div>
    </header>
  )
}
