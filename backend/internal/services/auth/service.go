package auth

import (
	"context"
	"errors"
	"regexp"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"golang.org/x/crypto/bcrypt"
)

var (
	ErrInvalid      = errors.New("login must contain 3 to 32 letters, digits or underscores and password must contain 8 to 72 bytes")
	ErrLoginTaken   = errors.New("login is already taken")
	ErrUnauthorized = errors.New("invalid credentials or token")
	loginPattern    = regexp.MustCompile("^[a-z0-9_]{3,32}$")
)

const TokenTTL = 24 * time.Hour
const issuer = "university-agent"

type Account struct {
	ID           uuid.UUID
	PasswordHash string
}

type Repository interface {
	Create(context.Context, string, Account) error
	Find(context.Context, string) (Account, error)
	Exists(context.Context, uuid.UUID) (bool, error)
}

type Session struct {
	UserID      uuid.UUID `json:"user_id"`
	AccessToken string    `json:"access_token"`
	ExpiresIn   int       `json:"expires_in"`
}

type Service struct {
	repo   Repository
	secret []byte
}

func New(repo Repository, secret string) *Service {
	return &Service{repo: repo, secret: []byte(secret)}
}

func (s *Service) Register(ctx context.Context, login, password string) (Session, error) {
	login = strings.ToLower(strings.TrimSpace(login))
	if !loginPattern.MatchString(login) || len(password) < 8 || len(password) > 72 {
		return Session{}, ErrInvalid
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return Session{}, err
	}
	account := Account{ID: uuid.New(), PasswordHash: string(hash)}
	if err := s.repo.Create(ctx, login, account); err != nil {
		return Session{}, err
	}
	return s.issue(account.ID)
}

func (s *Service) Login(ctx context.Context, login, password string) (Session, error) {
	login = strings.ToLower(strings.TrimSpace(login))
	if !loginPattern.MatchString(login) || len(password) < 8 || len(password) > 72 {
		return Session{}, ErrUnauthorized
	}
	account, err := s.repo.Find(ctx, login)
	if err != nil {
		if !errors.Is(err, ErrUnauthorized) {
			return Session{}, err
		}
		// Perform a comparison for unknown logins as well.
		account.PasswordHash = "$2a$10$C6UzMDM.H6dfI/f/IKcEe.9dhA90ZJht1dftz4IAf/4dZSbhc8SJa"
	}
	if bcrypt.CompareHashAndPassword([]byte(account.PasswordHash), []byte(password)) != nil || err != nil {
		return Session{}, ErrUnauthorized
	}
	return s.issue(account.ID)
}

func (s *Service) issue(id uuid.UUID) (Session, error) {
	now := time.Now()
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Issuer: issuer, Subject: id.String(), IssuedAt: jwt.NewNumericDate(now),
		ExpiresAt: jwt.NewNumericDate(now.Add(TokenTTL)),
	})
	signed, err := token.SignedString(s.secret)
	return Session{UserID: id, AccessToken: signed, ExpiresIn: int(TokenTTL.Seconds())}, err
}

func (s *Service) Authenticate(raw string) (uuid.UUID, time.Time, error) {
	claims := jwt.RegisteredClaims{}
	_, err := jwt.ParseWithClaims(raw, &claims, func(*jwt.Token) (any, error) {
		return s.secret, nil
	}, jwt.WithValidMethods([]string{"HS256"}), jwt.WithIssuer(issuer), jwt.WithExpirationRequired())
	if err != nil {
		return uuid.Nil, time.Time{}, ErrUnauthorized
	}
	id, err := uuid.Parse(claims.Subject)
	if err != nil || id == uuid.Nil {
		return uuid.Nil, time.Time{}, ErrUnauthorized
	}
	return id, claims.ExpiresAt.Time, nil
}

func (s *Service) Guest(ctx context.Context, id uuid.UUID) error {
	exists, err := s.repo.Exists(ctx, id)
	if err != nil {
		return err
	}
	if exists {
		return ErrUnauthorized
	}
	return nil
}
