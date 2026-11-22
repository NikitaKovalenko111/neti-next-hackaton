package auth

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"mime"
	"net/http"
	"strings"
	"time"

	service "university-agent/internal/services/auth"

	"github.com/google/uuid"
)

const socketCookie = "university_agent_token"

type Service interface {
	Register(context.Context, string, string) (service.Session, error)
	Login(context.Context, string, string) (service.Session, error)
	Authenticate(string) (uuid.UUID, time.Time, error)
	Guest(context.Context, uuid.UUID) error
}

type Handler struct {
	Service      Service
	SecureCookie bool
}

func (h Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /register", h.credentials(h.Service.Register, http.StatusCreated))
	mux.HandleFunc("POST /login", h.credentials(h.Service.Login, http.StatusOK))
	mux.HandleFunc("POST /logout", h.logout)
}

func (h Handler) logout(w http.ResponseWriter, r *http.Request) {
	mediaType, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		http.Error(w, "application/json is required", http.StatusUnsupportedMediaType)
		return
	}
	h.setSocketCookie(w, r, "", -1)
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(http.StatusNoContent)
}

func (h Handler) setSocketCookie(w http.ResponseWriter, r *http.Request, token string, maxAge int) {
	http.SetCookie(w, &http.Cookie{
		Name: socketCookie, Value: token, Path: "/ws",
		HttpOnly: true, Secure: h.SecureCookie || r.TLS != nil,
		SameSite: http.SameSiteStrictMode, MaxAge: maxAge,
	})
}

func (h Handler) credentials(operation func(context.Context, string, string) (service.Session, error), status int) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		mediaType, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
		if err != nil || mediaType != "application/json" {
			http.Error(w, "application/json is required", http.StatusUnsupportedMediaType)
			return
		}

		var input struct {
			Login    string `json:"login"`
			Password string `json:"password"`
		}
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&input); err != nil || decoder.Decode(new(any)) != io.EOF {
			http.Error(w, "invalid credentials JSON", http.StatusBadRequest)
			return
		}

		session, err := operation(r.Context(), input.Login, input.Password)
		if err != nil {
			switch {
			case errors.Is(err, service.ErrInvalid):
				http.Error(w, err.Error(), http.StatusBadRequest)
			case errors.Is(err, service.ErrLoginTaken):
				http.Error(w, err.Error(), http.StatusConflict)
			case errors.Is(err, service.ErrUnauthorized):
				http.Error(w, err.Error(), http.StatusUnauthorized)
			default:
				log.Printf("authenticate account: %v", err)
				http.Error(w, "authentication error", http.StatusInternalServerError)
			}
			return
		}

		h.setSocketCookie(w, r, session.AccessToken, session.ExpiresIn)
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		w.WriteHeader(status)
		_ = json.NewEncoder(w).Encode(session)
	}
}

type Identity struct {
	UserID    uuid.UUID
	ExpiresAt time.Time
}

func (i Identity) Registered() bool { return !i.ExpiresAt.IsZero() }

type identityKey struct{}

func FromContext(ctx context.Context) Identity {
	identity, _ := ctx.Value(identityKey{}).(Identity)
	return identity
}

func (h Handler) Resolve(next http.Handler, guestID func(*http.Request) string, socket bool) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var identity Identity
		token, err := accessToken(r, socket)
		if err == nil && token != "" {
			identity.UserID, identity.ExpiresAt, err = h.Service.Authenticate(token)
		} else if err == nil && guestID != nil {
			identity.UserID, err = uuid.Parse(guestID(r))
			if err != nil || identity.UserID == uuid.Nil {
				err = service.ErrUnauthorized
			} else {
				err = h.Service.Guest(r.Context(), identity.UserID)
			}
		} else if err == nil {
			err = service.ErrUnauthorized
		}
		if err != nil {
			if errors.Is(err, service.ErrUnauthorized) {
				w.Header().Set("WWW-Authenticate", "Bearer")
				http.Error(w, "valid authentication is required", http.StatusUnauthorized)
			} else {
				log.Printf("resolve guest: %v", err)
				http.Error(w, "authentication error", http.StatusInternalServerError)
			}
			return
		}
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), identityKey{}, identity)))
	})
}

func accessToken(r *http.Request, socket bool) (string, error) {
	if headers := r.Header.Values("Authorization"); len(headers) != 0 {
		if len(headers) == 1 {
			fields := strings.Fields(headers[0])
			if len(fields) == 2 && strings.EqualFold(fields[0], "Bearer") {
				return fields[1], nil
			}
		}
		return "", service.ErrUnauthorized
	}
	if socket {
		// Browser clients can explicitly open a guest socket after signing in.
		if r.URL.Query().Get("user_id") != "" {
			return "", nil
		}
		if cookie, err := r.Cookie(socketCookie); err == nil {
			return cookie.Value, nil
		}
	}
	return "", nil
}
