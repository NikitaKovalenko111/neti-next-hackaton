package request

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"university-agent/internal/models"
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

	if !record.NewChat {
		rows, err := tx.Query(ctx, `
			SELECT role, left(btrim(body), 500) AS message
			FROM (
				SELECT role, created_at, id, COALESCE((
					SELECT string_agg(part->>'message', chr(10) ORDER BY block_index)
					FROM jsonb_array_elements(blocks) WITH ORDINALITY AS parts(part, block_index)
					WHERE part->>'type' = 'text'
				), content) AS body
				FROM messages WHERE chat_id = $1
				ORDER BY created_at DESC, id DESC LIMIT 8
			) AS recent
			WHERE btrim(body) <> ''
			ORDER BY created_at, id`, record.Result.ChatID)
		if err != nil {
			return fmt.Errorf("load conversation for agent: %w", err)
		}
		record.Task.History, err = pgx.CollectRows(rows, pgx.RowToStructByName[models.DialogueTurn])
		if err != nil {
			return fmt.Errorf("read conversation for agent: %w", err)
		}
	}
	task, err := json.Marshal(record.Task)
	if err != nil {
		return fmt.Errorf("encode agent request: %w", err)
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
		record.Result.MessageID, task,
	)
	if err != nil {
		return fmt.Errorf("save agent task: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("%w: %v", service.ErrCommitUnknown, err)
	}

	return nil
}
