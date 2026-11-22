import axios from 'axios'
import { parseMessage } from './messageBlocks'

// The backend returns at most this many messages per page.
const historyPageSize = 100

export async function* chatHistory(chatId: string, options: {
  signal: AbortSignal
  headers?: { Authorization: string }
  guestId?: string
  after?: string
}) {
  let after = options.after
  while (true) {
    const { data } = await axios.get<unknown>(`/chats/${encodeURIComponent(chatId)}/messages`, {
      params: { after, user_id: options.guestId },
      headers: options.headers,
      signal: options.signal,
      timeout: 15_000,
    })

    if (!Array.isArray(data)) throw new Error('Не удалось прочитать диалог.')
    let lastId = after
    for (const item of data as unknown[]) {
      if (!item || typeof item !== 'object' || !('role' in item) ||
        (item.role !== 'user' && item.role !== 'assistant')) throw new Error('Не удалось прочитать диалог.')

      const message = parseMessage(item, item.role)
      if (!message || message.id === lastId) throw new Error('Не удалось прочитать диалог.')

      lastId = message.id
      const requestMessageId = 'request_message_id' in item && typeof item.request_message_id === 'string'
        ? item.request_message_id
        : undefined
      yield { message, requestMessageId }
    }
    if (data.length < historyPageSize) return
    if (lastId === after) throw new Error('Не удалось прочитать диалог.')
    after = lastId
  }
}
