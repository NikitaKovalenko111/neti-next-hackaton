package transport

import (
	"context"
	"net/http"

	"university-agent/internal/transport/http/handlers/chat"
	"university-agent/internal/transport/http/handlers/request"
	"university-agent/internal/transport/http/handlers/system"
	"university-agent/internal/transport/http/handlers/websocket"
)

func New(ctx context.Context, service request.Creator, sessions websocket.Subscriber, history chat.Historian) http.Handler {
	mux := http.NewServeMux()

	system.Register(mux)
	mux.Handle("POST /request", &request.Handler{Service: service})
	mux.Handle("GET /ws", &websocket.Handler{Sessions: sessions, Context: ctx})
	mux.Handle("GET /chats/{chat_id}/messages", &chat.Handler{Service: history})

	return mux
}
