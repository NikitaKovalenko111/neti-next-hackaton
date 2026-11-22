package chat

import (
	"context"
	"encoding/json"

	"university-agent/internal/models"
	service "university-agent/internal/services/chat"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct {
	db *pgxpool.Pool
}

func New(db *pgxpool.Pool) *Repository {
	return &Repository{db: db}
}

func (r *Repository) History(ctx context.Context, chatID, userID uuid.UUID, after *uuid.UUID, registered bool) ([]models.HistoryMessage, error) {
	var exists bool
	err := r.db.QueryRow(ctx, `
		SELECT EXISTS (SELECT 1 FROM chats WHERE id = $1 AND user_id = $2
		  AND CASE WHEN $3::boolean THEN guest_expires_at IS NULL ELSE guest_expires_at > now() END)`,
		chatID, userID, registered).Scan(&exists)
	if err != nil {
		return nil, err
	}
	if !exists {
		return nil, service.ErrNotFound
	}

	if after != nil {
		err := r.db.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM messages WHERE id = $1 AND chat_id = $2)`, after, chatID).Scan(&exists)
		if err != nil {
			return nil, err
		}
		if !exists {
			return nil, service.ErrInvalid
		}
	}

	rows, err := r.db.Query(ctx, `
		SELECT m.id, m.role, m.blocks, m.request_message_id, m.created_at
		FROM messages m
		WHERE m.chat_id = $1 AND ($2::uuid IS NULL OR (m.created_at, m.id) >
		    (SELECT created_at, id FROM messages WHERE id = $2))
		ORDER BY m.created_at, m.id LIMIT 100`, chatID, after)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	messages := make([]models.HistoryMessage, 0)
	for rows.Next() {
		var message models.HistoryMessage
		var blocks []byte
		if err := rows.Scan(&message.ID, &message.Role, &blocks, &message.RequestMessageID, &message.CreatedAt); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(blocks, &message.Blocks); err != nil {
			return nil, err
		}
		messages = append(messages, message)
	}

	return messages, rows.Err()
}

func (r *Repository) List(ctx context.Context, userID uuid.UUID) ([]models.Chat, error) {
	rows, err := r.db.Query(ctx, `
		SELECT id, created_at FROM chats WHERE user_id = $1 AND guest_expires_at IS NULL
		ORDER BY created_at DESC, id`, userID)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, pgx.RowToStructByPos[models.Chat])
}
