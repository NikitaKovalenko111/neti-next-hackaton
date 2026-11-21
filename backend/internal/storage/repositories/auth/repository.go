package auth

import (
	"context"
	"errors"

	service "university-agent/internal/services/auth"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct{ db *pgxpool.Pool }

func New(db *pgxpool.Pool) *Repository { return &Repository{db: db} }

func (r *Repository) Create(ctx context.Context, login string, account service.Account) error {
	result, err := r.db.Exec(ctx, `
		INSERT INTO users (id, login, password_hash) VALUES ($1, $2, $3)
		ON CONFLICT (login) DO NOTHING`, account.ID, login, account.PasswordHash)
	if err == nil && result.RowsAffected() == 0 {
		return service.ErrLoginTaken
	}
	return err
}

func (r *Repository) Find(ctx context.Context, login string) (service.Account, error) {
	var account service.Account
	err := r.db.QueryRow(ctx, `SELECT id, password_hash FROM users WHERE login = $1`, login).
		Scan(&account.ID, &account.PasswordHash)
	if errors.Is(err, pgx.ErrNoRows) {
		return service.Account{}, service.ErrUnauthorized
	}
	return account, err
}

func (r *Repository) Exists(ctx context.Context, id uuid.UUID) (bool, error) {
	var exists bool
	err := r.db.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM users WHERE id = $1)`, id).Scan(&exists)
	return exists, err
}
