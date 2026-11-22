package request

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"

	service "university-agent/internal/services/request"
	"university-agent/internal/transport/http/handlers/auth"
)

const maxRequestSize = 32 << 20

type Creator interface {
	Create(context.Context, service.Input) (service.Result, error)
}

type Handler struct{ Service Creator }

func (h *Handler) WithIdentity(identity auth.Handler) http.Handler {
	handle := identity.Resolve(http.HandlerFunc(h.create), func(r *http.Request) string {
		return r.FormValue("user_id")
	}, false)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		r.Body = http.MaxBytesReader(w, r.Body, maxRequestSize)
		if err := r.ParseMultipartForm(8 << 20); err != nil {
			http.Error(w, "invalid or oversized multipart form", http.StatusBadRequest)
			return
		}
		defer r.MultipartForm.RemoveAll()
		handle.ServeHTTP(w, r)
	})
}

func (h *Handler) create(w http.ResponseWriter, r *http.Request) {
	identity := auth.FromContext(r.Context())
	input := service.Input{
		UserID:     identity.UserID.String(),
		Registered: identity.Registered(),
		ChatID:     r.FormValue("chat_id"),
		Message:    r.FormValue("message"),
	}

	for _, file := range r.MultipartForm.File["attachments"] {
		file := file
		input.Files = append(input.Files, service.File{
			Filename: file.Filename,
			Size:     file.Size,
			Open: func() (io.ReadSeekCloser, error) {
				return file.Open()
			},
		})
	}

	result, err := h.Service.Create(r.Context(), input)
	if err != nil {
		switch {
		case errors.Is(err, service.ErrInvalid):
			http.Error(w, err.Error(), http.StatusBadRequest)
		case errors.Is(err, service.ErrChatNotFound):
			http.Error(w, "chat not found", http.StatusNotFound)
		default:
			log.Printf("create request: %v", err)
			http.Error(w, "storage error", http.StatusInternalServerError)
		}
		return
	}

	type attachment struct {
		ID       string `json:"attachment_id"`
		Filename string `json:"filename"`
	}

	attachments := make([]attachment, 0, len(result.Attachments))
	for _, a := range result.Attachments {
		attachments = append(attachments, attachment{ID: a.ID.String(), Filename: a.Filename})
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(struct {
		ChatID      string       `json:"chat_id"`
		MessageID   string       `json:"message_id"`
		Attachments []attachment `json:"attachments"`
	}{result.ChatID.String(), result.MessageID.String(), attachments})
}
