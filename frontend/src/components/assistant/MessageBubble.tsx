import type { ChatMessage } from '../../redux/assistantSlice'
import { AssistantIcon, AssistantMark } from './AssistantIcon'

interface MessageBubbleProps {
  message: ChatMessage
  onFollowUp: (prompt: string) => void
  isLoading: boolean
}

export function MessageBubble({ message, onFollowUp, isLoading }: MessageBubbleProps) {
  const isAssistant = message.role === 'assistant'

  return (
    <article className={isAssistant ? 'message-row assistant-row' : 'message-row user-row'}>
      {isAssistant && <AssistantMark />}
      <div className="message-content">
        <div className="message-author">{isAssistant ? 'Помощник УУНиТ' : 'Вы'}</div>
        <div className="message-bubble">{message.content}</div>
        {Boolean(message.sources?.length) && (
          <div className="source-list">
            <p className="source-list-title">Источники</p>
            {message.sources?.map((source) => (
              <a
                className="source-card"
                href={source.url}
                key={`${source.url}-${source.title}`}
                rel="noreferrer"
                target="_blank"
              >
                <AssistantIcon name="link" />
                <span>
                  <strong>{source.title}</strong>
                  {source.section && <small>{source.section}</small>}
                </span>
              </a>
            ))}
          </div>
        )}
        {Boolean(message.followUps?.length) && (
          <div className="follow-up-list">
            {message.followUps?.map((prompt) => (
              <button disabled={isLoading} key={prompt} onClick={() => onFollowUp(prompt)} type="button">
                {prompt}
              </button>
            ))}
          </div>
        )}
      </div>
    </article>
  )
}
