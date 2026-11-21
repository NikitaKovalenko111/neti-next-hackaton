package app_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"university-agent/internal/migrations"
	"university-agent/internal/models"
	agentservice "university-agent/internal/services/agent"
	blockservice "university-agent/internal/services/blocks"
	chatservice "university-agent/internal/services/chat"
	requestservice "university-agent/internal/services/request"
	agentrepo "university-agent/internal/storage/repositories/agent"
	chatrepo "university-agent/internal/storage/repositories/chat"
	requestrepo "university-agent/internal/storage/repositories/request"
	transport "university-agent/internal/transport/http"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type objects struct{ signed atomic.Int64 }

func (*objects) Put(context.Context, string, io.Reader, int64, string) error { return nil }
func (*objects) Delete(context.Context, string) error                        { return nil }
func (*objects) Stat(context.Context, string, string) (int64, bool, error)   { return 12, true, nil }
func (o *objects) URL(_ context.Context, bucket, key string) (string, error) {
	return fmt.Sprintf("https://minio.test/%s/%s?signature=%d", bucket, key, o.signed.Add(1)), nil
}

type publisher struct{ tasks []agentservice.Task }

func (p *publisher) Publish(_ context.Context, task agentservice.Task) error {
	p.tasks = append(p.tasks, task)
	return nil
}

