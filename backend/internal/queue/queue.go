package queue

import (
	"fmt"

	amqp "github.com/rabbitmq/amqp091-go"
)

func Connect(url, requestQueue, responseQueue string) (*amqp.Connection, error) {
	conn, err := amqp.Dial(url)
	if err != nil {
		return nil, err
	}

	ch, err := conn.Channel()
	if err != nil {
		conn.Close()
		return nil, err
	}
	defer ch.Close()

	for _, name := range []string{requestQueue, responseQueue} {
		if _, err = ch.QueueDeclare(name, true, false, false, false, nil); err != nil {
			conn.Close()
			return nil, fmt.Errorf("declare queue %q: %w", name, err)
		}
	}

	return conn, nil
}
