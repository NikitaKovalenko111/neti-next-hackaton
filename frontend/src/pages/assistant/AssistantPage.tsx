import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import campusOrbit from '../../assets/campus-orbit.webp'
import { AssistantIcon, AssistantMark } from '../../components/assistant/AssistantIcon'
import { IdleSeason } from '../../components/assistant/IdleSeason'
import { MessageBubble } from '../../components/assistant/MessageBubble'
import { ProjectHeader, universityUrl } from '../../components/project-header/ProjectHeader'
import { UniversityMark } from '../../components/project-header/UniversityMark'
import {
  assistantActions,
  requestAnswer,
} from '../../redux/assistantSlice'
import type { AppDispatch, RootState } from '../../redux/store'

const prompts = [
  { label: 'Поступление', question: 'Что нужно для поступления на бакалавриат?', icon: 'cap' },
  { label: 'Учебный план', question: 'Где найти учебный план моей программы?', icon: 'book' },
  { label: 'Как добраться', question: 'Покажи, как добраться до главного корпуса УУНиТ.', icon: 'globe' },
] as const

const audienceLabels = {
  unknown: 'Определю по сообщениям',
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
    composerRef.current?.focus({ preventScroll: true })
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
    composerRef.current?.focus({ preventScroll: true })
  }

  return (
    <div className={hasMessages ? 'assistant-app has-messages' : 'assistant-app'}>
      <aside className="assistant-sidebar" aria-label="Навигация помощника">
        <div className="sidebar-content">
          <a
            aria-label="Уфимский университет науки и технологий — официальный сайт"
            className="brand"
            href={universityUrl}
            rel="noreferrer"
            target="_blank"
          >
            <UniversityMark className="brand-symbol" />
            <span className="brand-name">
              Уфимский<br />университет<br />науки и технологий
            </span>
          </a>

          <button className="new-chat-button" onClick={startNewSession} type="button">
            <AssistantIcon name="plus" />
            <span>Новый диалог</span>
          </button>

          <div className="sidebar-section">
            <p className="section-label" id="audience-label">Ваш профиль</p>
            <div className="profile-card" aria-labelledby="audience-label" role="status">
              <AssistantIcon name={audience === 'student' ? 'book' : audience === 'applicant' ? 'cap' : 'chat'} />
              <span>{audienceLabels[audience]}</span>
              <UniversityMark className="audience-watermark" />
            </div>
          </div>
        </div>
      </aside>

      <main className="assistant-main">
        <ProjectHeader />

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
                <img className="welcome-art" src={campusOrbit} alt="" fetchPriority="high" />
                <div className="welcome-copy">
                  <p className="welcome-eyebrow">Think-About-It-Agent</p>
                  <h1 id="welcome-title">Спросите<br />про <span>УУНиТ</span></h1>
                  <p className="welcome-description">
                    Помогу разобраться в поступлении, учёбе и студенческой жизни.
                  </p>
                </div>
              </section>

              <section className="suggestions" aria-labelledby="suggestions-title">
                <h2 id="suggestions-title">С чего начать</h2>
                <div className="prompt-grid">
                  {prompts.map(({ label, question, icon }) => (
                    <button
                      className="prompt-card"
                      key={label}
                      onClick={() => submitPrompt(question)}
                      type="button"
                    >
                      <span className="prompt-icon"><AssistantIcon name={icon} /></span>
                      <strong>{label}</strong>
                      <span className="prompt-question">{question}</span>
                    </button>
                  ))}
                </div>
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
              aria-describedby="composer-hint"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Задайте вопрос об УУНиТ"
              rows={1}
              value={draft}
            />
            <div className="composer-bottom">
              <span id="composer-hint"><kbd>Enter</kbd> отправить · <kbd>Shift + Enter</kbd> новая строка</span>
              <button
                className="send-button"
                disabled={!draft.trim() || !canSend}
                type="submit"
              >
                Отправить
                <AssistantIcon name="send" />
              </button>
            </div>
          </form>
          {hasMessages ? (
            <p className="composer-note"><AssistantIcon name="link" /> Ссылки на источники появятся под ответом</p>
          ) : (
            <nav aria-label="Полезные ссылки УУНиТ" className="welcome-links">
              <a href={universityUrl + 'admission/'} target="_blank" rel="noreferrer">
                <AssistantIcon name="cap" />
                Приёмная комиссия
              </a>
              <a href={universityUrl + 'digital-services/'} target="_blank" rel="noreferrer">
                <AssistantIcon name="blocks" />
                Сервисы УУНиТ
              </a>
            </nav>
          )}
        </div>
      </main>
      {!isLoading && <IdleSeason />}
    </div>
  )
}
