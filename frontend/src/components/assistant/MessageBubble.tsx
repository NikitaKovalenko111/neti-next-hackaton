import type { ChatMessage, MapBlock, MessageBlock } from '../../api/messageBlocks'
import { campusMap } from '../../assets/campusMap'
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
  const isMainBuilding = Math.abs(lat - 54.720714) < .00001 && Math.abs(lon - 55.933422) < .00001
  const openMap = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=17/${lat}/${lon}`
  const map = new URL('https://www.openstreetmap.org/export/embed.html')
  map.search = new URLSearchParams({
    bbox: [lon - .003, lat - .0015, lon + .003, lat + .0015].join(','),
    layer: 'mapnik',
    marker: point,
  }).toString()
  const route = new URL('https://yandex.ru/maps/')
  route.search = new URLSearchParams({ mode: 'routes', rtext: `~${point}` }).toString()

  return (
    <section className="message-map" aria-label={title}>
      <div className="map-details">
        <AssistantIcon name="pin" />
        <div>
          <strong>{title}</strong>
          {block.address && <p>{block.address}</p>}
        </div>
      </div>
      {isMainBuilding ? (
        <div className="campus-map">
          <a aria-label={`Открыть на карте · ${title}`} className="campus-map-preview" href={openMap} rel="noreferrer" target="_blank">
            <svg aria-hidden="true" viewBox="0 0 460 240" preserveAspectRatio="xMidYMid slice">
              <path className="campus-map-greenery" d={campusMap.greenery} />
              <path className="campus-map-paths" d={campusMap.paths} />
              <path className="campus-map-streets" d={campusMap.streets} />
              <path className="campus-map-buildings" d={campusMap.buildings} />
              <path className="campus-map-building" d={campusMap.mainBuilding} />
            </svg>
            <AssistantIcon name="pin" />
          </a>
          <a className="campus-map-credit" href="https://www.openstreetmap.org/copyright" rel="noreferrer" target="_blank">
            © OpenStreetMap
          </a>
        </div>
      ) : (
        <iframe loading="lazy" referrerPolicy="no-referrer" src={map.href} title={title} />
      )}
      <a className="map-route" href={route.href} target="_blank" rel="noreferrer">
        Построить маршрут
      </a>
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
    <article aria-label={isAssistant ? 'Помощник УУНиТ' : 'Вы'} className={isAssistant ? 'message-row assistant-row' : 'message-row user-row'}>
      {isAssistant && <AssistantMark />}
      <div className="message-content">
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
