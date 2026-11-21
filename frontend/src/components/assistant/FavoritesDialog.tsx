import { useRef, type RefObject } from 'react'
import type { ChatMessage } from '../../api/messageBlocks'
import { AssistantIcon } from './AssistantIcon'
import { MessageBubble } from './MessageBubble'

export function FavoritesDialog({ dialogRef, favorites, hasError, isLoading, onRemove }: {
  dialogRef: RefObject<HTMLDialogElement | null>
  favorites: ChatMessage[]
  hasError: boolean
  isLoading: boolean
  onRemove: (message: ChatMessage) => Promise<boolean>
}) {
  const closeRef = useRef<HTMLButtonElement>(null)

  return (
    <dialog aria-labelledby="favorites-title" className="favorites-dialog" ref={dialogRef}>
      <header className="favorites-heading">
        <h2 id="favorites-title">Избранное</h2>
        <button
          aria-label="Закрыть избранное"
          className="favorites-close"
          onClick={() => dialogRef.current?.close()}
          ref={closeRef}
          type="button"
        >
          <AssistantIcon name="close" />
        </button>
      </header>
      <div className="favorites-body">
        {hasError && <p className="favorite-error" role="alert">Не удалось обновить избранное.</p>}
        {isLoading ? <p role="status">Загружаем избранное…</p> : favorites.length ? (
          <div className="favorites-list">
            {favorites.map((message) => (
              <MessageBubble
                isFavorite
                key={message.id}
                message={message}
                onToggleFavorite={() => {
                  void onRemove(message).then((removed) => { if (removed) closeRef.current?.focus() })
                }}
              />
            ))}
          </div>
        ) : (
          <div className="favorites-empty">
            <AssistantIcon name="star" />
            <p>Пока нет сохранённых ответов</p>
            <span>Нажмите звёздочку рядом с полезным ответом, чтобы сохранить его здесь.</span>
          </div>
        )}
      </div>
    </dialog>
  )
}
