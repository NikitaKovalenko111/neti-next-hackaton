import axios from 'axios'
import { parseMessage, type ChatMessage } from './messageBlocks'

export interface Account {
  id: string
  username: string
}

export interface SavedChat {
  id: string
  title: string
  updated_at: string
}

function accountHeaders(id: string) {
  return { 'X-UUST-Account': id }
}

export async function currentAccount(signal: AbortSignal) {
  const { data } = await axios.get<Account | null>('/account/session', { signal, timeout: 5000 })
  return data
}

export async function authenticate(mode: 'login' | 'register', username: string, password: string) {
  const { data } = await axios.post<Account>(`/account/${mode}`, { username, password }, { timeout: 15000 })
  return data
}

export async function logout(id: string) {
  await axios.post('/account/logout', undefined, { headers: accountHeaders(id), timeout: 10000 })
}

export async function accountChats(id: string, signal: AbortSignal) {
  const { data } = await axios.get<SavedChat[]>('/account/chats', { headers: accountHeaders(id), signal })
  return data ?? []
}

export async function accountChat(id: string, chatId: string, signal: AbortSignal) {
  const messages: ChatMessage[] = []
  let after: string | undefined
  for (;;) {
    const { data } = await axios.get<unknown[]>(`/chats/${encodeURIComponent(chatId)}/messages`, {
      params: { user_id: id, after }, signal,
    })
    for (const item of data) {
      if (!item || typeof item !== 'object' || !('role' in item) ||
        (item.role !== 'user' && item.role !== 'assistant')) throw new Error('Не удалось прочитать диалог.')
      const message = parseMessage(item, item.role)
      if (!message) throw new Error('Не удалось прочитать диалог.')
      messages.push(message)
    }
    if (data.length < 100) return messages
    after = messages.at(-1)?.id
  }
}

export async function accountFavorites(id: string, signal: AbortSignal) {
  const { data } = await axios.get<unknown[]>('/account/favorites', { headers: accountHeaders(id), signal })
  return data.map((item) => parseMessage(item, 'assistant')).filter((message) => message !== undefined)
}

export async function updateAccountFavorite(id: string, messageId: string, save: boolean) {
  await axios.request({
    url: `/account/favorites/${encodeURIComponent(messageId)}`,
    method: save ? 'PUT' : 'DELETE',
    headers: accountHeaders(id),
  })
}

export function accountError(error: unknown, fallback: string) {
  const description = axios.isAxiosError<{ error?: unknown }>(error) ? error.response?.data?.error : undefined
  return typeof description === 'string' ? description : fallback
}