func TestRequestAgentWebSocketFlow(t *testing.T) {
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Skip("set TEST_DATABASE_URL to run PostgreSQL integration test")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	admin, err := pgxpool.New(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	defer admin.Close()

	schema := "test_" + strings.ReplaceAll(uuid.NewString(), "-", "")
	quotedSchema := pgx.Identifier{schema}.Sanitize()
	if _, err := admin.Exec(ctx, "CREATE SCHEMA "+quotedSchema); err != nil {
		t.Fatal(err)
	}
	defer admin.Exec(context.Background(), "DROP SCHEMA "+quotedSchema+" CASCADE")

	cfg, err := pgxpool.ParseConfig(url)
	if err != nil {
		t.Fatal(err)
	}
	cfg.ConnConfig.RuntimeParams["search_path"] = schema
	db, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	for i := 0; i < 2; i++ {
		if err := migrations.Apply(ctx, db); err != nil {
			t.Fatal(err)
		}
	}

	hub := agentservice.NewHub()
	publisher := &publisher{}
	store := &objects{}
	blocks := blockservice.New(store, "images")
	agent := agentservice.New(agentrepo.New(db), publisher, hub, blocks)
	request := requestservice.New(requestrepo.New(db), store, "images")
	history := chatservice.New(chatrepo.New(db), blocks)
	server := httptest.NewServer(transport.New(ctx, request, hub, history))
	defer server.Close()

	userID := uuid.NewString()
	ws, _, err := websocket.DefaultDialer.Dial("ws"+strings.TrimPrefix(server.URL, "http")+"/ws?user_id="+userID, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer ws.Close()
	_ = ws.SetReadDeadline(time.Now().Add(5 * time.Second))
	var ready map[string]string
	if err := ws.ReadJSON(&ready); err != nil || ready["type"] != "ready" {
		t.Fatalf("ready: %v %v", ready, err)
	}

	var body bytes.Buffer
	form := multipart.NewWriter(&body)
	_ = form.WriteField("user_id", userID)
	_ = form.WriteField("message", "Question")
	file, err := form.CreateFormFile("attachments", "image.png")
	if err != nil {
		t.Fatal(err)
	}
	_, _ = file.Write([]byte("\x89PNG\r\n\x1a\nimage"))
	_ = form.Close()

	response, err := http.Post(server.URL+"/request", form.FormDataContentType(), &body)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusAccepted {
		data, _ := io.ReadAll(response.Body)
		t.Fatalf("POST: %d %s", response.StatusCode, data)
	}
	var accepted struct {
		ChatID    uuid.UUID `json:"chat_id"`
		MessageID uuid.UUID `json:"message_id"`
	}
	if err := json.NewDecoder(response.Body).Decode(&accepted); err != nil {
		t.Fatal(err)
	}

	if err := agent.Dispatch(ctx); err != nil {
		t.Fatal(err)
	}
	if len(publisher.tasks) != 1 {
		t.Fatalf("published %d tasks", len(publisher.tasks))
	}
	var task models.AgentRequest
	if err := json.Unmarshal(publisher.tasks[0].Payload, &task); err != nil {
		t.Fatal(err)
	}
	if task.MessageID != accepted.MessageID || len(task.Attachments) != 1 || task.Attachments[0].Bucket != "images" {
		t.Fatalf("invalid task: %+v", task)
	}
	if err := agent.Dispatch(ctx); err != nil || len(publisher.tasks) != 1 {
		t.Fatal("outbox sent confirmed task again")
	}

	attachmentID := uuid.New()
	source := "https://uust.ru/reception/pass-application/"
	reply := models.AgentResponse{
		RequestMessageID: accepted.MessageID,
		Blocks: []models.Block{
			{Text: &models.TextBlock{Message: "Answer", Source: []string{source}}},
			{Attachments: &models.AttachmentsBlock{Attachments: []models.AgentAttachment{{
				ID: attachmentID, Bucket: "images", ObjectKey: "agent/image.png",
				Filename: "image.png", ContentType: "image/png",
			}}}},
			{Text: &models.TextBlock{Message: "Final paragraph"}},
		},
	}
	var first models.ResponseEvent
	for i := 0; i < 2; i++ {
		if err := agent.HandleResponse(ctx, reply); err != nil {
			t.Fatal(err)
		}
		var event models.ResponseEvent
		if err := ws.ReadJSON(&event); err != nil {
			t.Fatal(err)
		}
		if event.Type != "agent_response" || event.ChatID != accepted.ChatID ||
			len(event.Blocks) != 3 || event.Blocks[0].Text.Message != "Answer" ||
			event.Blocks[2].Text.Message != "Final paragraph" {
			t.Fatalf("invalid event: %+v", event)
		}
		if got := event.Blocks[0].Text.Source; len(got) != 1 || got[0] != source {
			t.Fatalf("invalid WebSocket sources: %v", got)
		}
		attachment := event.Blocks[1].Attachments.Attachments[0]
		if attachment.ID != attachmentID || attachment.SizeBytes != 12 || attachment.URL == "" {
			t.Fatalf("invalid response attachment: %+v", attachment)
		}
		if i == 0 {
			first = event
		} else if event.MessageID != first.MessageID {
			t.Fatal("redelivery created duplicate response")
		}
		// A redelivery must use the saved blocks, even if the new payload changed.
		reply.Blocks[0].Text.Message = "Changed answer"
	}

	messages, err := history.History(ctx, accepted.ChatID.String(), userID, "")
	if err != nil || len(messages) != 2 {
		t.Fatalf("history: %+v %v", messages, err)
	}
	if messages[0].Role != "user" || messages[1].Role != "assistant" {
		t.Fatalf("invalid roles: %+v", messages)
	}
	if len(messages[0].Blocks) != 2 || messages[0].Blocks[0].Text.Message != "Question" ||
		len(messages[1].Blocks) != 3 || messages[1].Blocks[0].Text.Message != "Answer" {
		t.Fatalf("invalid history blocks: %+v", messages)
	}
	if got := messages[1].Blocks[0].Text.Source; len(got) != 1 || got[0] != source {
		t.Fatalf("invalid history sources: %v", got)
	}
	if messages[1].Blocks[1].Attachments.Attachments[0].URL == first.Blocks[1].Attachments.Attachments[0].URL {
		t.Fatal("history did not generate a fresh attachment URL")
	}

	var count int
	if err := db.QueryRow(ctx, `SELECT count(*) FROM attachments WHERE message_id = $1`, first.MessageID).Scan(&count); err != nil || count != 1 {
		t.Fatalf("response attachments: %d %v", count, err)
	}
	var persisted []byte
	if err := db.QueryRow(ctx, `SELECT blocks FROM messages WHERE id = $1`, first.MessageID).Scan(&persisted); err != nil || bytes.Contains(persisted, []byte(`"url"`)) {
		t.Fatalf("signed URL was persisted: %s %v", persisted, err)
	}
	if _, err := history.History(ctx, accepted.ChatID.String(), uuid.NewString(), ""); err != chatservice.ErrNotFound {
		t.Fatalf("other user history: %v", err)
	}
	messages, err = history.History(ctx, accepted.ChatID.String(), userID, accepted.MessageID.String())
	if err != nil || len(messages) != 1 || messages[0].ID != first.MessageID {
		t.Fatalf("cursor: %+v %v", messages, err)
	}
}
