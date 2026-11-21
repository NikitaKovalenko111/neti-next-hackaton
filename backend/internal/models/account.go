package models

import (
	"time"

	"github.com/google/uuid"
)

type Account struct {
	ID       uuid.UUID `json:"id"`
	Username string    `json:"username"`
}

type ChatSummary struct {
	ID        uuid.UUID `json:"id"`
	Title     string    `json:"title"`
	UpdatedAt time.Time `json:"updated_at"`
}
