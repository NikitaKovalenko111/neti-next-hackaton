package chat

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"

	"university-agent/internal/models"
	service "university-agent/internal/services/chat"
)

type Historian interface {
	History(context.Context, string, string, string) ([]models.HistoryMessage, error)
}

type Handler struct {
	Service Historian
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	messages, err := h.Service.History(r.Context(), r.PathValue("chat_id"), r.URL.Query().Get("user_id"), r.URL.Query().Get("after"))
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
