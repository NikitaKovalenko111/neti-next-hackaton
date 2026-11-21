package models

import (
	"time"

	"github.com/google/uuid"
)

type AgentAttachment struct {
	ID          uuid.UUID `json:"attachment_id"`
	Bucket      string    `json:"bucket"`
	ObjectKey   string    `json:"object_key"`
	Filename    string    `json:"filename"`
	ContentType string    `json:"content_type"`
	SizeBytes   int64     `json:"size_bytes,omitempty"`
	URL         string    `json:"url,omitempty"`
}

type ConversationTurn struct {
	UserMessage      string `json:"user_message"`
	AssistantMessage string `json:"assistant_message,omitempty"`
}

type ConversationContext struct {
	HistorySummary string             `json:"history_summary,omitempty"`
	RecentTurns    []ConversationTurn `json:"recent_turns,omitempty"`
	OlderTurns     []ConversationTurn `json:"older_turns,omitempty"`
}

type AgentRequest struct {
	MessageID    uuid.UUID            `json:"message_id"`
	ChatID       uuid.UUID            `json:"chat_id"`
	UserID       uuid.UUID            `json:"user_id"`
	Message      string               `json:"message"`
	Attachments  []AgentAttachment    `json:"attachments"`
	Conversation *ConversationContext `json:"conversation,omitempty"`
}

type AgentResponse struct {
	RequestMessageID uuid.UUID `json:"request_message_id"`
	Blocks           []Block   `json:"blocks"`
	HistorySummary   string    `json:"history_summary,omitempty"`
}

type ResponseEvent struct {
	Type             string    `json:"type"`
	ChatID           uuid.UUID `json:"chat_id"`
	RequestMessageID uuid.UUID `json:"request_message_id"`
	MessageID        uuid.UUID `json:"message_id"`
	Blocks           []Block   `json:"blocks"`
	CreatedAt        time.Time `json:"created_at"`
}

type HistoryMessage struct {
	ID               uuid.UUID  `json:"message_id"`
	Role             string     `json:"role"`
	Blocks           []Block    `json:"blocks"`
	RequestMessageID *uuid.UUID `json:"request_message_id,omitempty"`
	CreatedAt        time.Time  `json:"created_at"`
}
