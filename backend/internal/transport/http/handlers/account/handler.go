package account

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"io"
	"log"
	"mime"
	"net"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	"university-agent/internal/models"
	"university-agent/internal/storage/repositories/account"
	"university-agent/internal/transport/http/identity"

	"github.com/google/uuid"
	"golang.org/x/crypto/argon2"
)

const (
	cookieName      = "uust_session"
	sessionDuration = 30 * 24 * time.Hour
	saltSize        = 16
)

var usernamePattern = regexp.MustCompile(`^[a-z0-9_.-]{3,32}$`)

type Handler struct {
	repo      *account.Repository
	hashSlots chan struct{}
	mu        sync.Mutex
	resetAt   time.Time
	attempts  map[string]int
}

func New(repo *account.Repository) *Handler {
	return &Handler{repo: repo, hashSlots: make(chan struct{}, 4), attempts: make(map[string]int)}
}

func (h *Handler) Register(mux *http.ServeMux) {
	mux.HandleFunc("GET /account/session", h.session)
	mux.HandleFunc("POST /account/register", h.authenticate(true))
	mux.HandleFunc("POST /account/login", h.authenticate(false))
	mux.HandleFunc("POST /account/logout", h.logout)
	mux.HandleFunc("GET /account/chats", h.chats)
	mux.HandleFunc("GET /account/favorites", h.favorites)
	mux.HandleFunc("PUT /account/favorites/{message_id}", h.changeFavorite)
	mux.HandleFunc("DELETE /account/favorites/{message_id}", h.changeFavorite)
}

func (h *Handler) ResolveUser(w http.ResponseWriter, r *http.Request, supplied string) (identity.Principal, bool) {
	var principal identity.Principal
	hash := sessionHash(r)
	if hash != nil {
		account, err := h.repo.Session(r.Context(), hash)
		if err != nil {
			databaseError(w, err)
			return principal, false
		}
		if account != nil {
			if supplied != "" && supplied != account.ID.String() {
				writeError(w, http.StatusUnauthorized, "Сессия изменилась. Обновите страницу.")
				return principal, false
			}
			principal.ID = account.ID
			principal.Valid = func(ctx context.Context) bool {
				ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
				defer cancel()
				active, err := h.repo.Session(ctx, hash)
				return err == nil && active != nil && active.ID == account.ID
			}
			return principal, true
		}
	}

	id, err := uuid.Parse(supplied)
	if err != nil || id == uuid.Nil {
		writeError(w, http.StatusBadRequest, "Для гостевого диалога нужен идентификатор.")
		return principal, false
	}
	registered, err := h.repo.Exists(r.Context(), id)
	if err != nil {
		databaseError(w, err)
		return principal, false
	}
	if registered {
		writeError(w, http.StatusUnauthorized, "Войдите в аккаунт.")
		return principal, false
	}
	return identity.Principal{ID: id}, true
}

func (h *Handler) session(w http.ResponseWriter, r *http.Request) {
	var current *models.Account
	if hash := sessionHash(r); hash != nil {
		var err error
		current, err = h.repo.Session(r.Context(), hash)
		if err != nil {
			databaseError(w, err)
			return
		}
	}
	writeJSON(w, http.StatusOK, current)
}

func (h *Handler) authenticate(register bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var input struct {
			Username string `json:"username"`
			Password string `json:"password"`
		}
		media, _, _ := mime.ParseMediaType(r.Header.Get("Content-Type"))
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		decoder.DisallowUnknownFields()
		if media != "application/json" || decoder.Decode(&input) != nil || decoder.Decode(new(any)) != io.EOF {
			writeError(w, http.StatusBadRequest, "Проверьте логин и пароль.")
			return
		}
		username := strings.ToLower(strings.TrimSpace(input.Username))
		if !usernamePattern.MatchString(username) || len(input.Password) > 1024 || utf8.RuneCountInString(input.Password) < 12 {
			writeError(w, http.StatusBadRequest, "Логин должен содержать 3–32 символа латиницей, цифры, точку, дефис или подчёркивание. Пароль — от 12 символов.")
			return
		}
		if !h.allowAttempt(r) {
			w.Header().Set("Retry-After", "60")
			writeError(w, http.StatusTooManyRequests, "Слишком много попыток. Попробуйте через минуту.")
			return
		}
		select {
		case h.hashSlots <- struct{}{}:
			defer func() { <-h.hashSlots }()
		default:
			writeError(w, http.StatusTooManyRequests, "Попробуйте ещё раз через несколько секунд.")
			return
		}

		tokenBytes := make([]byte, 32)
		_, _ = rand.Read(tokenBytes)
		token := base64.RawURLEncoding.EncodeToString(tokenBytes)
		hash := sha256.Sum256(tokenBytes)
		expires := time.Now().Add(sessionDuration)
		account := models.Account{ID: uuid.New(), Username: username}
		var err error
		if register {
			salt := make([]byte, saltSize)
			_, _ = rand.Read(salt)
			password := append(salt, derivePassword(input.Password, salt)...)
			var created bool
			created, err = h.repo.Register(r.Context(), account, password, hash[:], sessionHash(r), expires)
			if err == nil && !created {
				writeError(w, http.StatusConflict, "Этот логин уже занят.")
				return
			}
		} else {
			var password []byte
			account, password, err = h.repo.Credentials(r.Context(), username)
			if err == nil && !verifyPassword(input.Password, password) {
				writeError(w, http.StatusUnauthorized, "Неверный логин или пароль.")
				return
			}
			if err == nil {
				err = h.repo.OpenSession(r.Context(), account.ID, hash[:], sessionHash(r), expires)
			}
		}
		if err != nil {
			databaseError(w, err)
			return
		}
		setCookie(w, r, token, int(sessionDuration/time.Second))
		writeJSON(w, http.StatusOK, account)
	}
}

