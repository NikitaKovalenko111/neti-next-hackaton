package chat

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"

	"university-agent/internal/models"
	service "university-agent/internal/services/chat"
	"university-agent/internal/transport/http/handlers/auth"

	"github.com/google/uuid"
)

type Historian interface {
	List(context.Context, uuid.UUID) ([]models.Chat, error)
	History(context.Context, string, string, string, bool) ([]models.HistoryMessage, error)
}

type Handler struct {
	Service Historian
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	identity := auth.FromContext(r.Context())
	messages, err := h.Service.History(r.Context(), r.PathValue("chat_id"),
		identity.UserID.String(), r.URL.Query().Get("after"), identity.Registered())
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

func (h *Handler) List(w http.ResponseWriter, r *http.Request) {
	chats, err := h.Service.List(r.Context(), auth.FromContext(r.Context()).UserID)
	if err != nil {
		log.Printf("list chats: %v", err)
		http.Error(w, "storage error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(chats)
}
