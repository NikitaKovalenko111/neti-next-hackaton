package chat

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"

	"university-agent/internal/models"
	service "university-agent/internal/services/chat"
	"university-agent/internal/transport/http/identity"
)

type Historian interface {
	History(context.Context, string, string, string) ([]models.HistoryMessage, error)
}

type Handler struct {
	Service     Historian
	ResolveUser identity.Resolver
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	principal, ok := h.ResolveUser(w, r, r.URL.Query().Get("user_id"))
	if !ok {
		return
	}
	messages, err := h.Service.History(r.Context(), r.PathValue("chat_id"), principal.ID.String(), r.URL.Query().Get("after"))
	if err != nil {
		switch {
		case errors.Is(err, service.ErrInvalid):
			http.Error(w, err.Error(), http.StatusBadRequest)
		case errors.Is(err, service.ErrNotFound):
			http.Error(w, err.Error(), http.StatusNotFound)
		default:
			log.Printf("get chat history: %v", err)
			http.Error(w, "storage error", http.StatusInternalServerError)
		}
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(messages)
}
