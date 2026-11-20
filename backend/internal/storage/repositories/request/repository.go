package request

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	service "university-agent/internal/services/request"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct{ db *pgxpool.Pool }

func New(db *pgxpool.Pool) *Repository { return &Repository{db: db} }

func (r *Repository) Save(ctx context.Context, record service.Record) error {
	tx, err := r.db.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin transaction: %w", err)
	}
	defer tx.Rollback(context.Background())

	if record.NewChat {
		_, err = tx.Exec(ctx, `INSERT INTO chats (id, user_id) VALUES ($1, $2)`, record.Result.ChatID, record.UserID)
	} else {
		var id uuid.UUID
		err = tx.QueryRow(ctx,
			`SELECT id FROM chats WHERE id = $1 AND user_id = $2 FOR UPDATE`,
			record.Result.ChatID, record.UserID,
		).Scan(&id)
		if errors.Is(err, pgx.ErrNoRows) {
			return service.ErrChatNotFound
		}
	}

	if err != nil {
		return fmt.Errorf("save chat: %w", err)
	}

	blocks, err := json.Marshal(record.Blocks)
	if err != nil {
		return err
	}

	_, err = tx.Exec(ctx,
		`INSERT INTO messages (id, chat_id, content, blocks) VALUES ($1, $2, $3, $4)`,
		record.Result.MessageID, record.Result.ChatID, record.Message, blocks,
	)
	if err != nil {
		return fmt.Errorf("save message: %w", err)
	}

	for _, a := range record.Result.Attachments {
		_, err = tx.Exec(ctx, `
			INSERT INTO attachments
				(attachment_id, message_id, bucket, object_key, filename, content_type, size_bytes)
			VALUES ($1, $2, $3, $4, $5, $6, $7)`,
			a.ID, record.Result.MessageID, a.Bucket, a.Key, a.Filename, a.ContentType, a.Size,
		)
		if err != nil {
			return fmt.Errorf("save attachment: %w", err)
		}
	}

	_, err = tx.Exec(ctx,
		`INSERT INTO agent_request_outbox (message_id, payload) VALUES ($1, $2)`,
		record.Result.MessageID, record.Task,
	)
	if err != nil {
		return fmt.Errorf("save agent task: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("%w: %v", service.ErrCommitUnknown, err)
	}

	return nil
}
