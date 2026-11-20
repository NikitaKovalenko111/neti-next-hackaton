import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import campusOrbit from '../../assets/campus-orbit.webp'
import { AssistantIcon, AssistantMark } from '../../components/assistant/AssistantIcon'
import { MessageBubble } from '../../components/assistant/MessageBubble'
import { ProjectHeader, universityUrl } from '../../components/project-header/ProjectHeader'
import { UniversityMark } from '../../components/project-header/UniversityMark'
import {
  assistantActions,
  requestAnswer,
  type Audience,
} from '../../redux/assistantSlice'
import type { AppDispatch, RootState } from '../../redux/store'

const prompts = {
  applicant: [
    { label: 'Поступление', question: 'Что нужно для поступления на бакалавриат?', icon: 'cap' },
    { label: 'Направления', question: 'Какие ИТ-направления есть в УУНиТ?', icon: 'blocks' },
    { label: 'Общежитие', question: 'Как получить место в общежитии?', icon: 'home' },
  ],
  student: [
    { label: 'Учебный план', question: 'Где найти учебный план моей программы?', icon: 'book' },
    { label: 'Цифровые сервисы', question: 'Какие сервисы доступны студентам?', icon: 'blocks' },
    { label: 'Поддержка', question: 'Куда обратиться по вопросу обучения?', icon: 'chat' },
  ],
} as const

const audiences = [
  { id: 'applicant', label: 'Я абитуриент', icon: 'cap' },
  { id: 'student', label: 'Я студент', icon: 'book' },
] as const satisfies ReadonlyArray<{ id: Audience; label: string; icon: 'cap' | 'book' }>

export function AssistantPage() {
  const dispatch = useDispatch<AppDispatch>()
  const { audience, messages, sessionId, status, error } = useSelector(
    (state: RootState) => state.assistant,
  )
  const [draft, setDraft] = useState('')
  const transcriptRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const hasMessages = messages.length > 0
  const isLoading = status === 'loading'

  useEffect(() => {
    const transcript = transcriptRef.current
    if (transcript) transcript.scrollTop = transcript.scrollHeight
  }, [messages.length, status])

  function submitPrompt(value: string) {
    const content = value.trim()
    if (!content || isLoading) return

    dispatch(
      assistantActions.addUserMessage({
        id: crypto.randomUUID(),
        role: 'user',
        content,
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
            <div className="audience-switch" role="group" aria-labelledby="audience-label">
              {audiences.map((option) => (
                <button
                  aria-pressed={audience === option.id}
                  className="audience-option"
                  key={option.id}
                  onClick={() => dispatch(assistantActions.setAudience(option.id))}
                  type="button"
                >
                  <AssistantIcon name={option.icon} />
                  {option.label}
                </button>
              ))}
              <UniversityMark className="audience-watermark" />
            </div>
          </div>

          <div className="sidebar-bottom">
            <nav aria-label="Ссылки УУНиТ">
              <p className="section-label">Полезные ссылки</p>
              <a href={universityUrl + 'admission/'} target="_blank" rel="noreferrer">
                <AssistantIcon name="cap" />
                Приёмная комиссия
              </a>
              <a href={universityUrl + 'digital-services/'} target="_blank" rel="noreferrer">
                <AssistantIcon name="blocks" />
                Сервисы УУНиТ
              </a>
            </nav>
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
                  isLoading={isLoading}
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
                  {prompts[audience].map(({ label, question, icon }) => (
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
                disabled={!draft.trim() || isLoading}
                type="submit"
              >
                Отправить
                <AssistantIcon name="send" />
              </button>
            </div>
          </form>
          <p className="composer-note"><AssistantIcon name="link" /> Ссылки на источники появятся под ответом</p>
        </div>
      </main>
    </div>
  )
}
