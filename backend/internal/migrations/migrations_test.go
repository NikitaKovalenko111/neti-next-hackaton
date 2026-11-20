package migrations

import (
	"context"
	"encoding/json"
	"os"
	"strings"
	"testing"

	"university-agent/internal/models"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestBlocksMigrationPreservesExistingMessages(t *testing.T) {
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Skip("set TEST_DATABASE_URL to run PostgreSQL migration test")
	}
	ctx := context.Background()
	admin, err := pgxpool.New(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(admin.Close)

	schema := "test_" + strings.ReplaceAll(uuid.NewString(), "-", "")
	quoted := pgx.Identifier{schema}.Sanitize()
	if _, err := admin.Exec(ctx, "CREATE SCHEMA "+quoted); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _, _ = admin.Exec(ctx, "DROP SCHEMA "+quoted+" CASCADE") })

	cfg, err := pgxpool.ParseConfig(url)
	if err != nil {
		t.Fatal(err)
	}
	cfg.ConnConfig.RuntimeParams["search_path"] = schema
	db, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(db.Close)

	// Start from the schema that existed before block support.
	if _, err := db.Exec(ctx, initialSQL+agentSQL+`
		CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY);
		INSERT INTO schema_migrations VALUES (1), (2);`); err != nil {
		t.Fatal(err)
	}
	chatID, messageID, replyID, attachmentID := uuid.New(), uuid.New(), uuid.New(), uuid.New()
	if _, err := db.Exec(ctx, `INSERT INTO chats (id, user_id) VALUES ($1, $2)`, chatID, uuid.New()); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(ctx, `INSERT INTO messages (id, chat_id, content) VALUES ($1, $2, 'Question')`, messageID, chatID); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(ctx, `INSERT INTO messages (id, chat_id, content, role, request_message_id)
		VALUES ($1, $2, 'Old answer', 'assistant', $3)`, replyID, chatID, messageID); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(ctx, `INSERT INTO attachments
		(attachment_id, message_id, bucket, object_key, filename, content_type, size_bytes)
		VALUES ($1, $2, 'images', 'old/image.png', 'image.png', 'image/png', 42)`, attachmentID, messageID); err != nil {
		t.Fatal(err)
	}

	for i := 0; i < 2; i++ {
		if err := Apply(ctx, db); err != nil {
			t.Fatal(err)
		}
	}

	var data []byte
	if err := db.QueryRow(ctx, `SELECT blocks FROM messages WHERE id = $1`, messageID).Scan(&data); err != nil {
		t.Fatal(err)
	}
	var blocks []models.Block
	if err := json.Unmarshal(data, &blocks); err != nil {
		t.Fatal(err)
	}
	if len(blocks) != 2 || blocks[0].Text.Message != "Question" || blocks[1].Attachments.Attachments[0].ID != attachmentID {
		t.Fatalf("legacy message was not preserved: %s", data)
	}

	if err := db.QueryRow(ctx, `SELECT blocks FROM messages WHERE id = $1`, replyID).Scan(&data); err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(data, &blocks); err != nil {
		t.Fatal(err)
	}
	if len(blocks) != 1 || blocks[0].Text.Message != "Old answer" {
		t.Fatalf("legacy response was not preserved: %s", data)
	}
}
