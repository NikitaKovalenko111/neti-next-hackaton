import { parseMessage, type ChatMessage } from '../../api/messageBlocks'

const favoritesKey = 'uust-favorite-answers'

export function favoritesStorageKey(accountId?: string) {
  return accountId ? `${favoritesKey}:${accountId}` : favoritesKey
}

export function canSaveFavorite(message: ChatMessage) {
  return message.role === 'assistant' &&
    (message.blocks.some((block) => block.type !== 'attachments') || Boolean(message.sources?.length))
}

export function snapshotFavorite(message: ChatMessage): ChatMessage {
  return {
    id: message.id,
    role: 'assistant',
    blocks: message.blocks.filter((block) => block.type !== 'attachments'),
    sources: message.sources,
  }
}

export function loadFavorites(key: string): ChatMessage[] {
  try {
    const entries: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    if (!Array.isArray(entries)) return []

    return entries.flatMap((entry: unknown) => {
      const message = parseMessage(entry, 'assistant')
      if (!message || !canSaveFavorite(message)) return []

      return [snapshotFavorite(message)]
    })
  } catch {
    return []
  }
}

export function writeFavorites(messages: ChatMessage[], key: string) {
  const entries = messages.map(({ id, blocks, sources }) => ({
    message_id: id,
    blocks,
    sources,
  }))
  localStorage.setItem(key, JSON.stringify(entries))
}
