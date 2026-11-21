package blocks

import (
	"context"
	"errors"
	"fmt"
	"math"
	"mime"
	"strings"

	"university-agent/internal/models"

	"github.com/google/uuid"
)

var ErrInvalid = errors.New("invalid message blocks")

type ObjectStorage interface {
	Stat(context.Context, string, string) (int64, bool, error)
	URL(context.Context, string, string) (string, error)
}

type Service struct {
	objects ObjectStorage
	bucket  string
}

func New(objects ObjectStorage, bucket string) *Service {
	return &Service{objects: objects, bucket: bucket}
}

// Validate checks the canonical payload and fills attachment sizes from MinIO.
// Signed URLs are generated only for delivery and never persisted.
func (s *Service) Validate(ctx context.Context, blocks []models.Block) error {
	if len(blocks) == 0 {
		return fmt.Errorf("%w: at least one block is required", ErrInvalid)
	}

	ids := make(map[uuid.UUID]bool)
	keys := make(map[string]bool)

	for _, block := range blocks {
		switch {
		case block.Text != nil && block.Attachments == nil && block.Map == nil:
			if strings.TrimSpace(block.Text.Message) == "" {
				return fmt.Errorf("%w: text message is required", ErrInvalid)
			}
			switch block.Text.Audience {
			case "", "unknown", "applicant", "student":
			default:
				return fmt.Errorf("%w: unsupported audience", ErrInvalid)
			}

		case block.Attachments != nil && block.Text == nil && block.Map == nil:
			if len(block.Attachments.Attachments) == 0 {
				return fmt.Errorf("%w: attachments must not be empty", ErrInvalid)
			}

			for index := range block.Attachments.Attachments {
				attachment := &block.Attachments.Attachments[index]
				if attachment.ID == uuid.Nil || attachment.Bucket != s.bucket ||
					strings.TrimSpace(attachment.ObjectKey) == "" || strings.TrimSpace(attachment.Filename) == "" {
					return fmt.Errorf("%w: attachment ID, bucket, object_key and filename are required", ErrInvalid)
				}
				mediaType, _, err := mime.ParseMediaType(attachment.ContentType)
				if err != nil || !strings.Contains(mediaType, "/") {
					return fmt.Errorf("%w: invalid attachment content_type", ErrInvalid)
				}
				if ids[attachment.ID] || keys[attachment.ObjectKey] {
					return fmt.Errorf("%w: duplicate attachment ID or object_key", ErrInvalid)
				}
				ids[attachment.ID] = true
				keys[attachment.ObjectKey] = true

				size, exists, err := s.objects.Stat(ctx, attachment.Bucket, attachment.ObjectKey)
				if err != nil {
					return fmt.Errorf("stat attachment: %w", err)
				}
				if !exists {
					return fmt.Errorf("%w: attachment does not exist in MinIO", ErrInvalid)
				}
				attachment.SizeBytes = size
				attachment.URL = ""
			}

		case block.Map != nil && block.Text == nil && block.Attachments == nil:
			if block.Map.Points == nil {
				if block.Map.Lat == nil || block.Map.Lon == nil ||
					!(math.Abs(*block.Map.Lat) <= 85 && math.Abs(*block.Map.Lon) <= 180) {
					return fmt.Errorf("%w: valid map coordinates are required", ErrInvalid)
				}
				continue
			}
			if block.Map.Lat != nil || block.Map.Lon != nil || block.Map.Title != "" || block.Map.Address != "" {
				return fmt.Errorf("%w: map block uses more than one format", ErrInvalid)
			}
			if len(block.Map.Points) == 0 {
				return fmt.Errorf("%w: map points must not be empty", ErrInvalid)
			}
			for _, point := range block.Map.Points {
				if strings.TrimSpace(point.Title) == "" {
					return fmt.Errorf("%w: map point title is required", ErrInvalid)
				}
				if !(point.Latitude >= -90 && point.Latitude <= 90 &&
					point.Longitude >= -180 && point.Longitude <= 180) {
					return fmt.Errorf("%w: map point coordinates are out of range", ErrInvalid)
				}
			}

		default:
			return fmt.Errorf("%w: exactly one supported block payload is required", ErrInvalid)
		}
	}

	return nil
}

func (s *Service) WithURLs(ctx context.Context, blocks []models.Block) ([]models.Block, error) {
	result := make([]models.Block, 0, len(blocks))

	for _, block := range blocks {
		if block.Attachments == nil {
			result = append(result, block)
			continue
		}

		attachments := make([]models.AgentAttachment, 0, len(block.Attachments.Attachments))
		for _, attachment := range block.Attachments.Attachments {
			url, err := s.objects.URL(ctx, attachment.Bucket, attachment.ObjectKey)
			if err != nil {
				return nil, fmt.Errorf("create attachment URL: %w", err)
			}
			attachment.URL = url
			attachments = append(attachments, attachment)
		}

		result = append(result, models.Block{
			Attachments: &models.AttachmentsBlock{Attachments: attachments},
		})
	}

	return result, nil
}
