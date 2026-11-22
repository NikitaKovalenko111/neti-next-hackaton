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

const recentTurnLimit = 5
const contextMessageLimit = 2500

func (r *Repository) Save(ctx context.Context, record service.Record) error {
	tx, err := r.db.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin transaction: %w", err)
	}
	defer tx.Rollback(context.Background())

	var summary string
	var summarizedThrough int64
	if record.NewChat {
		_, err = tx.Exec(ctx, `
			INSERT INTO chats (id, user_id, guest_expires_at)
			VALUES ($1, $2, CASE WHEN NOT $3::boolean THEN now() + interval '24 hours' END)`,
			record.Result.ChatID, record.UserID, record.Registered)
	} else {
		err = tx.QueryRow(ctx,
			`
			SELECT history_summary, history_summary_through FROM chats
			WHERE id = $1 AND user_id = $2
			  AND CASE WHEN $3::boolean THEN guest_expires_at IS NULL ELSE guest_expires_at > now() END
			FOR NO KEY UPDATE`,
			record.Result.ChatID, record.UserID, record.Registered,
		).Scan(&summary, &summarizedThrough)
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

	var turnNumber int64
	err = tx.QueryRow(ctx, `
		INSERT INTO messages (id, chat_id, content, blocks, turn_number)
		SELECT $1, $2, $3, $4, COALESCE(MAX(turn_number), 0) + 1
		FROM messages WHERE chat_id = $2 AND role = 'user'
		RETURNING turn_number`,
		record.Result.MessageID, record.Result.ChatID, record.Message, blocks,
	).Scan(&turnNumber)
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

	task := record.Task
	task.Conversation, err = loadConversation(ctx, tx, record.Result.ChatID, turnNumber, summary, summarizedThrough)
	if err != nil {
		return fmt.Errorf("load conversation context: %w", err)
	}
	payload, err := json.Marshal(task)
	if err != nil {
		return fmt.Errorf("encode agent task: %w", err)
	}

	_, err = tx.Exec(ctx,
		`INSERT INTO agent_request_outbox (message_id, payload) VALUES ($1, $2)`,
		record.Result.MessageID, payload,
	)
	if err != nil {
		return fmt.Errorf("save agent task: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("%w: %v", service.ErrCommitUnknown, err)
	}

	return nil
}

func loadConversation(
	ctx context.Context, tx pgx.Tx, chatID uuid.UUID, turnNumber int64, summary string, summarizedThrough int64,
) (*models.ConversationContext, error) {
	conversation := &models.ConversationContext{HistorySummary: summary}
	firstRecent := turnNumber - recentTurnLimit
	rows, err := tx.Query(ctx, `
		SELECT u.turn_number,
		       left(concat_ws(E'\n', nullif(u.content, ''), files.names), $4),
		       left(coalesce(reply.text, ''), $4)
		FROM messages u
		LEFT JOIN messages a ON a.request_message_id = u.id AND a.role = 'assistant'
		LEFT JOIN LATERAL (
		    SELECT 'Прикреплённые файлы: ' || string_agg(f.filename, ', ' ORDER BY f.attachment_id) AS names
		    FROM attachments f WHERE f.message_id = u.id
		) files ON true
		LEFT JOIN LATERAL (
		    SELECT string_agg(block.value->>'message', E'\n' ORDER BY block.position) AS text
		    FROM jsonb_array_elements(a.blocks) WITH ORDINALITY AS block(value, position)
		    WHERE block.value->>'type' = 'text'
		) reply ON true
		WHERE u.chat_id = $1 AND u.role = 'user'
		  AND u.turn_number < $2 AND u.turn_number >= $3
		ORDER BY u.turn_number`,
		chatID, turnNumber, min(firstRecent, summarizedThrough+1), contextMessageLimit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var number int64
		var turn models.ConversationTurn
		if err := rows.Scan(&number, &turn.UserMessage, &turn.AssistantMessage); err != nil {
			return nil, err
		}
		if number >= firstRecent {
			conversation.RecentTurns = append(conversation.RecentTurns, turn)
		} else {
			conversation.OlderTurns = append(conversation.OlderTurns, turn)
		}
	}
	return conversation, rows.Err()
}
