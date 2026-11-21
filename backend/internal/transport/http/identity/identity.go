package identity

import (
	"context"
	"net/http"

	"github.com/google/uuid"
)

type Principal struct {
	ID uuid.UUID
	// Recheck account sessions before delivering events on an open WebSocket.
	Valid func(context.Context) bool
}

type Resolver func(http.ResponseWriter, *http.Request, string) (Principal, bool)
