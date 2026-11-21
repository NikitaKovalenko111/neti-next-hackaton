import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { accountFavorites, currentAccount, updateAccountFavorite, type Account } from '../../api/account'
import type { ChatMessage } from '../../api/messageBlocks'
import { AccountDialog } from '../../components/assistant/AccountDialog'
import { AssistantIcon, AssistantMark } from '../../components/assistant/AssistantIcon'
import { CampusArt } from '../../components/assistant/CampusArt'
import { FavoritesDialog } from '../../components/assistant/FavoritesDialog'
import { IdleSeason } from '../../components/assistant/IdleSeason'
import { MessageBubble } from '../../components/assistant/MessageBubble'
import { ProjectHeader, universityUrl } from '../../components/project-header/ProjectHeader'
import {
  assistantActions,
  requestAnswer,
} from '../../redux/assistantSlice'
import type { AppDispatch, RootState } from '../../redux/store'
import { canSaveFavorite, favoritesKey, loadFavorites, snapshotFavorite, writeFavorites } from './favorites'

const prompts = [
  { label: 'Поступление', question: 'Что нужно для поступления на бакалавриат?', icon: 'cap' },
  { label: 'Учебный план', question: 'Где найти учебный план моей программы?', icon: 'book' },
  { label: 'Как добраться', question: 'Как добраться до главного корпуса УУНиТ?', icon: 'pin' },
] as const

const audienceLabels = {
  unknown: 'Профиль уточняется',
  applicant: 'Абитуриент',
  student: 'Студент',
}

const accountChangeKey = 'uust-account-change'

interface AccountFavorites {
  accountId: string
  messages: ChatMessage[] | null
  error?: boolean
}

