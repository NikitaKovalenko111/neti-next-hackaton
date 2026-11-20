package queue

import (
	"context"
	"fmt"

	"university-agent/internal/services/agent"

	amqp "github.com/rabbitmq/amqp091-go"
)

type Publisher struct {
	Conn          *amqp.Connection
	RequestQueue  string
	ResponseQueue string
}

func (p *Publisher) Publish(ctx context.Context, task agent.Task) error {
	if err := ctx.Err(); err != nil {
		return err
	}

	channel, err := p.Conn.Channel()
	if err != nil {
		return err
	}
	defer channel.Close()

	if err := channel.Confirm(false); err != nil {
		return err
	}
	returned := channel.NotifyReturn(make(chan amqp.Return, 1))

	confirmation, err := channel.PublishWithDeferredConfirmWithContext(ctx, "", p.RequestQueue, true, false, amqp.Publishing{
		ContentType:   "application/json",
		DeliveryMode:  amqp.Persistent,
		MessageId:     task.MessageID.String(),
		CorrelationId: task.MessageID.String(),
		ReplyTo:       p.ResponseQueue,
		Body:          task.Payload,
	})
	if err != nil {
		return err
	}

	ack, err := confirmation.WaitContext(ctx)
	if err != nil {
		return err
	}
	if !ack {
		return fmt.Errorf("broker rejected message %s", task.MessageID)
	}

	select {
	case message := <-returned:
		return fmt.Errorf("unroutable message: %s", message.ReplyText)
	default:
		return nil
	}
}
