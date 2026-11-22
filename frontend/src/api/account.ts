import axios from 'axios'
import { chatHistory } from './chatHistory'
import type { ChatMessage } from './messageBlocks'

export interface Account {
  id: string
  username: string
  expiresAt: number
}

export interface SavedChat {
  chat_id: string
  created_at: string
}

interface Session extends Account {
  token: string
}

export const accountSessionKey = 'uust-account-session'
let memorySession: Session | null | undefined

function readSession(): Session | null {
  try {
    const value = memorySession === undefined
      ? JSON.parse(localStorage.getItem(accountSessionKey) ?? 'null') as Session | null
      : memorySession
    if (!value || typeof value.id !== 'string' || typeof value.username !== 'string' ||
      typeof value.token !== 'string' || !Number.isFinite(value.expiresAt) || value.expiresAt <= Date.now()) return null
    return value
  } catch {
    return null
  }
}

function storeSession(session: Session | null) {
  try {
    if (session) localStorage.setItem(accountSessionKey, JSON.stringify(session))
    else localStorage.removeItem(accountSessionKey)
    memorySession = undefined
  } catch {
    memorySession = session
  }
}

export function currentAccount(): Account | null {
  const session = readSession()
  return session ? { id: session.id, username: session.username, expiresAt: session.expiresAt } : null
}

export function accountHeaders(id: string) {
  const session = readSession()
  if (session?.id !== id) throw new Error('Сессия завершилась. Войдите в аккаунт снова.')
  return { Authorization: `Bearer ${session.token}` }
}

export async function authenticate(mode: 'login' | 'register', username: string, password: string) {
  const length = new TextEncoder().encode(password).length
  if (length < 8 || length > 72) throw new Error('Пароль должен занимать от 8 до 72 байт.')
  const login = username.trim().toLowerCase()
  const { data } = await axios.post(`/${mode}`, { login, password }, { timeout: 15000 })
  if (typeof data?.user_id !== 'string' || typeof data?.access_token !== 'string' ||
    !Number.isFinite(data.expires_in) || data.expires_in <= 0) throw new Error('Сервер не подтвердил вход.')
  const account: Account = { id: data.user_id, username: login, expiresAt: Date.now() + data.expires_in * 1000 }
  storeSession({ ...account, token: data.access_token })
  return account
}

export async function logout() {
  await axios.post('/logout', {}, { timeout: 15_000 })
  storeSession(null)
}

export async function accountChats(id: string, signal: AbortSignal) {
  const { data } = await axios.get<SavedChat[]>('/chats', { headers: accountHeaders(id), signal, timeout: 15_000 })
  return data ?? []
}

export async function accountChat(id: string, chatId: string, signal: AbortSignal) {
  const messages: ChatMessage[] = []
  for await (const { message } of chatHistory(chatId, { headers: accountHeaders(id), signal })) {
    messages.push(message)
  }
  return messages
}

export function accountError(error: unknown, fallback: string) {
  if (!axios.isAxiosError(error)) return error instanceof Error ? error.message : fallback
  if (error.response?.status === 409) return 'Этот логин уже занят.'
  if (error.response?.status === 401) {
    return error.config?.url === '/login' ? 'Неверный логин или пароль.' : 'Войдите в аккаунт снова.'
  }
  return fallback
}
