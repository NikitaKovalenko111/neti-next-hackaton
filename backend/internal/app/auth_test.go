package app_test

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"university-agent/internal/migrations"
	"university-agent/internal/models"
	agentservice "university-agent/internal/services/agent"
	authservice "university-agent/internal/services/auth"
	blockservice "university-agent/internal/services/blocks"
	chatservice "university-agent/internal/services/chat"
	requestservice "university-agent/internal/services/request"
	authrepo "university-agent/internal/storage/repositories/auth"
	chatrepo "university-agent/internal/storage/repositories/chat"
	requestrepo "university-agent/internal/storage/repositories/request"
	transport "university-agent/internal/transport/http"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestAccountAndGuestChatAccess(t *testing.T) {
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Skip("set TEST_DATABASE_URL to run PostgreSQL integration test")
	}
	ctx := t.Context()
	admin, err := pgxpool.New(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	defer admin.Close()
	schema := "test_" + strings.ReplaceAll(uuid.NewString(), "-", "")
	quoted := pgx.Identifier{schema}.Sanitize()
	if _, err := admin.Exec(ctx, "CREATE SCHEMA "+quoted); err != nil {
		t.Fatal(err)
	}
	defer admin.Exec(ctx, "DROP SCHEMA "+quoted+" CASCADE")

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
	if err := migrations.Apply(ctx, db); err != nil {
		t.Fatal(err)
	}

	store := &objects{}
	hub := agentservice.NewHub()
	server := httptest.NewServer(transport.New(ctx,
		requestservice.New(requestrepo.New(db), store, "images"), hub,
		chatservice.New(chatrepo.New(db), blockservice.New(store, "images")),
		authservice.New(authrepo.New(db), strings.Repeat("a", 32)), false,
	))
	defer server.Close()

	credentials := func(path, body string, code int) (authservice.Session, []*http.Cookie) {
		t.Helper()
		res, err := http.Post(server.URL+path, "application/json", strings.NewReader(body))
		if err != nil {
			t.Fatal(err)
		}
		defer res.Body.Close()
		if res.StatusCode != code {
			t.Fatalf("%s got status %d want %d", path, res.StatusCode, code)
		}
		var session authservice.Session
		if code < 300 {
			if err := json.NewDecoder(res.Body).Decode(&session); err != nil {
				t.Fatal(err)
			}
			if session.AccessToken == "" || session.UserID == uuid.Nil {
				t.Fatal("incomplete session")
			}
		}
		return session, res.Cookies()
	}
	account, _ := credentials("/register", `{"login":"Student","password":"long password"}`, 201)
	credentials("/register", `{"login":"student","password":"long password"}`, 409)
	credentials("/login", `{"login":"student","password":"wrong password"}`, 401)
	signedIn, cookies := credentials("/login", `{"login":"student","password":"long password"}`, 200)
	if signedIn.UserID != account.UserID || len(cookies) != 1 || !cookies[0].HttpOnly || cookies[0].Path != "/ws" {
		t.Fatal("login did not restore the account and issue a WebSocket cookie")
	}
	var hash string
	if err := db.QueryRow(ctx, "SELECT password_hash FROM users WHERE id = $1", account.UserID).Scan(&hash); err != nil || !strings.HasPrefix(hash, "$2") {
		t.Fatalf("expected a bcrypt hash: %v", err)
	}

	do := func(method, path, token string, fields map[string]string, code int, into any) {
		t.Helper()
		var body bytes.Buffer
		var contentType string
		if fields != nil {
			form := multipart.NewWriter(&body)
			for key, value := range fields {
				if err := form.WriteField(key, value); err != nil {
					t.Fatal(err)
				}
			}
			if err := form.Close(); err != nil {
				t.Fatal(err)
			}
			contentType = form.FormDataContentType()
		}
		req, err := http.NewRequest(method, server.URL+path, &body)
		if err != nil {
			t.Fatal(err)
		}
		if token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		}
		req.Header.Set("Content-Type", contentType)
		res, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer res.Body.Close()
		if res.StatusCode != code {
			t.Fatalf("%s %s got status %d want %d", method, path, res.StatusCode, code)
		}
		if into != nil {
			if err := json.NewDecoder(res.Body).Decode(into); err != nil {
				t.Fatal(err)
			}
		}
	}

	guest := uuid.NewString()
	var durable, temporary models.Chat
	do("POST", "/request", account.AccessToken, map[string]string{"user_id": guest, "message": "Account chat"}, 202, &durable)
	do("POST", "/request", "", map[string]string{"user_id": guest, "message": "Guest chat"}, 202, &temporary)
	do("POST", "/request", "", map[string]string{"user_id": account.UserID.String(), "message": "Spoof"}, 401, nil)
	do("POST", "/request", "invalid", map[string]string{"user_id": guest, "message": "Fallback"}, 401, nil)

	var chats []models.Chat
	do("GET", "/chats", signedIn.AccessToken, nil, 200, &chats)
	if len(chats) != 1 || chats[0].ID != durable.ID {
		t.Fatalf("wrong saved chats: %+v", chats)
	}
	do("GET", "/chats?user_id="+guest, "", nil, 401, nil)
	do("GET", "/chats/"+durable.ID.String()+"/messages", signedIn.AccessToken, nil, 200, nil)
	do("GET", "/chats/"+durable.ID.String()+"/messages?user_id="+account.UserID.String(), "", nil, 401, nil)
	other, _ := credentials("/register", `{"login":"other","password":"long password"}`, 201)
	do("GET", "/chats?user_id="+account.UserID.String(), other.AccessToken, nil, 200, &chats)
	if len(chats) != 0 {
		t.Fatalf("another account can list saved chats: %+v", chats)
	}
	do("GET", "/chats/"+durable.ID.String()+"/messages", other.AccessToken, nil, 404, nil)
	guestHistory := "/chats/" + temporary.ID.String() + "/messages?user_id=" + guest
	do("GET", guestHistory, "", nil, 200, nil)
	do("GET", guestHistory, signedIn.AccessToken, nil, 404, nil)

	var expiration sql.NullTime
	if err := db.QueryRow(ctx, "SELECT guest_expires_at FROM chats WHERE id = $1", durable.ID).Scan(&expiration); err != nil || expiration.Valid {
		t.Fatalf("account chat must have no expiration: %v", err)
	}
	if _, err := db.Exec(ctx, "UPDATE chats SET guest_expires_at = now() - interval '1 minute' WHERE id = $1", temporary.ID); err != nil {
		t.Fatal(err)
	}
	do("GET", guestHistory, "", nil, 404, nil)
	do("POST", "/request", "", map[string]string{"user_id": guest, "chat_id": temporary.ID.String(), "message": "Expired"}, 404, nil)

	socketURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws"
	headers := http.Header{"Cookie": {cookies[0].Name + "=" + cookies[0].Value}}
	socket, _, err := websocket.DefaultDialer.Dial(socketURL, headers)
	if err != nil {
		t.Fatal(err)
	}
	socket.Close()
	socket, response, err := websocket.DefaultDialer.Dial(socketURL+"?user_id="+account.UserID.String(), nil)
	if socket != nil {
		socket.Close()
	}
	if err == nil || response == nil || response.StatusCode != 401 {
		t.Fatal("guest must not subscribe to an account")
	}
	response.Body.Close()
}
