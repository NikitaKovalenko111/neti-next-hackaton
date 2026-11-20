package agent

import (
	"sync"

	"university-agent/internal/models"

	"github.com/google/uuid"
)

// Hub routes events to all active sessions of a user in this backend instance.
type Hub struct {
	mu       sync.Mutex
	sessions map[uuid.UUID]map[chan models.ResponseEvent]struct{}
}

func NewHub() *Hub {
	return &Hub{sessions: make(map[uuid.UUID]map[chan models.ResponseEvent]struct{})}
}

func (h *Hub) Subscribe(userID uuid.UUID) (<-chan models.ResponseEvent, func()) {
	h.mu.Lock()
	defer h.mu.Unlock()

	events := make(chan models.ResponseEvent, 32)
	if h.sessions[userID] == nil {
		h.sessions[userID] = make(map[chan models.ResponseEvent]struct{})
	}
	h.sessions[userID][events] = struct{}{}

	return events, func() {
		h.mu.Lock()
		defer h.mu.Unlock()

		if _, ok := h.sessions[userID][events]; ok {
			delete(h.sessions[userID], events)
			close(events)
		}
		if len(h.sessions[userID]) == 0 {
			delete(h.sessions, userID)
		}
	}
}

func (h *Hub) Notify(userID uuid.UUID, event models.ResponseEvent) {
	h.mu.Lock()
	defer h.mu.Unlock()

	for session := range h.sessions[userID] {
		select {
		case session <- event:
		default:
			// Slow sessions reconnect and recover missed messages from history.
			delete(h.sessions[userID], session)
			close(session)
		}
	}

	if len(h.sessions[userID]) == 0 {
		delete(h.sessions, userID)
	}
}
