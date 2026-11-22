import { useEffect, useState, type FormEvent, type RefObject } from 'react'
import { accountChat, accountChats, accountError, authenticate, logout, type Account, type SavedChat } from '../../api/account'
import type { ChatMessage } from '../../api/messageBlocks'
import { AssistantIcon } from './AssistantIcon'

const chatDate = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'medium' })

function SavedChats({ account, busy, onOpen }: {
  account: Account
  busy: boolean
  onOpen: (chat: SavedChat) => void
}) {
  const [chats, setChats] = useState<SavedChat[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    void accountChats(account.id, controller.signal).then(setChats).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(accountError(cause, 'Не удалось загрузить историю.'))
    })
    return () => controller.abort()
  }, [account.id])

  return (
    <section className="account-history" aria-labelledby="account-history-title">
      <h3 id="account-history-title">История диалогов</h3>
      {error ? <p role="alert">{error}</p> : chats === null ? <p role="status">Загружаем историю…</p> :
        chats.length === 0 ? <p>Новые диалоги будут сохраняться здесь.</p> : (
          <ul>
            {chats.map((chat) => (
              <li key={chat.chat_id}>
                <button disabled={busy} onClick={() => onOpen(chat)} type="button">
                  <span>Диалог</span>
                  <time dateTime={chat.created_at}>{chatDate.format(new Date(chat.created_at))}</time>
                </button>
              </li>
            ))}
          </ul>
        )}
    </section>
  )
}

export function AccountDialog({ dialogRef, account, open, onClose, onAccountChange, onChat }: {
  dialogRef: RefObject<HTMLDialogElement | null>
  account: Account | null
  open: boolean
  onClose: () => void
  onAccountChange: (account: Account | null) => void
  onChat: (accountId: string, chatId: string, messages: ChatMessage[]) => void
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const title = account ? 'Личный кабинет' : mode === 'register' ? 'Создать аккаунт' : 'Войти в аккаунт'

  async function run(action: () => Promise<void>, fallback: string) {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (cause) {
      setError(accountError(cause, fallback))
    } finally {
      setBusy(false)
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    void run(async () => {
      const current = await authenticate(mode, String(form.get('username')), String(form.get('password')))
      onAccountChange(current)
    }, 'Не удалось войти. Проверьте подключение и попробуйте ещё раз.')
  }

  function selectChat(chat: SavedChat) {
    if (!account) return
    void run(async () => {
      const messages = await accountChat(account.id, chat.chat_id, AbortSignal.timeout(20000))
      onChat(account.id, chat.chat_id, messages)
      dialogRef.current?.close()
    }, 'Не удалось открыть диалог. Попробуйте ещё раз.')
  }

  function signOut() {
    void run(async () => {
      await logout()
      onAccountChange(null)
      dialogRef.current?.close()
    }, 'Не удалось выйти. Проверьте подключение и попробуйте ещё раз.')
  }

  return (
    <dialog
      aria-labelledby="account-title"
      className="account-dialog"
      ref={dialogRef}
      onCancel={(event) => { if (busy) event.preventDefault() }}
      onClose={() => { setMode('login'); setError(''); onClose() }}
    >
      <header className="favorites-heading">
        <h2 id="account-title">{title}</h2>
        <button aria-label="Закрыть" className="favorites-close" disabled={busy} onClick={() => dialogRef.current?.close()} type="button">
          <AssistantIcon name="close" />
        </button>
      </header>
      {open && (
        <div className="account-body" aria-busy={busy}>
          {account ? (
            <>
              <div className="account-profile">
                <span><AssistantIcon name="user" /> {account.username}</span>
                <button className="account-secondary" disabled={busy} onClick={signOut} type="button">Выйти</button>
              </div>
              <SavedChats key={account.id} account={account} busy={busy} onOpen={selectChat} />
            </>
          ) : (
            <>
              <p>Войдите, чтобы открывать сохранённые диалоги на другом устройстве.</p>
              <form className="account-form" onSubmit={submit}>
                <label>Логин
                  <input autoComplete="username" autoCapitalize="none" maxLength={32} name="username" pattern="[A-Za-z0-9_]{3,32}" required />
                </label>
                <label>Пароль
                  <input autoComplete={mode === 'register' ? 'new-password' : 'current-password'} name="password" required type="password" />
                </label>
                {mode === 'register' && <p className="account-hint">Логин из 3–32 латинских букв, цифр или подчёркиваний. Пароль от 8 до 72 байт.</p>}
                <button className="new-chat-button" disabled={busy} type="submit">{busy ? 'Подождите…' : mode === 'register' ? 'Создать аккаунт' : 'Войти'}</button>
              </form>
              <div className="account-actions">
                <button className="account-secondary" disabled={busy} onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }} type="button">
                  {mode === 'login' ? 'Создать аккаунт' : 'Уже есть аккаунт'}
                </button>
                <button className="account-secondary" disabled={busy} onClick={() => dialogRef.current?.close()} type="button">Продолжить без входа</button>
              </div>
            </>
          )}
          {error && <p className="favorite-error" role="alert">{error}</p>}
        </div>
      )}
    </dialog>
  )
}
