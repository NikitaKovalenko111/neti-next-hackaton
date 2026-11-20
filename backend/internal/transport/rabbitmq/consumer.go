package rabbitmq

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"time"

	"university-agent/internal/models"
	"university-agent/internal/services/agent"

	amqp "github.com/rabbitmq/amqp091-go"
)

type ResponseHandler interface {
	HandleResponse(context.Context, models.AgentResponse) error
}

func Consume(ctx context.Context, conn *amqp.Connection, queue string, handler ResponseHandler) error {
	channel, err := conn.Channel()
	if err != nil {
		return err
	}
	defer channel.Close()

	if err := channel.Qos(1, 0, false); err != nil {
		return err
	}

	deliveries, err := channel.ConsumeWithContext(ctx, queue, "", false, false, false, false, nil)
	if err != nil {
		return err
	}

	for {
		select {
		case <-ctx.Done():
			return nil
		case delivery, ok := <-deliveries:
			if !ok {
				if ctx.Err() != nil {
					return nil
				}
				return fmt.Errorf("agent response consumer disconnected")
			}

			retry, err := handleDelivery(ctx, delivery, handler)
			if err != nil {
				return err
			}
			if !retry {
				continue
			}

			select {
			case <-ctx.Done():
				return nil
			case <-time.After(time.Second):
			}
		}
	}
}

func handleDelivery(ctx context.Context, delivery amqp.Delivery, handler ResponseHandler) (bool, error) {
	var response models.AgentResponse
	err := json.Unmarshal(delivery.Body, &response)
	if err == nil {
		handleCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
		err = handler.HandleResponse(handleCtx, response)
		cancel()
	} else {
		err = fmt.Errorf("%w: %v", agent.ErrInvalidResponse, err)
	}

	if err == nil {
		return false, delivery.Ack(false)
	}

	log.Printf("process agent response: %v", err)
	if errors.Is(err, agent.ErrInvalidResponse) {
		return false, delivery.Reject(false)
	}

	return true, delivery.Nack(false, true)
}
