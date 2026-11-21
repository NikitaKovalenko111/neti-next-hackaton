package agent

import (
	"context"
	"encoding/json"
	"errors"
	"strings"

	"university-agent/internal/models"
	service "university-agent/internal/services/agent"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct {
	db *pgxpool.Pool
}

func New(db *pgxpool.Pool) *Repository {
	return &Repository{db: db}
}

func (r *Repository) Pending(ctx context.Context) ([]service.Task, error) {
	rows, err := r.db.Query(ctx, `
		SELECT message_id, payload FROM agent_request_outbox
		ORDER BY created_at, message_id LIMIT 50`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var tasks []service.Task
	for rows.Next() {
		var task service.Task
		if err := rows.Scan(&task.MessageID, &task.Payload); err != nil {
			return nil, err
		}
		tasks = append(tasks, task)
	}

	return tasks, rows.Err()
}

func (r *Repository) MarkPublished(ctx context.Context, messageID uuid.UUID) error {
	_, err := r.db.Exec(ctx, `DELETE FROM agent_request_outbox WHERE message_id = $1`, messageID)
	return err
}

func (r *Repository) SaveResponse(ctx context.Context, response models.AgentResponse) (uuid.UUID, models.ResponseEvent, error) {
	tx, err := r.db.Begin(ctx)
	if err != nil {
		return uuid.Nil, models.ResponseEvent{}, err
	}
	defer tx.Rollback(context.Background())

	var userID uuid.UUID
	var turnNumber int64
	event := models.ResponseEvent{Type: "agent_response", RequestMessageID: response.RequestMessageID}
	err = tx.QueryRow(ctx, `
		SELECT m.chat_id, c.user_id, m.turn_number
		FROM messages m JOIN chats c ON c.id = m.chat_id
		WHERE m.id = $1 AND m.role = 'user' FOR NO KEY UPDATE OF c`, response.RequestMessageID,
	).Scan(&event.ChatID, &userID, &turnNumber)
	if errors.Is(err, pgx.ErrNoRows) {
		return uuid.Nil, event, service.ErrInvalidResponse
	}
	if err != nil {
		return uuid.Nil, event, err
	}

	blocks, err := json.Marshal(response.Blocks)
	if err != nil {
		return uuid.Nil, event, err
	}

	var insertedID uuid.UUID
	err = tx.QueryRow(ctx, `
		INSERT INTO messages (id, chat_id, content, role, request_message_id, blocks)
		VALUES ($1, $2, '', 'assistant', $3, $4)
		ON CONFLICT (request_message_id) DO NOTHING RETURNING id`,
		uuid.New(), event.ChatID, response.RequestMessageID, blocks,
	).Scan(&insertedID)
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return uuid.Nil, event, err
	}

	if err == nil {
		if summary := strings.TrimSpace(response.HistorySummary); summary != "" {
			_, err := tx.Exec(ctx, `
				UPDATE chats SET history_summary = left($2, 2400), history_summary_through = $3
				WHERE id = $1 AND history_summary_through < $3`,
				event.ChatID, summary, turnNumber,
			)
			if err != nil {
				return uuid.Nil, event, err
			}
		}

		for _, block := range response.Blocks {
			if block.Attachments == nil {
				continue
			}

			for _, attachment := range block.Attachments.Attachments {
				_, err = tx.Exec(ctx, `
					INSERT INTO attachments
					    (attachment_id, message_id, bucket, object_key, filename, content_type, size_bytes)
					VALUES ($1, $2, $3, $4, $5, $6, $7)`,
					attachment.ID, insertedID, attachment.Bucket, attachment.ObjectKey,
					attachment.Filename, attachment.ContentType, attachment.SizeBytes,
				)
				if err != nil {
					var constraintErr *pgconn.PgError
					if errors.As(err, &constraintErr) && constraintErr.Code == "23505" {
						return uuid.Nil, event, service.ErrInvalidResponse
					}
					return uuid.Nil, event, err
				}
			}
		}
	}

	// Return the original saved result on redelivery, even if the payload changed.
	err = tx.QueryRow(ctx, `
		SELECT id, blocks, created_at FROM messages WHERE request_message_id = $1`,
		response.RequestMessageID,
	).Scan(&event.MessageID, &blocks, &event.CreatedAt)
	if err != nil {
		return uuid.Nil, event, err
	}

	if err := json.Unmarshal(blocks, &event.Blocks); err != nil {
		return uuid.Nil, event, err
	}

	if err := tx.Commit(ctx); err != nil {
		return uuid.Nil, event, err
	}

	return userID, event, nil
}
