import axios from 'axios'
import { buffers, eventChannel } from 'redux-saga'
import { parseMessage, type ChatMessage } from './messageBlocks'

export interface AcceptedRequest {
  chatId: string
  messageId: string
}

export type ChatSocketEvent =
  | { type: 'ready' | 'disconnected' }
  | ({ type: 'answer'; message: ChatMessage; requestMessageId: string } & Pick<AcceptedRequest, 'chatId'>)

export function openChatSocket(userId: string) {
  const url = new URL('/ws', window.location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.searchParams.set('user_id', userId)

  return eventChannel<ChatSocketEvent>((emit) => {
    const socket = new WebSocket(url)
    socket.onclose = () => emit({ type: 'disconnected' })
    socket.onmessage = ({ data }) => {
      if (typeof data !== 'string') return

      try {
        const event = JSON.parse(data)
        if (event?.type === 'ready') {
          emit({ type: 'ready' })
        } else if (event?.type === 'agent_response' && typeof event.chat_id === 'string' &&
          typeof event.request_message_id === 'string') {
          const message = parseMessage(event, 'assistant')
          if (message) {
            emit({
              type: 'answer',
              chatId: event.chat_id,
              requestMessageId: event.request_message_id,
              message,
            })
          }
        }
      } catch {
        // A malformed socket event must not interrupt the conversation.
      }
    }

    return () => {
      socket.onmessage = null
      socket.onclose = null
      socket.close()
    }
  }, buffers.expanding<ChatSocketEvent>())
}

export async function sendAssistantMessage(
  userId: string,
  chatId: string | null,
  message: string,
  signal: AbortSignal,
): Promise<AcceptedRequest> {
  const form = new FormData()
  form.set('user_id', userId)
  form.set('message', message)
  if (chatId) form.set('chat_id', chatId)

  const { data } = await axios.post('/request', form, { signal })
  if (typeof data?.chat_id !== 'string' || typeof data?.message_id !== 'string') {
    throw new Error('Сервис не подтвердил отправку вопроса.')
  }
  return { chatId: data.chat_id, messageId: data.message_id }
}

export async function recoverAnswer(
  userId: string,
  request: AcceptedRequest,
  signal: AbortSignal,
): Promise<ChatMessage | undefined> {
  const { data } = await axios.get<unknown>(`/chats/${encodeURIComponent(request.chatId)}/messages`, {
    params: { user_id: userId, after: request.messageId },
    signal,
  })
  if (!Array.isArray(data)) return

  const response = data.find(
    (entry) => entry?.role === 'assistant' && entry.request_message_id === request.messageId,
  )
  return parseMessage(response, 'assistant')
}