export function AssistantPage() {
  const dispatch = useDispatch<AppDispatch>()
  const { account, messages, sessionId, status, error, pendingMessageId } = useSelector(
    (state: RootState) => state.assistant,
  )
  const [draft, setDraft] = useState('')
  const [guestFavorites, setGuestFavorites] = useState(loadFavorites)
  const [guestFavoriteError, setGuestFavoriteError] = useState(false)
  const [savedFavorites, setSavedFavorites] = useState<AccountFavorites | null>(null)
  const [favoriteRefresh, setFavoriteRefresh] = useState(0)
  const [accountReady, setAccountReady] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
  const transcriptRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const favoritesDialogRef = useRef<HTMLDialogElement>(null)
  const accountDialogRef = useRef<HTMLDialogElement>(null)
  const favoriteWrites = useRef(new Set<string>())
  const accountId = account?.id
  const scopedFavorites = savedFavorites?.accountId === accountId ? savedFavorites : null
  const favorites = accountId ? scopedFavorites?.messages ?? [] : guestFavorites
  const favoriteError = accountId ? Boolean(scopedFavorites?.error) : guestFavoriteError
  const favoriteIds = new Set(favorites.map(({ id }) => id))
  const hasMessages = messages.length > 0
  const isLoading = status === 'loading'
  const canSend = accountReady && !isLoading && pendingMessageId === null
  const audience = messages.findLast((message) => message.role === 'assistant')
    ?.blocks.find((block) => block.type === 'text')?.audience ?? 'unknown'

  useEffect(() => {
    const transcript = transcriptRef.current
    if (transcript) transcript.scrollTop = transcript.scrollHeight
  }, [messages.length, status])

  useEffect(() => {
    let controller: AbortController | undefined
    function refreshSession() {
      controller?.abort()
      const connection = new AbortController()
      controller = connection
      void currentAccount(connection.signal).then((account) => {
        if (!connection.signal.aborted) {
          dispatch(assistantActions.accountChanged({ account, sessionId: crypto.randomUUID() }))
        }
      }).catch(() => undefined).finally(() => {
        if (!connection.signal.aborted) setAccountReady(true)
      })
    }
    function syncFavorites(event: StorageEvent) {
      if (event.key === favoritesKey || event.key === null) setGuestFavorites(loadFavorites())
      if (event.key === accountChangeKey) refreshSession()
    }

    refreshSession()
    window.addEventListener('storage', syncFavorites)
    return () => {
      controller?.abort()
      window.removeEventListener('storage', syncFavorites)
    }
  }, [dispatch])

  useEffect(() => {
    if (!accountId) return
    const controller = new AbortController()
    void accountFavorites(accountId, controller.signal).then((messages) => {
      if (!controller.signal.aborted) setSavedFavorites({ accountId, messages })
    }).catch(() => {
      if (!controller.signal.aborted) setSavedFavorites({ accountId, messages: null, error: true })
    })
    return () => controller.abort()
  }, [accountId, favoriteRefresh])

  async function changeFavorite(message: ChatMessage, shouldSave: boolean) {
    if (accountId) {
      const key = `${accountId}/${message.id}`
      if (favoriteWrites.current.has(key) || !scopedFavorites?.messages) return false
      favoriteWrites.current.add(key)
      try {
        await updateAccountFavorite(accountId, message.id, shouldSave)
        setSavedFavorites((current) => {
          if (current?.accountId !== accountId || !current.messages) return current
          const others = current.messages.filter(({ id }) => id !== message.id)
          return { accountId, messages: shouldSave ? [snapshotFavorite(message), ...others] : others }
        })
        return true
      } catch {
        setSavedFavorites((current) => current?.accountId === accountId ? { ...current, error: true } : current)
        return false
      } finally {
        favoriteWrites.current.delete(key)
      }
    }
    const others = loadFavorites().filter(({ id }) => id !== message.id)
    const updated = shouldSave ? [snapshotFavorite(message), ...others] : others

    try {
      writeFavorites(updated)
      setGuestFavorites(updated)
      setGuestFavoriteError(false)
      return true
    } catch {
      setGuestFavoriteError(true)
      return false
    }
  }

  function focusComposerOnDesktop() {
    if (window.matchMedia('(pointer: coarse)').matches) {
      composerRef.current?.blur()
    } else {
      composerRef.current?.focus({ preventScroll: true })
    }
  }

  function submitPrompt(value: string) {
    const content = value.trim()
    if (!content || !canSend) return

    dispatch(
      assistantActions.addUserMessage({
        id: crypto.randomUUID(),
        role: 'user',
        blocks: [{ type: 'text', message: content }],
      }),
    )
    dispatch(requestAnswer(sessionId))
    setDraft('')
    focusComposerOnDesktop()
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submitPrompt(draft)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submitPrompt(draft)
    }
  }

  function startNewSession() {
    dispatch(assistantActions.startNewSession(crypto.randomUUID()))
    setDraft('')
    focusComposerOnDesktop()
  }

  function changeAccount(current: Account | null) {
    dispatch(assistantActions.accountChanged({ account: current, sessionId: crypto.randomUUID() }))
    setSavedFavorites(null)
    setDraft('')
    try {
      localStorage.setItem(accountChangeKey, crypto.randomUUID())
    } catch {
      // The session cookie still works when browser storage is disabled.
    }
  }

  function restoreChat(owner: string, chatId: string, messages: ChatMessage[]) {
    const sessionId = crypto.randomUUID()
    dispatch(assistantActions.restoreChat({ accountId: owner, sessionId, chatId, messages }))
    if (messages.at(-1)?.role === 'user') dispatch(requestAnswer(sessionId))
    setDraft('')
  }

  return (
    <div className="assistant-app">
      <ProjectHeader
        profileLabel={audienceLabels[audience]}
        signedIn={Boolean(account)}
        accountReady={accountReady}
        onNewChat={startNewSession}
        onOpenFavorites={() => {
          if (accountId && scopedFavorites?.error && !scopedFavorites.messages) setFavoriteRefresh((previous) => previous + 1)
          favoritesDialogRef.current?.showModal()
        }}
        onOpenAccount={() => {
          accountDialogRef.current?.showModal()
          setAccountOpen(true)
        }}
      />
      <main className={hasMessages ? 'assistant-main' : 'assistant-main assistant-main--welcome'}>
        <div
          className="assistant-content"
          key={hasMessages ? 'conversation' : 'welcome'}
          ref={hasMessages ? transcriptRef : undefined}
        >
          {hasMessages ? (
            <div className="message-list content-width" role="log" aria-label="Диалог">
              {messages.map((message) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  onFollowUp={submitPrompt}
                  isLoading={!canSend}
                  isFavorite={favoriteIds.has(message.id)}
                  onToggleFavorite={canSaveFavorite(message) && (!accountId || scopedFavorites?.messages)
                    ? () => { void changeFavorite(message, !favoriteIds.has(message.id)) }
                    : undefined}
                />
              ))}
              {isLoading && (
                <div className="message-row assistant-row" role="status" aria-label="Помощник готовит ответ">
                  <AssistantMark />
                  <div className="typing-indicator" aria-hidden="true"><i /><i /><i /></div>
                </div>
              )}
            </div>
          ) : (
            <div className="welcome-panel content-width">
              <section className="welcome-hero" aria-labelledby="welcome-title">
                <div className="welcome-copy">
                  <h1 id="welcome-title">Спросите<br />про УУНиТ</h1>
                  <p className="welcome-description">Поступление, учёба<br />и студенческая жизнь</p>
                </div>
                <CampusArt />
              </section>
            </div>
          )}
        </div>

        <div className="composer-area content-width">
          {favoriteError && <p className="favorite-error" role="alert">Не удалось обновить избранное.</p>}
          {error && (
            <div className="request-error" role="alert">
              <span>{error}</span>
              <button onClick={() => dispatch(requestAnswer(sessionId))} type="button">
                Повторить
              </button>
            </div>
          )}
          <form className="composer" onSubmit={handleSubmit}>
            <textarea
              ref={composerRef}
              aria-label="Ваш вопрос"
              enterKeyHint="send"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Задайте вопрос об УУНиТ"
              rows={1}
              value={draft}
            />
            <button aria-label="Отправить" className="send-button" disabled={!draft.trim() || !canSend} type="submit">
              <span>Отправить</span>
              <AssistantIcon name="send" />
            </button>
          </form>
          {!hasMessages && (
            <section className="prompt-grid" aria-label="Готовые вопросы">
              {prompts.map(({ label, question, icon }) => (
                <button className="prompt-card" key={label} onClick={() => submitPrompt(question)} type="button">
                  <AssistantIcon name={icon} />
                  <span>{label}</span>
                </button>
              ))}
            </section>
          )}
          <nav aria-label="Полезные ссылки УУНиТ" className="welcome-links">
            <a href={universityUrl + 'admission/'} target="_blank" rel="noreferrer">Приёмная комиссия</a>
            <a href={universityUrl + 'digital-services/'} target="_blank" rel="noreferrer">Сервисы УУНиТ</a>
          </nav>
        </div>
      </main>
      <FavoritesDialog
        dialogRef={favoritesDialogRef}
        favorites={favorites}
        hasError={favoriteError}
        isLoading={Boolean(accountId && !scopedFavorites)}
        onRemove={(message) => changeFavorite(message, false)}
      />
      <AccountDialog
        dialogRef={accountDialogRef}
        open={accountOpen}
        account={account}
        onClose={() => setAccountOpen(false)}
        onAccountChange={changeAccount}
        onChat={restoreChat}
      />
      {!isLoading && <IdleSeason />}
    </div>
  )
}
