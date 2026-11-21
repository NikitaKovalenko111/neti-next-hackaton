package request

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"university-agent/internal/models"

	"github.com/google/uuid"
)

var (
	ErrInvalid       = errors.New("invalid request")
	ErrChatNotFound  = errors.New("chat not found")
	ErrCommitUnknown = errors.New("commit outcome unknown")
)

type File struct {
	Filename string
	Size     int64
	Open     func() (io.ReadSeekCloser, error)
}

type Input struct {
	UserID  string
	ChatID  string
	Message string
	Files   []File
}

type Attachment struct {
	ID          uuid.UUID
	Filename    string
	Bucket      string
	Key         string
	ContentType string
	Size        int64
}

type Result struct {
	ChatID, MessageID uuid.UUID
	Attachments       []Attachment
}

type Record struct {
	UserID  uuid.UUID
	NewChat bool
	Message string
	Result  Result
	Task    models.AgentRequest
	Blocks  []models.Block
}

type Repository interface {
	Save(context.Context, Record) error
}

type ObjectStorage interface {
	Put(context.Context, string, io.Reader, int64, string) error
	Delete(context.Context, string) error
}

type Service struct {
	repo    Repository
	objects ObjectStorage
	bucket  string
}

func New(repo Repository, objects ObjectStorage, bucket string) *Service {
	return &Service{repo, objects, bucket}
}

func (s *Service) Create(ctx context.Context, input Input) (Result, error) {
	userID, err := uuid.Parse(input.UserID)
	if err != nil || userID == uuid.Nil {
		return Result{}, fmt.Errorf("%w: valid user_id is required", ErrInvalid)
	}

	message := strings.TrimSpace(input.Message)
	if message == "" && len(input.Files) == 0 {
		return Result{}, fmt.Errorf("%w: message or attachments required", ErrInvalid)
	}

	chatID := uuid.New()
	newChat := input.ChatID == ""
	if !newChat {
		chatID, err = uuid.Parse(input.ChatID)
		if err != nil || chatID == uuid.Nil {
			return Result{}, fmt.Errorf("%w: invalid chat_id", ErrInvalid)
		}
	}

	result := Result{
		ChatID:      chatID,
		MessageID:   uuid.New(),
		Attachments: make([]Attachment, 0, len(input.Files)),
	}

	var uploaded []string
	keep := false
	defer func() {
		if keep {
			return
		}

		cleanupCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		for _, key := range uploaded {
			if err := s.objects.Delete(cleanupCtx, key); err != nil {
				log.Printf("remove orphaned object %s: %v", key, err)
			}
		}
	}()

	for _, file := range input.Files {
		f, err := file.Open()
		if err != nil {
			return Result{}, fmt.Errorf("%w: invalid attachment", ErrInvalid)
		}

		var header [512]byte
		n, readErr := io.ReadFull(f, header[:])
		if readErr != nil && readErr != io.EOF && readErr != io.ErrUnexpectedEOF {
			f.Close()
			return Result{}, fmt.Errorf("%w: invalid attachment", ErrInvalid)
		}

		contentType := http.DetectContentType(header[:n])
		if !strings.HasPrefix(contentType, "image/") {
			f.Close()
			return Result{}, fmt.Errorf("%w: attachments must be images", ErrInvalid)
		}

		if _, err := f.Seek(0, io.SeekStart); err != nil {
			f.Close()
			return Result{}, fmt.Errorf("%w: invalid attachment", ErrInvalid)
		}

		id := uuid.New()
		key := fmt.Sprintf("%s/%s/%s", chatID, result.MessageID, id)
		uploaded = append(uploaded, key)

		err = s.objects.Put(ctx, key, f, file.Size, contentType)
		f.Close()
		if err != nil {
			return Result{}, fmt.Errorf("upload attachment: %w", err)
		}

		result.Attachments = append(result.Attachments, Attachment{
			ID:          id,
			Filename:    file.Filename,
			Bucket:      s.bucket,
			Key:         key,
			ContentType: contentType,
			Size:        file.Size,
		})
	}

	task := models.AgentRequest{
		MessageID:   result.MessageID,
		ChatID:      result.ChatID,
		UserID:      userID,
		Message:     message,
		Attachments: make([]models.AgentAttachment, 0, len(result.Attachments)),
	}
	for _, attachment := range result.Attachments {
		task.Attachments = append(task.Attachments, models.AgentAttachment{
			ID: attachment.ID, Bucket: attachment.Bucket, ObjectKey: attachment.Key,
			Filename: attachment.Filename, ContentType: attachment.ContentType,
			SizeBytes: attachment.Size,
		})
	}

	blocks := make([]models.Block, 0, 2)
	if message != "" {
		blocks = append(blocks, models.Block{Text: &models.TextBlock{Message: message}})
	}
	if len(task.Attachments) > 0 {
		blocks = append(blocks, models.Block{
			Attachments: &models.AttachmentsBlock{Attachments: task.Attachments},
		})
	}

	err = s.repo.Save(ctx, Record{
		UserID: userID, NewChat: newChat, Message: message,
		Result: result, Task: task, Blocks: blocks,
	})
	if err != nil {
		if errors.Is(err, ErrCommitUnknown) {
			keep = true
		}
		return Result{}, err
	}

	keep = true
	return result, nil
}
