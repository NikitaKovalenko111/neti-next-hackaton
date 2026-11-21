export interface ChatSource {
  title: string
  url: string
  section?: string
}

export type Audience = 'unknown' | 'applicant' | 'student'

interface ChatAttachment {
  id: string
  filename: string
  contentType: string
  url: string
}

export interface MapPoint {
  latitude: number
  longitude: number
  title?: string
  address?: string
}

export interface MapBlock {
  type: 'map'
  points: MapPoint[]
}

export type MessageBlock =
  | { type: 'text'; message: string; audience?: Audience }
  | { type: 'attachments'; attachments: ChatAttachment[] }
  | MapBlock

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  blocks: MessageBlock[]
  sources?: ChatSource[]
  followUps?: string[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isWebUrl(value: unknown): value is string {
  return typeof value === 'string' && URL.canParse(value) && /^https?:$/i.test(new URL(value).protocol)
}

function isSource(value: unknown): value is ChatSource {
  return isRecord(value) && typeof value.title === 'string' && isWebUrl(value.url) &&
    (value.section === undefined || typeof value.section === 'string')
}

function parseMapPoint(value: unknown): MapPoint | undefined {
  if (!isRecord(value)) return
  const latitude = value.latitude ?? value.lat
  const longitude = value.longitude ?? value.lon
  if (typeof latitude !== 'number' || typeof longitude !== 'number' ||
    !Number.isFinite(latitude) || Math.abs(latitude) > 90 ||
    !Number.isFinite(longitude) || Math.abs(longitude) > 180) return

  return {
    latitude,
    longitude,
    title: typeof value.title === 'string' ? value.title : undefined,
    address: typeof value.address === 'string' ? value.address : undefined,
  }
}

function parseBlock(value: unknown): MessageBlock | undefined {
  if (!isRecord(value)) return

  if (value.type === 'text' && typeof value.message === 'string' && value.message.trim()) {
    const audience = value.audience
    return {
      type: 'text',
      message: value.message,
      audience: audience === 'applicant' || audience === 'student' || audience === 'unknown'
        ? audience
        : undefined,
    }
  }
  if (value.type === 'attachments' && Array.isArray(value.attachments)) {
    const attachments = value.attachments.flatMap((item: unknown) => {
      if (!isRecord(item) || typeof item.attachment_id !== 'string' ||
        typeof item.filename !== 'string' || typeof item.content_type !== 'string' ||
        !isWebUrl(item.url)) return []

      return [{ id: item.attachment_id, filename: item.filename, contentType: item.content_type, url: item.url }]
    })
    if (attachments.length) return { type: 'attachments', attachments }
  }
  if (value.type === 'map') {
    const points = (Array.isArray(value.points) ? value.points : [value])
      .map(parseMapPoint)
      .filter((point) => point !== undefined)
    if (points.length) return { type: 'map', points }
  }
}

export function parseMessage(value: unknown, role: ChatMessage['role']): ChatMessage | undefined {
  if (!isRecord(value) || typeof value.message_id !== 'string' || !Array.isArray(value.blocks)) return

  const sources = new Map<string, ChatSource>()
  if (Array.isArray(value.sources)) {
    for (const source of value.sources.filter(isSource)) {
      sources.set(source.url, source)
    }
  }
  for (const block of value.blocks) {
    if (!isRecord(block) || block.type !== 'text' || !Array.isArray(block.source)) continue

    for (const url of block.source.filter(isWebUrl)) {
      if (!sources.has(url)) sources.set(url, { url, title: new URL(url).hostname })
    }
  }

  const blocks: MessageBlock[] = []
  const map: MapBlock = { type: 'map', points: [] }
  const mapPointKeys = new Set<string>()
  for (const block of value.blocks) {
    const parsed = parseBlock(block)
    if (!parsed) continue
    if (parsed.type !== 'map') {
      blocks.push(parsed)
      continue
    }
    if (!map.points.length) blocks.push(map)
    for (const point of parsed.points) {
      const key = JSON.stringify([point.latitude, point.longitude, point.title, point.address])
      if (mapPointKeys.has(key)) continue
      mapPointKeys.add(key)
      map.points.push(point)
    }
  }

  return {
    id: value.message_id,
    role,
    blocks,
    sources: sources.size ? [...sources.values()] : undefined,
    followUps: Array.isArray(value.followUps)
      ? value.followUps.filter((prompt): prompt is string => typeof prompt === 'string' && Boolean(prompt.trim()))
      : undefined,
  }
}
