import axios from 'axios'
import type {
  Audience,
  ChatMessage,
  ChatSource,
} from '../redux/assistantSlice'

export interface ChatRequest {
  sessionId: string
  audience: Audience
  history: Array<Pick<ChatMessage, 'role' | 'content'>>
}

export interface ChatResponse {
  answer: string
  sources?: ChatSource[]
  followUps?: string[]
}

function isUsableSource(source: ChatSource): boolean {
  if (typeof source?.title !== 'string' || !source.title.trim() || typeof source.url !== 'string') {
    return false
  }
  if (source.section !== undefined && typeof source.section !== 'string') return false
  if (!URL.canParse(source.url)) return false

  const protocol = new URL(source.url).protocol
  return protocol === 'https:' || protocol === 'http:'
}

export async function sendAssistantMessage(
  request: ChatRequest,
): Promise<ChatResponse> {
  const { data } = await axios.post<ChatResponse | null>('/api/chat', request)
  if (typeof data?.answer !== 'string' || !data.answer.trim()) {
    throw new Error('Получен пустой ответ от сервиса')
  }

  return {
    answer: data.answer,
    sources: Array.isArray(data.sources) ? data.sources.filter(isUsableSource) : undefined,
    followUps: Array.isArray(data.followUps)
      ? data.followUps.filter((prompt) => typeof prompt === 'string' && prompt.trim())
      : undefined,
  }
}
