import { AssistantIcon } from '../assistant/AssistantIcon'
import { ThemeToggle } from './ThemeToggle'
import { UniversityMark } from './UniversityMark'

export const universityUrl = 'https://uust.ru/'

export function ProjectHeader({ profileLabel, signedIn, onNewChat, onOpenFavorites, onOpenAccount }: {
  profileLabel: string
  signedIn: boolean
  onNewChat: () => void
  onOpenFavorites: () => void
  onOpenAccount: () => void
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
        <div className="topbar-status">
          <div className="profile-status" role="status">{profileLabel}</div>
          <button aria-haspopup="dialog" className="favorites-button" onClick={onOpenFavorites} type="button">
            <AssistantIcon name="star" />
            Избранное
          </button>
          <button aria-haspopup="dialog" className="favorites-button account-button" onClick={onOpenAccount} type="button">
            <AssistantIcon name="user" />
            {signedIn ? 'Аккаунт' : 'Войти'}
          </button>
        </div>
        <ThemeToggle />
      </div>
    </header>
  )
}
