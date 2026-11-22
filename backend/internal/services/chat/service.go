package chat

import (
	"context"
	"errors"

	"university-agent/internal/models"

	"github.com/google/uuid"
)

var (
	ErrInvalid  = errors.New("invalid chat, user or cursor ID")
	ErrNotFound = errors.New("chat not found")
)

type Repository interface {
	List(context.Context, uuid.UUID) ([]models.Chat, error)
	History(context.Context, uuid.UUID, uuid.UUID, *uuid.UUID, bool) ([]models.HistoryMessage, error)
}

type Service struct {
	repo   Repository
	blocks BlockPresenter
}

type BlockPresenter interface {
	WithURLs(context.Context, []models.Block) ([]models.Block, error)
}

func New(repo Repository, blocks BlockPresenter) *Service {
	return &Service{repo: repo, blocks: blocks}
}

func (s *Service) History(ctx context.Context, chat, user, after string, registered bool) ([]models.HistoryMessage, error) {
	chatID, err := uuid.Parse(chat)
	if err != nil || chatID == uuid.Nil {
		return nil, ErrInvalid
	}

	userID, err := uuid.Parse(user)
	if err != nil || userID == uuid.Nil {
		return nil, ErrInvalid
	}

	var cursor *uuid.UUID
	if after != "" {
		id, err := uuid.Parse(after)
		if err != nil || id == uuid.Nil {
			return nil, ErrInvalid
		}
		cursor = &id
	}

	messages, err := s.repo.History(ctx, chatID, userID, cursor, registered)
	if err != nil {
		return nil, err
	}

	for index := range messages {
		messages[index].Blocks, err = s.blocks.WithURLs(ctx, messages[index].Blocks)
		if err != nil {
			return nil, err
		}
	}

	return messages, nil
}

func (s *Service) List(ctx context.Context, user uuid.UUID) ([]models.Chat, error) {
	return s.repo.List(ctx, user)
}
