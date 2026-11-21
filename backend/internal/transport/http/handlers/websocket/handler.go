package websocket

import (
	"context"
	"net/http"
	"time"

	"university-agent/internal/models"
	"university-agent/internal/transport/http/handlers/auth"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
)

type Subscriber interface {
	Subscribe(uuid.UUID) (<-chan models.ResponseEvent, func())
}

type Handler struct {
	Sessions Subscriber
	Context  context.Context
}

var upgrader = websocket.Upgrader{HandshakeTimeout: 5 * time.Second}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	identity := auth.FromContext(r.Context())
	var expires <-chan time.Time
	if identity.Registered() {
		timer := time.NewTimer(time.Until(identity.ExpiresAt))
		defer timer.Stop()
		expires = timer.C
	}

	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	defer conn.Close()

	events, unsubscribe := h.Sessions.Subscribe(identity.UserID)
	defer unsubscribe()

	conn.SetReadLimit(1024)
	_ = conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	conn.SetPongHandler(func(string) error {
		return conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	})

	done := make(chan struct{})
	go func() {
		defer close(done)
		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				return
			}
		}
	}()

	// The ready event ensures subscription is active before the client posts a request.
	_ = conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
	if err := conn.WriteJSON(map[string]string{"type": "ready"}); err != nil {
		return
	}

	ticker := time.NewTicker(25 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-h.Context.Done():
			return
		case <-expires:
			return
		case <-done:
			return
		case event, ok := <-events:
			if !ok {
				return
			}
			_ = conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := conn.WriteJSON(event); err != nil {
				return
			}
		case <-ticker.C:
			_ = conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}
