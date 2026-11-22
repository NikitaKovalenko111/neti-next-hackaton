package transport

import (
	"context"
	"net/http"

	"university-agent/internal/transport/http/handlers/auth"
	"university-agent/internal/transport/http/handlers/chat"
	"university-agent/internal/transport/http/handlers/request"
	"university-agent/internal/transport/http/handlers/system"
	"university-agent/internal/transport/http/handlers/websocket"
)

func New(ctx context.Context, service request.Creator, sessions websocket.Subscriber, history chat.Historian, accounts auth.Service, secureCookie bool) http.Handler {
	mux := http.NewServeMux()
	identity := auth.Handler{Service: accounts, SecureCookie: secureCookie}

	system.Register(mux)
	identity.RegisterRoutes(mux)

	queryGuest := func(r *http.Request) string { return r.URL.Query().Get("user_id") }
	mux.Handle("POST /request", (&request.Handler{Service: service}).WithIdentity(identity))
	mux.Handle("GET /ws", identity.Resolve(&websocket.Handler{Sessions: sessions, Context: ctx}, queryGuest, true))
	chats := &chat.Handler{Service: history}
	mux.Handle("GET /chats", identity.Resolve(http.HandlerFunc(chats.List), nil, false))
	mux.Handle("GET /chats/{chat_id}/messages", identity.Resolve(chats, queryGuest, false))

	return mux
}
