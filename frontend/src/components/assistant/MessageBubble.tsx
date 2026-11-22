import { lazy, Suspense } from 'react'
import { isWebUrl, type ChatMessage, type MessageBlock } from '../../api/messageBlocks'
import { AssistantIcon, AssistantMark } from './AssistantIcon'
import { RouteCard } from './RouteCard'

const Markdown = lazy(() => import('react-markdown'))

interface MessageBubbleProps {
  message: ChatMessage
  onFollowUp?: (prompt: string) => void
  isLoading?: boolean
  isFavorite?: boolean
  onToggleFavorite?: () => void
}

function BlockView({ block, renderMarkdown }: { block: MessageBlock; renderMarkdown: boolean }) {
  switch (block.type) {
    case 'text':
      if (renderMarkdown) {
        return (
          <div className="message-bubble message-bubble--markdown">
            <Suspense fallback={block.message}>
              <Markdown
                components={{
                  a: ({ href, children }) => href
                    ? <a href={href} rel="noreferrer" target="_blank">{children}</a>
                    : <>{children}</>,
                }}
                disallowedElements={['img']}
                skipHtml
                urlTransform={(url) => isWebUrl(url) ? url : undefined}
              >
                {block.message}
              </Markdown>
            </Suspense>
          </div>
        )
      }
      return <div className="message-bubble">{block.message}</div>
    case 'attachments':
      return (
        <div className="message-attachments">
          {block.attachments.map(({ id, contentType, filename, url }) => (
            <a className="message-attachment" href={url} key={id} rel="noreferrer" target="_blank">
              {contentType.startsWith('image/') && (
                <img alt="" loading="lazy" referrerPolicy="no-referrer" src={url} />
              )}
              <span>{filename}</span>
            </a>
          ))}
        </div>
      )
    case 'map':
      return <RouteCard points={block.points} />
  }
}

export function MessageBubble({ message, onFollowUp, isLoading, isFavorite, onToggleFavorite }: MessageBubbleProps) {
  const isAssistant = message.role === 'assistant'
  const favoriteTitle = isFavorite ? 'Убрать из избранного' : 'Сохранить в избранное'

  return (
    <article aria-label={isAssistant ? 'Помощник УУНиТ' : 'Вы'} className={isAssistant ? 'message-row assistant-row' : 'message-row user-row'}>
      {isAssistant && (
        <div className="message-aside">
          <AssistantMark />
          {onToggleFavorite && (
            <button
              aria-label="Сохранить ответ в избранное"
              aria-pressed={Boolean(isFavorite)}
              className="message-favorite"
              onClick={onToggleFavorite}
              title={favoriteTitle}
              type="button"
            >
              <AssistantIcon name="star" />
            </button>
          )}
        </div>
      )}
      <div className="message-content">
        <div className="message-blocks">
          {message.blocks.length
            ? message.blocks.map((block, index) => <BlockView block={block} key={index} renderMarkdown={isAssistant} />)
            : <div className="message-bubble">Формат ответа пока не поддерживается.</div>}
        </div>
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
        {onFollowUp && Boolean(message.followUps?.length) && (
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
