package transport

import (
	"context"
	"net/http"
	"net/url"
	"strings"

	"university-agent/internal/transport/http/handlers/account"
	"university-agent/internal/transport/http/handlers/chat"
	"university-agent/internal/transport/http/handlers/request"
	"university-agent/internal/transport/http/handlers/system"
	"university-agent/internal/transport/http/handlers/websocket"
)

func New(ctx context.Context, service request.Creator, sessions websocket.Subscriber, history chat.Historian, accounts *account.Handler) http.Handler {
	mux := http.NewServeMux()

	system.Register(mux)
	accounts.Register(mux)
	mux.Handle("POST /request", &request.Handler{Service: service, ResolveUser: accounts.ResolveUser})
	mux.Handle("GET /ws", &websocket.Handler{Sessions: sessions, Context: ctx, ResolveUser: accounts.ResolveUser})
	mux.Handle("GET /chats/{chat_id}/messages", &chat.Handler{Service: history, ResolveUser: accounts.ResolveUser})

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Method != http.MethodHead && r.Method != http.MethodOptions && !sameOrigin(r) {
			http.Error(w, "cross-origin request", http.StatusForbidden)
			return
		}
		mux.ServeHTTP(w, r)
	})
}

func sameOrigin(r *http.Request) bool {
	site := r.Header.Get("Sec-Fetch-Site")
	if site == "cross-site" {
		return false
	}
	if origin := r.Header.Get("Origin"); origin != "" {
		parsed, err := url.Parse(origin)
		return err == nil && (parsed.Scheme == "https" || parsed.Scheme == "http") && strings.EqualFold(parsed.Host, r.Host)
	}
	return site != "same-site"
}
