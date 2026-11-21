package account

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"university-agent/internal/models"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct{ db *pgxpool.Pool }

func New(db *pgxpool.Pool) *Repository { return &Repository{db: db} }

func (r *Repository) Register(ctx context.Context, account models.Account, passwordHash, tokenHash, previousHash []byte, expires time.Time) (bool, error) {
	result, err := r.db.Exec(ctx, `
		WITH created AS (
			INSERT INTO accounts (id, username, password_hash) VALUES ($1, $2, $3)
			ON CONFLICT (username) DO NOTHING RETURNING id
		), removed AS (
			DELETE FROM account_sessions WHERE token_hash = $6::bytea AND EXISTS (SELECT FROM created)
		)
		INSERT INTO account_sessions (token_hash, account_id, expires_at) SELECT $4, id, $5 FROM created`,
		account.ID, account.Username, passwordHash, tokenHash, expires, previousHash)
	return err == nil && result.RowsAffected() == 1, err
}

func (r *Repository) Credentials(ctx context.Context, username string) (models.Account, []byte, error) {
	account := models.Account{Username: username}
	var hash []byte
	err := r.db.QueryRow(ctx, `SELECT id, password_hash FROM accounts WHERE username = $1`, username).Scan(&account.ID, &hash)
	if errors.Is(err, pgx.ErrNoRows) {
		return account, nil, nil
	}
	return account, hash, err
}

func (r *Repository) Exists(ctx context.Context, id uuid.UUID) (bool, error) {
	var exists bool
	err := r.db.QueryRow(ctx, `SELECT EXISTS (SELECT FROM accounts WHERE id = $1)`, id).Scan(&exists)
	return exists, err
}

func (r *Repository) Session(ctx context.Context, tokenHash []byte) (*models.Account, error) {
	var account models.Account
	err := r.db.QueryRow(ctx, `
		SELECT a.id, a.username FROM account_sessions s JOIN accounts a ON a.id = s.account_id
		WHERE s.token_hash = $1 AND s.expires_at > now()`, tokenHash).Scan(&account.ID, &account.Username)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	return &account, err
}

func (r *Repository) OpenSession(ctx context.Context, id uuid.UUID, tokenHash, previousHash []byte, expires time.Time) error {
	_, err := r.db.Exec(ctx, `
		WITH removed AS (DELETE FROM account_sessions WHERE token_hash = $4::bytea OR expires_at <= now())
		INSERT INTO account_sessions (account_id, token_hash, expires_at) VALUES ($1, $2, $3)`,
		id, tokenHash, expires, previousHash)
	return err
}

func (r *Repository) CloseSession(ctx context.Context, tokenHash []byte) error {
	_, err := r.db.Exec(ctx, `DELETE FROM account_sessions WHERE token_hash = $1`, tokenHash)
	return err
}

func (r *Repository) Chats(ctx context.Context, accountID uuid.UUID) ([]models.ChatSummary, error) {
	rows, err := r.db.Query(ctx, `
		SELECT c.id, COALESCE((
		    SELECT left(NULLIF(btrim(m.blocks->0->>'message'), ''), 120) FROM messages m
		    WHERE m.chat_id = c.id AND m.role = 'user' ORDER BY m.created_at, m.id LIMIT 1
		), 'Диалог'), COALESCE((
		    SELECT max(m.created_at) FROM messages m WHERE m.chat_id = c.id
		), c.created_at) AS updated_at
		FROM chats c WHERE c.user_id = $1 ORDER BY updated_at DESC, c.id`, accountID)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, pgx.RowToStructByPos[models.ChatSummary])
}

func (r *Repository) Favorites(ctx context.Context, accountID uuid.UUID) ([]models.HistoryMessage, error) {
	rows, err := r.db.Query(ctx, `
		SELECT m.id, m.blocks, m.created_at
		FROM account_favorites f JOIN messages m ON m.id = f.message_id JOIN chats c ON c.id = m.chat_id
		WHERE f.account_id = $1 AND c.user_id = $1 ORDER BY f.created_at DESC, m.id`, accountID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	messages := []models.HistoryMessage{}
	for rows.Next() {
		message := models.HistoryMessage{Role: "assistant", Blocks: []models.Block{}}
		var blocks []models.Block
		var payload []byte
		if err := rows.Scan(&message.ID, &payload, &message.CreatedAt); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(payload, &blocks); err != nil {
			return nil, err
		}
		for _, block := range blocks {
			if block.Attachments == nil {
				message.Blocks = append(message.Blocks, block)
			}
		}
		messages = append(messages, message)
	}
	return messages, rows.Err()
}

func (r *Repository) SaveFavorite(ctx context.Context, accountID, messageID uuid.UUID) (bool, error) {
	result, err := r.db.Exec(ctx, `
		INSERT INTO account_favorites (account_id, message_id)
		SELECT $1, m.id FROM messages m JOIN chats c ON c.id = m.chat_id
		WHERE c.user_id = $1 AND m.id = $2 AND m.role = 'assistant'
		ON CONFLICT (account_id, message_id) DO UPDATE SET message_id = EXCLUDED.message_id`, accountID, messageID)
	return err == nil && result.RowsAffected() == 1, err
}

func (r *Repository) RemoveFavorite(ctx context.Context, accountID, messageID uuid.UUID) error {
	_, err := r.db.Exec(ctx, `DELETE FROM account_favorites WHERE account_id = $1 AND message_id = $2`, accountID, messageID)
	return err
}
