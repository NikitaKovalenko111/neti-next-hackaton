package agent

import (
	"context"
	"errors"
	"fmt"
	"log"
	"time"

	"university-agent/internal/models"
	blockservice "university-agent/internal/services/blocks"

	"github.com/google/uuid"
)

var ErrInvalidResponse = errors.New("invalid agent response")

type Task struct {
	MessageID uuid.UUID
	Payload   []byte
}

type Repository interface {
	Pending(context.Context) ([]Task, error)
	MarkPublished(context.Context, uuid.UUID) error
	SaveResponse(context.Context, models.AgentResponse) (uuid.UUID, models.ResponseEvent, error)
}

type Publisher interface {
	Publish(context.Context, Task) error
}

type Notifier interface {
	Notify(uuid.UUID, models.ResponseEvent)
}

type Blocks interface {
	Validate(context.Context, []models.Block) error
	WithURLs(context.Context, []models.Block) ([]models.Block, error)
}

type Service struct {
	repo      Repository
	publisher Publisher
	notifier  Notifier
	blocks    Blocks
}

func New(repo Repository, publisher Publisher, notifier Notifier, blocks Blocks) *Service {
	return &Service{repo: repo, publisher: publisher, notifier: notifier, blocks: blocks}
}

func (s *Service) HandleResponse(ctx context.Context, response models.AgentResponse) error {
	if response.RequestMessageID == uuid.Nil {
		return ErrInvalidResponse
	}

	if err := s.blocks.Validate(ctx, response.Blocks); err != nil {
		if errors.Is(err, blockservice.ErrInvalid) {
			return fmt.Errorf("%w: %v", ErrInvalidResponse, err)
		}
		return err
	}

	userID, event, err := s.repo.SaveResponse(ctx, response)
	if err != nil {
		return err
	}

	event.Blocks, err = s.blocks.WithURLs(ctx, event.Blocks)
	if err != nil {
		return err
	}

	s.notifier.Notify(userID, event)
	return nil
}

func (s *Service) Dispatch(ctx context.Context) error {
	tasks, err := s.repo.Pending(ctx)
	if err != nil {
		return err
	}

	for _, task := range tasks {
		if err := s.publisher.Publish(ctx, task); err != nil {
			return fmt.Errorf("publish task %s: %w", task.MessageID, err)
		}

		if err := s.repo.MarkPublished(ctx, task.MessageID); err != nil {
			return err
		}
	}

	return nil
}

func (s *Service) RunDispatcher(ctx context.Context) {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()

	for {
		batchCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
		err := s.Dispatch(batchCtx)
		cancel()
		if err != nil && ctx.Err() == nil {
			log.Printf("dispatch agent tasks: %v", err)
		}

		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
