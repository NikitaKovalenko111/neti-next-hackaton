import type { ChatMessage, MapBlock, MessageBlock } from '../../api/messageBlocks'
import { AssistantIcon, AssistantMark } from './AssistantIcon'

interface MessageBubbleProps {
  message: ChatMessage
  onFollowUp: (prompt: string) => void
  isLoading: boolean
}

function RouteCard({ block }: { block: MapBlock }) {
  const { lat, lon } = block
  const point = `${lat},${lon}`
  const title = block.title || 'Точка на карте'
  const map = new URL('https://www.openstreetmap.org/export/embed.html')
  map.search = new URLSearchParams({
    bbox: [lon - .008, lat - .004, lon + .008, lat + .004].join(','),
    layer: 'mapnik',
    marker: point,
  }).toString()
  const route = new URL('https://yandex.ru/maps/')
  route.search = new URLSearchParams({ mode: 'routes', rtext: `~${point}` }).toString()

  return (
    <section className="message-map" aria-label={title}>
      <iframe loading="lazy" referrerPolicy="no-referrer" src={map.href} title={title} />
      <div className="map-details">
        <div>
          <strong>{title}</strong>
          {block.address && <p>{block.address}</p>}
        </div>
        <a className="map-route" href={route.href} target="_blank" rel="noreferrer">
          Построить маршрут
        </a>
      </div>
    </section>
  )
}

function BlockView({ block }: { block: MessageBlock }) {
  switch (block.type) {
    case 'text':
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
      return <RouteCard block={block} />
  }
}

export function MessageBubble({ message, onFollowUp, isLoading }: MessageBubbleProps) {
  const isAssistant = message.role === 'assistant'

  return (
    <article className={isAssistant ? 'message-row assistant-row' : 'message-row user-row'}>
      {isAssistant && <AssistantMark />}
      <div className="message-content">
        <div className="message-author">{isAssistant ? 'Помощник УУНиТ' : 'Вы'}</div>
        <div className="message-blocks">
          {message.blocks.length
            ? message.blocks.map((block, index) => <BlockView block={block} key={index} />)
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
