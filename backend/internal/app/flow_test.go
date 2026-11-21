package app_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/cookiejar"
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
	accountrepo "university-agent/internal/storage/repositories/account"
	agentrepo "university-agent/internal/storage/repositories/agent"
	chatrepo "university-agent/internal/storage/repositories/chat"
	requestrepo "university-agent/internal/storage/repositories/request"
	transport "university-agent/internal/transport/http"
	accountapi "university-agent/internal/transport/http/handlers/account"

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
	server := httptest.NewServer(transport.New(ctx, request, hub, history, accountapi.New(accountrepo.New(db))))
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
	point := models.MapPoint{Title: "Campus", Latitude: 54.720714, Longitude: 55.933422}
	reply := models.AgentResponse{
		RequestMessageID: accepted.MessageID,
		HistorySummary:   "Original summary",
		Blocks: []models.Block{
			{Text: &models.TextBlock{Message: "Answer", Audience: "student", Source: []string{source}}},
			{Attachments: &models.AttachmentsBlock{Attachments: []models.AgentAttachment{{
				ID: attachmentID, Bucket: "images", ObjectKey: "agent/image.png",
				Filename: "image.png", ContentType: "image/png",
			}}}},
			{Text: &models.TextBlock{Message: "Final paragraph"}},
			{Map: &models.MapBlock{Points: []models.MapPoint{point}}},
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
			len(event.Blocks) != 4 || event.Blocks[0].Text.Message != "Answer" ||
			event.Blocks[0].Text.Audience != "student" ||
			event.Blocks[2].Text.Message != "Final paragraph" {
			t.Fatalf("invalid event: %+v", event)
		}
		if got := event.Blocks[0].Text.Source; len(got) != 1 || got[0] != source {
			t.Fatalf("invalid WebSocket sources: %v", got)
		}
		if block := event.Blocks[3].Map; block == nil || len(block.Points) != 1 || block.Points[0] != point {
			t.Fatalf("invalid WebSocket map: %+v", block)
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
		reply.HistorySummary = "Changed summary"
	}

	messages, err := history.History(ctx, accepted.ChatID.String(), userID, "")
	if err != nil || len(messages) != 2 {
		t.Fatalf("history: %+v %v", messages, err)
	}
	if messages[0].Role != "user" || messages[1].Role != "assistant" {
		t.Fatalf("invalid roles: %+v", messages)
	}
	if len(messages[0].Blocks) != 2 || messages[0].Blocks[0].Text.Message != "Question" ||
		len(messages[1].Blocks) != 4 || messages[1].Blocks[0].Text.Message != "Answer" {
		t.Fatalf("invalid history blocks: %+v", messages)
	}
	if got := messages[1].Blocks[0].Text.Source; len(got) != 1 || got[0] != source {
		t.Fatalf("invalid history sources: %v", got)
	}
	if block := messages[1].Blocks[3].Map; block == nil || len(block.Points) != 1 || block.Points[0] != point {
		t.Fatalf("invalid history map: %+v", block)
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

	var followups []uuid.UUID
	for i := 0; i < 7; i++ {
		var followupBody bytes.Buffer
		form := multipart.NewWriter(&followupBody)
		_ = form.WriteField("user_id", userID)
		_ = form.WriteField("chat_id", accepted.ChatID.String())
		_ = form.WriteField("message", fmt.Sprintf("Followup %d", i))
		if err := form.Close(); err != nil {
			t.Fatal(err)
		}
		followupResponse, err := http.Post(server.URL+"/request", form.FormDataContentType(), &followupBody)
		if err != nil {
			t.Fatal(err)
		}
		var next struct {
			ChatID    uuid.UUID `json:"chat_id"`
			MessageID uuid.UUID `json:"message_id"`
		}
		err = json.NewDecoder(followupResponse.Body).Decode(&next)
		followupResponse.Body.Close()
		if err != nil || followupResponse.StatusCode != http.StatusAccepted || next.ChatID != accepted.ChatID {
			t.Fatalf("HTTP followup did not continue the chat: %+v (%v)", next, err)
		}
		followups = append(followups, next.MessageID)
	}
	if err := agent.Dispatch(ctx); err != nil {
		t.Fatal(err)
	}

	var firstFollowup, lastFollowup models.AgentRequest
	for _, item := range publisher.tasks {
		if item.MessageID == followups[0] {
			if err := json.Unmarshal(item.Payload, &firstFollowup); err != nil {
				t.Fatal(err)
			}
		}
		if item.MessageID == followups[6] {
			if err := json.Unmarshal(item.Payload, &lastFollowup); err != nil {
				t.Fatal(err)
			}
		}
	}
	snapshot := firstFollowup.Conversation
	if snapshot == nil || snapshot.HistorySummary != "Original summary" ||
		len(snapshot.RecentTurns) != 1 || snapshot.RecentTurns[0].AssistantMessage != "Answer\nFinal paragraph" {
		t.Fatalf("unexpected first followup context: %+v", snapshot)
	}
	snapshot = lastFollowup.Conversation
	if snapshot == nil || len(snapshot.RecentTurns) != 5 || len(snapshot.OlderTurns) != 1 ||
		snapshot.RecentTurns[0].UserMessage != "Followup 1" ||
		snapshot.OlderTurns[0].UserMessage != "Followup 0" {
		t.Fatalf("unexpected last followup context: %+v", snapshot)
	}

	campusKey := "campus/ishimbay-photo.jpg"
	reply.Blocks = []models.Block{
		{Text: &models.TextBlock{Message: "Followup answer"}},
		{Attachments: &models.AttachmentsBlock{Attachments: []models.AgentAttachment{
			{ID: uuid.New(), Bucket: "images", ObjectKey: campusKey, Filename: "ishimbay.jpg", ContentType: "image/jpeg"},
		}}},
	}
	reply.RequestMessageID = followups[6]
	reply.HistorySummary = "Newer summary"
	if err := agent.HandleResponse(ctx, reply); err != nil {
		t.Fatal(err)
	}
	reply.Blocks[1].Attachments.Attachments[0].ID = uuid.New()
	reply.RequestMessageID = followups[5]
	reply.HistorySummary = "Stale summary"
	if err := agent.HandleResponse(ctx, reply); err != nil {
		t.Fatal(err)
	}

	var summary string
	if err := db.QueryRow(ctx, `SELECT history_summary FROM chats WHERE id = $1`, accepted.ChatID).Scan(&summary); err != nil || summary != "Newer summary" {
		t.Fatalf("unexpected saved annotation: %q (%v)", summary, err)
	}

	for i := 0; i < 2; i++ {
		var event models.ResponseEvent
		if err := ws.ReadJSON(&event); err != nil {
			t.Fatal(err)
		}
		photo := event.Blocks[1].Attachments.Attachments[0]
		if photo.ObjectKey != campusKey || !strings.Contains(photo.URL, "?signature=") {
			t.Fatalf("campus photo URL not signed: %+v", photo)
		}
	}

	messages, err = history.History(ctx, accepted.ChatID.String(), userID, "")
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range messages[len(messages)-2:] {
		photo := entry.Blocks[1].Attachments.Attachments[0]
		if photo.ObjectKey != campusKey || photo.URL == "" {
			t.Fatalf("shared campus photo missing in history: %+v", photo)
		}
	}

	newChat, err := request.Create(ctx, requestservice.Input{UserID: userID, Message: "New chat"})
	if err != nil {
		t.Fatal(err)
	}
	if err := agent.Dispatch(ctx); err != nil {
		t.Fatal(err)
	}
	lastTask := publisher.tasks[len(publisher.tasks)-1]
	if lastTask.MessageID != newChat.MessageID {
		t.Fatalf("new chat task missing: %s", newChat.MessageID)
	}
	var newRequest models.AgentRequest
	if err := json.Unmarshal(lastTask.Payload, &newRequest); err != nil {
		t.Fatal(err)
	}
	if c := newRequest.Conversation; c != nil && (c.HistorySummary != "" || len(c.RecentTurns)+len(c.OlderTurns) != 0) {
		t.Fatalf("new chat inherited previous context: %+v", c)
	}

	t.Run("optional accounts keep their own chats and favorites", func(t *testing.T) {
		testAccountFlow(t, ctx, server, agent)
	})
}

func testAccountFlow(t *testing.T, ctx context.Context, server *httptest.Server, agent *agentservice.Service) {
	t.Helper()
	newBrowser := func() *http.Client {
		jar, err := cookiejar.New(nil)
		if err != nil {
			t.Fatal(err)
		}
		return &http.Client{Transport: server.Client().Transport, Jar: jar}
	}
	call := func(client *http.Client, method, path, body string, status int, out any) {
		t.Helper()
		request, err := http.NewRequestWithContext(ctx, method, server.URL+path, strings.NewReader(body))
		if err != nil {
			t.Fatal(err)
		}
		request.Header.Set("Content-Type", "application/json")
		response, err := client.Do(request)
		if err != nil {
			t.Fatal(err)
		}
		defer response.Body.Close()
		if response.StatusCode != status {
			details, _ := io.ReadAll(response.Body)
			t.Fatalf("%s %s: got %d, want %d: %s", method, path, response.StatusCode, status, details)
		}
		if out != nil {
			if err := json.NewDecoder(response.Body).Decode(out); err != nil {
				t.Fatal(err)
			}
		}
	}

	guest, first, second := newBrowser(), newBrowser(), newBrowser()
	call(guest, "GET", "/account/chats", "", 401, nil)
	var owner models.Account
	const credentials = `{"username":"student-one","password":"test password for accounts"}`
	call(first, "POST", "/account/register", credentials, 200, &owner)
	call(second, "POST", "/account/register", credentials, 409, nil)
	call(second, "POST", "/account/login", `{"username":"student-one","password":"wrong password here"}`, 401, nil)
	call(second, "POST", "/account/login", credentials, 200, nil)

	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	_ = writer.WriteField("message", "My saved question")
	_ = writer.WriteField("user_id", owner.ID.String())
	_ = writer.Close()
	response, err := first.Post(server.URL+"/request", writer.FormDataContentType(), &body)
	if err != nil {
		t.Fatal(err)
	}
	var accepted struct {
		Chat    uuid.UUID `json:"chat_id"`
		Message uuid.UUID `json:"message_id"`
	}
	decodeErr := json.NewDecoder(response.Body).Decode(&accepted)
	response.Body.Close()
	if response.StatusCode != 202 || decodeErr != nil || accepted.Chat == uuid.Nil {
		t.Fatalf("account question was not accepted: %d (%v)", response.StatusCode, decodeErr)
	}
	if err := agent.HandleResponse(ctx, models.AgentResponse{
		RequestMessageID: accepted.Message,
		Blocks:           []models.Block{{Text: &models.TextBlock{Message: "A saved answer"}}},
	}); err != nil {
		t.Fatal(err)
	}
	var chats []models.ChatSummary
	call(second, "GET", "/account/chats", "", 200, &chats)
	if len(chats) != 1 || chats[0].ID != accepted.Chat || chats[0].Title != "My saved question" {
		t.Fatalf("unexpected saved chats: %+v", chats)
	}
	chatPath := "/chats/" + accepted.Chat.String() + "/messages"
	var messages []models.HistoryMessage
	call(second, "GET", chatPath+"?user_id="+owner.ID.String(), "", 200, &messages)
	if len(messages) != 2 || messages[1].Role != "assistant" {
		t.Fatalf("unexpected saved messages: %+v", messages)
	}
	call(guest, "GET", chatPath+"?user_id="+owner.ID.String(), "", 401, nil)
	call(guest, "GET", "/ws?user_id="+owner.ID.String(), "", 401, nil)
	favoritePath := "/account/favorites/" + messages[1].ID.String()
	call(first, "PUT", favoritePath, "", 204, nil)
	call(first, "PUT", favoritePath, "", 204, nil)
	var favorites []models.HistoryMessage
	call(second, "GET", "/account/favorites", "", 200, &favorites)
	if len(favorites) != 1 || favorites[0].ID != messages[1].ID {
		t.Fatalf("unexpected synced favorites: %+v", favorites)
	}
	call(guest, "POST", "/account/register", `{"username":"other-student","password":"another test password"}`, 200, nil)
	call(guest, "GET", chatPath, "", 404, nil)
	call(guest, "PUT", favoritePath, "", 404, nil)
	call(second, "DELETE", favoritePath, "", 204, nil)
	call(first, "GET", "/account/favorites", "", 200, &favorites)
	if len(favorites) != 0 {
		t.Fatalf("favorite was not removed: %+v", favorites)
	}
	call(first, "POST", "/account/logout", "", 204, nil)
	call(first, "GET", "/account/chats", "", 401, nil)
	call(second, "GET", "/account/chats", "", 200, nil)
}
