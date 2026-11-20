package config

import (
	"fmt"
	"os"
	"strconv"
)

type Config struct {
	HTTPAddress           string
	PostgresURL           string
	MinIOEndpoint         string
	MinIOAccessKey        string
	MinIOSecretKey        string
	MinIOBucket           string
	MinIOSecure           bool
	RabbitMQURL           string
	RabbitMQQueue         string
	RabbitMQResponseQueue string
}

func Load() (Config, error) {
	c := Config{
		HTTPAddress:           env("HTTP_ADDRESS", ":8080"),
		PostgresURL:           env("POSTGRES_URL", "postgres://postgres:postgres@localhost:5432/university?sslmode=disable"),
		MinIOEndpoint:         env("MINIO_ENDPOINT", "localhost:9000"),
		MinIOAccessKey:        env("MINIO_ACCESS_KEY", "minioadmin"),
		MinIOSecretKey:        env("MINIO_SECRET_KEY", "minioadmin"),
		MinIOBucket:           env("MINIO_BUCKET", "images"),
		RabbitMQURL:           env("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
		RabbitMQQueue:         env("RABBITMQ_QUEUE", "agent_requests"),
		RabbitMQResponseQueue: env("RABBITMQ_RESPONSE_QUEUE", "agent_responses"),
	}
	if c.RabbitMQQueue == c.RabbitMQResponseQueue {
		return Config{}, fmt.Errorf("RabbitMQ request and response queues must have different names")
	}

	var err error
	c.MinIOSecure, err = strconv.ParseBool(env("MINIO_SECURE", "false"))
	if err != nil {
		return Config{}, fmt.Errorf("MINIO_SECURE: %w", err)
	}
	return c, nil
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
