import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { AssistantIcon, AssistantMark } from '../../components/assistant/AssistantIcon'
import { CampusArt } from '../../components/assistant/CampusArt'
import { IdleSeason } from '../../components/assistant/IdleSeason'
import { MessageBubble } from '../../components/assistant/MessageBubble'
import { ProjectHeader, universityUrl } from '../../components/project-header/ProjectHeader'
import {
  assistantActions,
  requestAnswer,
} from '../../redux/assistantSlice'
import type { AppDispatch, RootState } from '../../redux/store'

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

export function AssistantPage() {
  const dispatch = useDispatch<AppDispatch>()
  const { messages, sessionId, status, error, pendingMessageId } = useSelector(
    (state: RootState) => state.assistant,
  )
  const [draft, setDraft] = useState('')
  const transcriptRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const hasMessages = messages.length > 0
  const isLoading = status === 'loading'
  const canSend = !isLoading && pendingMessageId === null
  const audience = messages.findLast((message) => message.role === 'assistant')
    ?.blocks.find((block) => block.type === 'text')?.audience ?? 'unknown'

  useEffect(() => {
    const transcript = transcriptRef.current
    if (transcript) transcript.scrollTop = transcript.scrollHeight
  }, [messages.length, status])

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

  return (
    <div className="assistant-app">
      <ProjectHeader profileLabel={audienceLabels[audience]} onNewChat={startNewSession} />
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
      {!isLoading && <IdleSeason />}
    </div>
  )
}
