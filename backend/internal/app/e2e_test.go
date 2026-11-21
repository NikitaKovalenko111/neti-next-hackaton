package app_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"university-agent/internal/app"
	"university-agent/internal/config"
	"university-agent/internal/models"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	amqp "github.com/rabbitmq/amqp091-go"
)

// TestFullPipeline runs the actual application with real PostgreSQL, RabbitMQ
// and MinIO. Only the external AI agent is replaced by this test's AMQP client.
func TestFullPipeline(t *testing.T) {
	databaseURL := os.Getenv("TEST_DATABASE_URL")
	brokerURL := os.Getenv("TEST_RABBITMQ_URL")
	minioEndpoint := os.Getenv("TEST_MINIO_ENDPOINT")
	if databaseURL == "" || brokerURL == "" || minioEndpoint == "" {
		t.Skip("set TEST_DATABASE_URL, TEST_RABBITMQ_URL and TEST_MINIO_ENDPOINT for the real-service E2E test")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 40*time.Second)
	defer cancel()

	admin, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatal(err)
	}
	defer admin.Close()

	suffix := strings.ReplaceAll(uuid.NewString(), "-", "")
	schema := "e2e_" + suffix
	quotedSchema := pgx.Identifier{schema}.Sanitize()
	if _, err := admin.Exec(ctx, "CREATE SCHEMA "+quotedSchema); err != nil {
		t.Fatal(err)
	}
	defer admin.Exec(context.Background(), "DROP SCHEMA "+quotedSchema+" CASCADE")

	if strings.HasPrefix(databaseURL, "postgres://") || strings.HasPrefix(databaseURL, "postgresql://") {
		parsed, err := url.Parse(databaseURL)
		if err != nil {
			t.Fatal(err)
		}
		query := parsed.Query()
		query.Set("search_path", schema)
		parsed.RawQuery = query.Encode()
		databaseURL = parsed.String()
	} else {
		databaseURL += " search_path=" + schema
	}

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	address := listener.Addr().String()
	_ = listener.Close()

	cfg := config.Config{
		JWTSecret:             strings.Repeat("a", 32),
		HTTPAddress:           address,
		PostgresURL:           databaseURL,
		RabbitMQURL:           brokerURL,
		RabbitMQQueue:         "e2e.requests." + suffix,
		RabbitMQResponseQueue: "e2e.responses." + suffix,
		MinIOEndpoint:         minioEndpoint,
		MinIOAccessKey:        envOr("TEST_MINIO_ACCESS_KEY", "minioadmin"),
		MinIOSecretKey:        envOr("TEST_MINIO_SECRET_KEY", "minioadmin"),
		MinIOBucket:           "e2e-" + suffix,
	}

	objects, err := minio.New(minioEndpoint, &minio.Options{
		Creds: credentials.NewStaticV4(cfg.MinIOAccessKey, cfg.MinIOSecretKey, ""),
	})
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cleanupCancel()
		for object := range objects.ListObjects(cleanupCtx, cfg.MinIOBucket, minio.ListObjectsOptions{Recursive: true}) {
			if object.Err == nil {
				_ = objects.RemoveObject(cleanupCtx, cfg.MinIOBucket, object.Key, minio.RemoveObjectOptions{})
			}
		}
		_ = objects.RemoveBucket(cleanupCtx, cfg.MinIOBucket)
	}()

	applicationCtx, stopApplication := context.WithCancel(ctx)
	applicationDone := make(chan error, 1)
	go func() { applicationDone <- app.RunContext(applicationCtx, cfg) }()
	var stopOnce sync.Once
	stopBackend := func() {
		stopOnce.Do(func() {
			stopApplication()
			select {
			case err := <-applicationDone:
				if err != nil {
					t.Errorf("application exited: %v", err)
				}
			case <-time.After(12 * time.Second):
				t.Error("application did not stop")
			}
		})
	}
	defer stopBackend()

	baseURL := "http://" + address
	client := &http.Client{Timeout: 3 * time.Second}
	waitFor(t, ctx, "backend health", func() bool {
		select {
		case err := <-applicationDone:
			applicationDone <- err
			t.Fatalf("backend exited during startup: %v", err)
		default:
		}

		response, err := client.Get(baseURL + "/health")
		if err != nil {
			return false
		}
		defer response.Body.Close()
		return response.StatusCode == http.StatusOK
	})

	agentConnection, err := amqp.Dial(brokerURL)
	if err != nil {
		t.Fatal(err)
	}
	defer agentConnection.Close()
	agentChannel, err := agentConnection.Channel()
	if err != nil {
		t.Fatal(err)
	}
	defer agentChannel.Close()
	defer func() {
		_, _ = agentChannel.QueueDelete(cfg.RabbitMQQueue, false, false, false)
		_, _ = agentChannel.QueueDelete(cfg.RabbitMQResponseQueue, false, false, false)
	}()
	defer stopBackend()
	if err := agentChannel.Confirm(false); err != nil {
		t.Fatal(err)
	}
	deliveries, err := agentChannel.ConsumeWithContext(ctx, cfg.RabbitMQQueue, "", false, false, false, false, nil)
	if err != nil {
		t.Fatal(err)
	}

	userID := uuid.NewString()
	connectWebSocket := func() *websocket.Conn {
		connection, _, err := websocket.DefaultDialer.DialContext(ctx, "ws://"+address+"/ws?user_id="+userID, nil)
		if err != nil {
			t.Fatal(err)
		}
		_ = connection.SetReadDeadline(time.Now().Add(10 * time.Second))
		var ready map[string]string
		if err := connection.ReadJSON(&ready); err != nil || ready["type"] != "ready" {
			t.Fatalf("WebSocket ready: %+v %v", ready, err)
		}
		return connection
	}
	webSocket := connectWebSocket()
	defer webSocket.Close()

	image := []byte("\x89PNG\r\n\x1a\nE2E image bytes")
	type accepted struct {
		ChatID    uuid.UUID `json:"chat_id"`
		MessageID uuid.UUID `json:"message_id"`
	}
	post := func(chatID string) accepted {
		var body bytes.Buffer
		form := multipart.NewWriter(&body)
		_ = form.WriteField("user_id", userID)
		_ = form.WriteField("message", "University question")
		if chatID != "" {
			_ = form.WriteField("chat_id", chatID)
		}
		file, err := form.CreateFormFile("attachments", "question.png")
		if err != nil {
			t.Fatal(err)
		}
		_, _ = file.Write(image)
		_ = form.Close()

		response, err := client.Post(baseURL+"/request", form.FormDataContentType(), &body)
		if err != nil {
			t.Fatal(err)
		}
		defer response.Body.Close()
		if response.StatusCode != http.StatusAccepted {
			data, _ := io.ReadAll(response.Body)
			t.Fatalf("POST /request: %d %s", response.StatusCode, data)
		}
		var result accepted
		if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
			t.Fatal(err)
		}
		return result
	}

	receiveTask := func(expected accepted) amqp.Delivery {
		select {
		case delivery, ok := <-deliveries:
			if !ok {
				t.Fatal("agent task consumer closed")
			}
			var task models.AgentRequest
			if err := json.Unmarshal(delivery.Body, &task); err != nil {
				t.Fatal(err)
			}
			if task.MessageID != expected.MessageID || task.ChatID != expected.ChatID || task.UserID.String() != userID ||
				task.Message != "University question" || len(task.Attachments) != 1 ||
				delivery.CorrelationId != expected.MessageID.String() || delivery.ReplyTo != cfg.RabbitMQResponseQueue || delivery.DeliveryMode != amqp.Persistent {
				t.Fatalf("invalid agent task: %+v", task)
			}
			object, err := objects.GetObject(ctx, task.Attachments[0].Bucket, task.Attachments[0].ObjectKey, minio.GetObjectOptions{})
			if err != nil {
				t.Fatal(err)
			}
			data, err := io.ReadAll(object)
			_ = object.Close()
			if err != nil || !bytes.Equal(data, image) {
				t.Fatalf("request image in MinIO: %q %v", data, err)
			}
			return delivery
		case <-ctx.Done():
			t.Fatal("timed out waiting for actual RabbitMQ task")
			return amqp.Delivery{}
		}
	}

	publishReply := func(reply models.AgentResponse) {
		payload, err := json.Marshal(reply)
		if err != nil {
			t.Fatal(err)
		}
		confirmation, err := agentChannel.PublishWithDeferredConfirmWithContext(ctx, "", cfg.RabbitMQResponseQueue, false, false, amqp.Publishing{
			ContentType: "application/json", DeliveryMode: amqp.Persistent, Body: payload,
		})
		if err != nil {
			t.Fatal(err)
		}
		if ok, err := confirmation.WaitContext(ctx); err != nil || !ok {
			t.Fatalf("reply broker confirmation: %v %v", ok, err)
		}
	}

	getHistory := func(chatID uuid.UUID) []models.HistoryMessage {
		response, err := client.Get(fmt.Sprintf("%s/chats/%s/messages?user_id=%s", baseURL, chatID, userID))
		if err != nil {
			t.Fatal(err)
		}
		defer response.Body.Close()
		if response.StatusCode != http.StatusOK {
			t.Fatalf("history: %d", response.StatusCode)
		}
		var messages []models.HistoryMessage
		if err := json.NewDecoder(response.Body).Decode(&messages); err != nil {
			t.Fatal(err)
		}
		return messages
	}

	firstRequest := post("")
	firstTask := receiveTask(firstRequest)
	if history := getHistory(firstRequest.ChatID); len(history) != 1 || history[0].ID != firstRequest.MessageID {
		t.Fatalf("request was not saved before task dispatch: %+v", history)
	}

	outputID := uuid.New()
	outputKey := "agent/" + outputID.String() + ".png"
	if _, err := objects.PutObject(ctx, cfg.MinIOBucket, outputKey, bytes.NewReader(image), int64(len(image)), minio.PutObjectOptions{ContentType: "image/png"}); err != nil {
		t.Fatal(err)
	}
	reply := models.AgentResponse{
		RequestMessageID: firstRequest.MessageID,
		Blocks: []models.Block{
			{Text: &models.TextBlock{Message: "Answer from agent"}},
			{Attachments: &models.AttachmentsBlock{Attachments: []models.AgentAttachment{{
				ID: outputID, Bucket: cfg.MinIOBucket, ObjectKey: outputKey,
				Filename: "answer.png", ContentType: "image/png",
			}}}},
			{Text: &models.TextBlock{Message: "Final paragraph"}},
		},
	}
	publishReply(reply)
	if err := firstTask.Ack(false); err != nil {
		t.Fatal(err)
	}

	var firstEvent models.ResponseEvent
	for i := 0; i < 2; i++ {
		_ = webSocket.SetReadDeadline(time.Now().Add(10 * time.Second))
		var event models.ResponseEvent
		if err := webSocket.ReadJSON(&event); err != nil {
			t.Fatal(err)
		}
		if event.ChatID != firstRequest.ChatID || event.RequestMessageID != firstRequest.MessageID ||
			event.Type != "agent_response" || len(event.Blocks) != 3 || event.Blocks[0].Text.Message != "Answer from agent" {
			t.Fatalf("invalid WebSocket event: %+v", event)
		}
		attachment := event.Blocks[1].Attachments.Attachments[0]
		if attachment.SizeBytes != int64(len(image)) || attachment.ID != outputID {
			t.Fatalf("invalid output attachment: %+v", attachment)
		}
		response, err := client.Get(attachment.URL)
		if err != nil {
			t.Fatal(err)
		}
		data, err := io.ReadAll(response.Body)
		_ = response.Body.Close()
		if err != nil || response.StatusCode != http.StatusOK || !bytes.Equal(data, image) {
			t.Fatalf("signed MinIO URL: status=%d bytes=%q error=%v", response.StatusCode, data, err)
		}
		if i == 0 {
			firstEvent = event
			publishReply(reply)
		} else if event.MessageID != firstEvent.MessageID {
			t.Fatal("redelivered response created a duplicate message")
		}
	}

	messages := getHistory(firstRequest.ChatID)
	if len(messages) != 2 || messages[1].Role != "assistant" || messages[1].ID != firstEvent.MessageID || len(messages[1].Blocks) != 3 {
		t.Fatalf("response was not saved in history: %+v", messages)
	}

	_ = webSocket.Close()
	secondRequest := post(firstRequest.ChatID.String())
	secondTask := receiveTask(secondRequest)
	publishReply(models.AgentResponse{
		RequestMessageID: secondRequest.MessageID,
		Blocks:           []models.Block{{Text: &models.TextBlock{Message: "Offline answer"}}},
	})
	if err := secondTask.Ack(false); err != nil {
		t.Fatal(err)
	}
	waitFor(t, ctx, "offline reply persistence", func() bool {
		return len(getHistory(firstRequest.ChatID)) == 4
	})

	reconnected := connectWebSocket()
	defer reconnected.Close()
	messages = getHistory(firstRequest.ChatID)
	if messages[3].Blocks[0].Text.Message != "Offline answer" || messages[3].RequestMessageID == nil || *messages[3].RequestMessageID != secondRequest.MessageID {
		t.Fatalf("offline response was lost: %+v", messages)
	}
	t.Log("PASS: HTTP + image upload → PostgreSQL/outbox → real RabbitMQ task → agent reply queue → PostgreSQL + real MinIO signed URL → WebSocket; redelivery and offline history")
}

func envOr(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func waitFor(t *testing.T, ctx context.Context, description string, check func() bool) {
	t.Helper()
	for !check() {
		select {
		case <-ctx.Done():
			t.Fatalf("timed out waiting for %s", description)
		case <-time.After(100 * time.Millisecond):
		}
	}
}
