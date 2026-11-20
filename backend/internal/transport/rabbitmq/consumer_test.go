package rabbitmq

import (
	"context"
	"errors"
	"testing"

	"university-agent/internal/models"
	"university-agent/internal/services/agent"

	amqp "github.com/rabbitmq/amqp091-go"
)

type acknowledger struct {
	ack, nack, reject, requeue bool
}

func (a *acknowledger) Ack(uint64, bool) error { a.ack = true; return nil }
func (a *acknowledger) Nack(_ uint64, _, requeue bool) error {
	a.nack, a.requeue = true, requeue
	return nil
}
func (a *acknowledger) Reject(_ uint64, requeue bool) error {
	a.reject, a.requeue = true, requeue
	return nil
}

type responseHandler struct {
	err    error
	called bool
	ack    *acknowledger
}

func (h *responseHandler) HandleResponse(context.Context, models.AgentResponse) error {
	if h.ack.ack {
		panic("ack before handling response")
	}
	h.called = true
	return h.err
}

func TestDeliveryAcknowledgement(t *testing.T) {
	for _, tc := range []struct {
		name                         string
		body                         string
		handlerErr                   error
		ack, reject, requeue, called bool
	}{
		{name: "success", body: `{}`, ack: true, called: true},
		{name: "invalid json", body: `{`, reject: true},
		{name: "invalid response", body: `{}`, handlerErr: agent.ErrInvalidResponse, reject: true, called: true},
		{name: "database failure", body: `{}`, handlerErr: errors.New("database unavailable"), requeue: true, called: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			ack := &acknowledger{}
			handler := &responseHandler{err: tc.handlerErr, ack: ack}
			retry, err := handleDelivery(context.Background(), amqp.Delivery{Body: []byte(tc.body), Acknowledger: ack}, handler)
			if err != nil || retry != tc.requeue || ack.ack != tc.ack || ack.reject != tc.reject || ack.nack != tc.requeue || ack.requeue != tc.requeue || handler.called != tc.called {
				t.Fatalf("retry=%v ack=%+v called=%v err=%v", retry, ack, handler.called, err)
			}
		})
	}
}
