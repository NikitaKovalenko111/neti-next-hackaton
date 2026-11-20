package app

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"university-agent/internal/config"
	"university-agent/internal/migrations"
	"university-agent/internal/objectstorage"
	"university-agent/internal/queue"
	agentservice "university-agent/internal/services/agent"
	blockservice "university-agent/internal/services/blocks"
	chatservice "university-agent/internal/services/chat"
	requestservice "university-agent/internal/services/request"
	"university-agent/internal/storage"
	agentrepo "university-agent/internal/storage/repositories/agent"
	chatrepo "university-agent/internal/storage/repositories/chat"
	requestrepo "university-agent/internal/storage/repositories/request"
	transport "university-agent/internal/transport/http"
	"university-agent/internal/transport/rabbitmq"
)

func Run(cfg config.Config) error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	return RunContext(ctx, cfg)
}

func RunContext(parent context.Context, cfg config.Config) error {
	runCtx, stop := context.WithCancel(parent)
	defer stop()

	ctx, cancel := context.WithTimeout(runCtx, 10*time.Second)
	defer cancel()

	db, err := storage.Connect(ctx, cfg.PostgresURL)
	if err != nil {
		return fmt.Errorf("connect postgres: %w", err)
	}
	defer db.Close()

	if err := migrations.Apply(ctx, db); err != nil {
		return fmt.Errorf("apply migrations: %w", err)
	}

	objects, err := objectstorage.New(ctx, cfg)
	if err != nil {
		return fmt.Errorf("connect minio: %w", err)
	}

	conn, err := queue.Connect(cfg.RabbitMQURL, cfg.RabbitMQQueue, cfg.RabbitMQResponseQueue)
	if err != nil {
		return fmt.Errorf("connect rabbitmq: %w", err)
	}
	defer conn.Close()

	objectStore, err := objectstorage.NewStorage(objects, cfg)
	if err != nil {
		return fmt.Errorf("configure object storage: %w", err)
	}
	blocks := blockservice.New(objectStore, cfg.MinIOBucket)
	service := requestservice.New(
		requestrepo.New(db),
		objectStore,
		cfg.MinIOBucket,
	)
	sessions := agentservice.NewHub()
	agent := agentservice.New(
		agentrepo.New(db),
		&queue.Publisher{Conn: conn, RequestQueue: cfg.RabbitMQQueue, ResponseQueue: cfg.RabbitMQResponseQueue},
		sessions,
		blocks,
	)
	history := chatservice.New(chatrepo.New(db), blocks)

	server := &http.Server{
		Addr:              cfg.HTTPAddress,
		Handler:           transport.New(runCtx, service, sessions, history),
		ReadHeaderTimeout: 5 * time.Second,
	}

	var workers sync.WaitGroup
	errorsCh := make(chan error, 2)

	workers.Add(1)
	go func() {
		defer workers.Done()
		agent.RunDispatcher(runCtx)
	}()

	workers.Add(1)
	go func() {
		defer workers.Done()
		errorsCh <- rabbitmq.Consume(runCtx, conn, cfg.RabbitMQResponseQueue, agent)
	}()

	go func() {
		errorsCh <- server.ListenAndServe()
	}()

	var runErr error
	select {
	case <-runCtx.Done():
	case runErr = <-errorsCh:
	}
	stop()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		_ = server.Close()
	}
	_ = conn.Close()
	workers.Wait()

	if errors.Is(runErr, http.ErrServerClosed) {
		return nil
	}
	return runErr
}