func derivePassword(password string, salt []byte) []byte {
	return argon2.IDKey([]byte(password), salt, 2, 19*1024, 1, 32)
}

func verifyPassword(password string, stored []byte) bool {
	valid := len(stored) == saltSize+32
	if !valid {
		stored = make([]byte, saltSize+32)
	}
	return subtle.ConstantTimeCompare(derivePassword(password, stored[:saltSize]), stored[saltSize:]) == 1 && valid
}

func (h *Handler) allowAttempt(r *http.Request) bool {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		host = r.RemoteAddr
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	now := time.Now()
	if !now.Before(h.resetAt) {
		clear(h.attempts)
		h.resetAt = now.Add(time.Minute)
	}
	if h.attempts[host] >= 20 || len(h.attempts) >= 4096 {
		return false
	}
	h.attempts[host]++
	return true
}

func sessionHash(r *http.Request) []byte {
	cookie, err := r.Cookie(cookieName)
	if err != nil {
		return nil
	}
	token, err := base64.RawURLEncoding.DecodeString(cookie.Value)
	if err != nil || len(token) != 32 {
		return nil
	}
	hash := sha256.Sum256(token)
	return hash[:]
}

func setCookie(w http.ResponseWriter, r *http.Request, token string, maxAge int) {
	host := r.Host
	if name, _, err := net.SplitHostPort(r.Host); err == nil {
		host = name
	}
	local := host == "localhost" || net.ParseIP(strings.Trim(host, "[]")).IsLoopback()
	http.SetCookie(w, &http.Cookie{
		Name: cookieName, Value: token, Path: "/", HttpOnly: true, SameSite: http.SameSiteStrictMode,
		Secure: r.TLS != nil || !local, MaxAge: maxAge,
	})
}

func (h *Handler) requireAccount(w http.ResponseWriter, r *http.Request) *models.Account {
	hash := sessionHash(r)
	if hash != nil {
		account, err := h.repo.Session(r.Context(), hash)
		if err != nil {
			databaseError(w, err)
			return nil
		}
		expected := r.Header.Get("X-UUST-Account")
		if account != nil && (expected == "" || expected == account.ID.String()) {
			return account
		}
	}
	writeError(w, http.StatusUnauthorized, "Войдите в аккаунт.")
	return nil
}

func (h *Handler) logout(w http.ResponseWriter, r *http.Request) {
	if hash := sessionHash(r); hash != nil {
		if expected := r.Header.Get("X-UUST-Account"); expected != "" {
			current, err := h.repo.Session(r.Context(), hash)
			if err != nil {
				databaseError(w, err)
				return
			}
			if current != nil && current.ID.String() != expected {
				writeError(w, http.StatusUnauthorized, "Сессия изменилась. Обновите страницу.")
				return
			}
		}
		if err := h.repo.CloseSession(r.Context(), hash); err != nil {
			databaseError(w, err)
			return
		}
	}
	setCookie(w, r, "", -1)
	w.WriteHeader(http.StatusNoContent)
}

func (h *Handler) chats(w http.ResponseWriter, r *http.Request) {
	account := h.requireAccount(w, r)
	if account == nil {
		return
	}
	chats, err := h.repo.Chats(r.Context(), account.ID)
	if err != nil {
		databaseError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, chats)
}

func (h *Handler) favorites(w http.ResponseWriter, r *http.Request) {
	account := h.requireAccount(w, r)
	if account == nil {
		return
	}
	favorites, err := h.repo.Favorites(r.Context(), account.ID)
	if err != nil {
		databaseError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, favorites)
}

func (h *Handler) changeFavorite(w http.ResponseWriter, r *http.Request) {
	account := h.requireAccount(w, r)
	if account == nil {
		return
	}
	id, err := uuid.Parse(r.PathValue("message_id"))
	if err != nil || id == uuid.Nil {
		writeError(w, http.StatusBadRequest, "Некорректный ответ.")
		return
	}
	if r.Method == http.MethodPut {
		var saved bool
		saved, err = h.repo.SaveFavorite(r.Context(), account.ID, id)
		if err == nil && !saved {
			writeError(w, http.StatusNotFound, "Ответ не найден.")
			return
		}
	} else {
		err = h.repo.RemoveFavorite(r.Context(), account.ID, id)
	}
	if err != nil {
		databaseError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}

func databaseError(w http.ResponseWriter, err error) {
	log.Printf("account storage: %v", err)
	writeError(w, http.StatusInternalServerError, "Не удалось связаться с аккаунтом. Попробуйте ещё раз.")
}
