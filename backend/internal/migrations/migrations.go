package migrations

import (
	"context"
	_ "embed"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed 001_chats.sql
var initialSQL string

//go:embed 002_agent_messages.sql
var agentSQL string

//go:embed 003_message_blocks.sql
var blocksSQL string

//go:embed 004_conversation_context.sql
var conversationSQL string

//go:embed 005_accounts.sql
var accountsSQL string

func Apply(ctx context.Context, db *pgxpool.Pool) error {
	tx, err := db.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err = tx.Exec(ctx, `SELECT pg_advisory_xact_lock(781234901)`); err != nil {
		return err
	}
	if _, err = tx.Exec(ctx, `CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)`); err != nil {
		return err
	}

	for index, sql := range []string{initialSQL, agentSQL, blocksSQL, conversationSQL, accountsSQL} {
		version := index + 1
		var exists bool
		if err = tx.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = $1)`, version).Scan(&exists); err != nil {
			return err
		}
		if exists {
			continue
		}

		if _, err = tx.Exec(ctx, sql); err != nil {
			return fmt.Errorf("migration %03d: %w", version, err)
		}
		if _, err = tx.Exec(ctx, `INSERT INTO schema_migrations (version) VALUES ($1)`, version); err != nil {
			return err
		}
	}

	return tx.Commit(ctx)
}
