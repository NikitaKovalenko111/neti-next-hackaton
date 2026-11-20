package agent

import (
	"context"
	"errors"
	"testing"

	"university-agent/internal/models"
	blockservice "university-agent/internal/services/blocks"

	"github.com/google/uuid"
)

type fakeRepository struct {
	tasks   []Task
	saved   bool
	marked  bool
	saveErr error
}

func (r *fakeRepository) Pending(context.Context) ([]Task, error) {
	return r.tasks, nil
}

func (r *fakeRepository) MarkPublished(context.Context, uuid.UUID) error {
	r.marked = true
	return nil
}

func (r *fakeRepository) SaveResponse(_ context.Context, response models.AgentResponse) (uuid.UUID, models.ResponseEvent, error) {
	r.saved = true
	return uuid.New(), models.ResponseEvent{Blocks: response.Blocks}, r.saveErr
}

type fakePublisher struct{ err error }

func (p fakePublisher) Publish(context.Context, Task) error { return p.err }

type fakeNotifier struct {
	repo     *fakeRepository
	notified bool
}

func (n *fakeNotifier) Notify(uuid.UUID, models.ResponseEvent) {
	if !n.repo.saved {
		panic("notification before persistence")
	}
	n.notified = true
}

func TestDispatchKeepsTaskUntilBrokerConfirms(t *testing.T) {
	for _, publishErr := range []error{nil, errors.New("broker unavailable")} {
		repo := &fakeRepository{tasks: []Task{{MessageID: uuid.New()}}}
		service := New(repo, fakePublisher{publishErr}, &fakeNotifier{repo: repo}, blockservice.New(nil, "images"))

		err := service.Dispatch(context.Background())
		if (err != nil) != (publishErr != nil) || repo.marked != (publishErr == nil) {
			t.Fatalf("err=%v marked=%v", err, repo.marked)
		}
	}
}

func TestResponseNotifiesOnlyAfterSuccessfulSave(t *testing.T) {
	for _, saveErr := range []error{nil, errors.New("database unavailable")} {
		repo := &fakeRepository{saveErr: saveErr}
		notifier := &fakeNotifier{repo: repo}
		service := New(repo, fakePublisher{}, notifier, blockservice.New(nil, "images"))

		err := service.HandleResponse(context.Background(), models.AgentResponse{
			RequestMessageID: uuid.New(),
			Blocks:           []models.Block{{Text: &models.TextBlock{Message: "Answer"}}},
		})
		if (err != nil) != (saveErr != nil) || notifier.notified != (saveErr == nil) {
			t.Fatalf("err=%v notified=%v", err, notifier.notified)
		}
	}
}

func TestHubIsolatesUsersAndDisconnectsSlowSessions(t *testing.T) {
	hub := NewHub()
	userID := uuid.New()
	first, cancelFirst := hub.Subscribe(userID)
	defer cancelFirst()
	second, cancelSecond := hub.Subscribe(userID)
	defer cancelSecond()
	other, cancelOther := hub.Subscribe(uuid.New())
	defer cancelOther()

	event := models.ResponseEvent{MessageID: uuid.New()}
	hub.Notify(userID, event)
	if (<-first).MessageID != event.MessageID || (<-second).MessageID != event.MessageID {
		t.Fatal("event was not delivered to both sessions")
	}
	select {
	case <-other:
		t.Fatal("event leaked to another user")
	default:
	}

	for i := 0; i < 33; i++ {
		hub.Notify(userID, event)
	}
	for range first {
	}
	for range second {
	}

	// Unsubscribe remains safe after a slow session has already been removed.
	cancelFirst()
	cancelFirst()
}
