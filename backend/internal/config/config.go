package config

import (
	"fmt"
	"os"
	"strconv"
)

type Config struct {
	JWTSecret             string
	JWTSecureCookie       bool
	HTTPAddress           string
	PostgresURL           string
	MinIOEndpoint         string
	MinIOPublicEndpoint   string
	MinIORegion           string
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
		JWTSecret:             os.Getenv("JWT_SECRET"),
		HTTPAddress:           env("HTTP_ADDRESS", ":8080"),
		PostgresURL:           env("POSTGRES_URL", "postgres://backend_app:backend_app@localhost:5433/university?sslmode=disable&search_path=backend"),
		MinIOEndpoint:         env("MINIO_ENDPOINT", "localhost:9000"),
		MinIOPublicEndpoint:   env("MINIO_PUBLIC_ENDPOINT", ""),
		MinIORegion:           env("MINIO_REGION", "us-east-1"),
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

	if len(c.JWTSecret) < 32 {
		return Config{}, fmt.Errorf("JWT_SECRET must contain at least 32 bytes")
	}

	var err error
	c.JWTSecureCookie, err = strconv.ParseBool(env("JWT_SECURE_COOKIE", "false"))
	if err != nil {
		return Config{}, fmt.Errorf("JWT_SECURE_COOKIE: %w", err)
	}
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
