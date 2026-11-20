package blocks

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"university-agent/internal/models"

	"github.com/google/uuid"
)

type fakeObjects struct {
	exists bool
	err    error
}

func (s fakeObjects) Stat(context.Context, string, string) (int64, bool, error) {
	return 42, s.exists, s.err
}

func (s fakeObjects) URL(context.Context, string, string) (string, error) {
	return "https://minio.test/signed-image", s.err
}

func validAttachment() models.AgentAttachment {
	return models.AgentAttachment{
		ID: uuid.New(), Bucket: "images", ObjectKey: "agent/image.png",
		Filename: "image.png", ContentType: "image/png",
	}
}

func TestValidateBlocks(t *testing.T) {
	for _, tc := range []struct {
		name    string
		payload string
	}{
		{"no blocks", `[]`},
		{"blank text", `[{"type":"text","message":"  "}]`},
		{"unsupported audience", `[{"type":"text","message":"Hello","audience":"staff"}]`},
		{"missing latitude", `[{"type":"map","lon":55}]`},
		{"invalid longitude", `[{"type":"map","lat":54,"lon":181}]`},
		{"no attachments", `[{"type":"attachments","attachments":[]}]`},
		{"missing attachment fields", `[{"type":"attachments","attachments":[{}]}]`},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var blocks []models.Block
			if err := json.Unmarshal([]byte(tc.payload), &blocks); err != nil {
				t.Fatal(err)
			}
			if err := New(fakeObjects{exists: true}, "images").Validate(context.Background(), blocks); !errors.Is(err, ErrInvalid) {
				t.Fatalf("expected invalid blocks, got %v", err)
			}
		})
	}

	attachment := validAttachment()
	invalidMIME := attachment
	invalidMIME.ContentType = "image"
	wrongBucket := attachment
	wrongBucket.Bucket = "other"
	for _, tc := range []struct {
		name        string
		attachments []models.AgentAttachment
		storage     fakeObjects
		invalid     bool
	}{
		{"invalid MIME type", []models.AgentAttachment{invalidMIME}, fakeObjects{exists: true}, true},
		{"wrong bucket", []models.AgentAttachment{wrongBucket}, fakeObjects{exists: true}, true},
		{"missing object", []models.AgentAttachment{attachment}, fakeObjects{}, true},
		{"duplicate attachment", []models.AgentAttachment{attachment, attachment}, fakeObjects{exists: true}, true},
		{"storage unavailable", []models.AgentAttachment{attachment}, fakeObjects{err: errors.New("unavailable")}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			blocks := []models.Block{{Attachments: &models.AttachmentsBlock{Attachments: tc.attachments}}}
			err := New(tc.storage, "images").Validate(context.Background(), blocks)
			if err == nil || errors.Is(err, ErrInvalid) != tc.invalid {
				t.Fatalf("unexpected validation error: %v", err)
			}
		})
	}
}

func TestAttachmentURLsAreNotPersisted(t *testing.T) {
	attachment := validAttachment()
	attachment.URL = "https://untrusted.example/image"
	blocks := []models.Block{
		{Text: &models.TextBlock{Message: "Before"}},
		{Attachments: &models.AttachmentsBlock{Attachments: []models.AgentAttachment{attachment}}},
		{Text: &models.TextBlock{Message: "After"}},
	}
	service := New(fakeObjects{exists: true}, "images")
	if err := service.Validate(context.Background(), blocks); err != nil {
		t.Fatal(err)
	}

	canonical := blocks[1].Attachments.Attachments[0]
	if canonical.URL != "" || canonical.SizeBytes != 42 {
		t.Fatalf("invalid canonical metadata: %+v", canonical)
	}

	result, err := service.WithURLs(context.Background(), blocks)
	if err != nil {
		t.Fatal(err)
	}
	if result[0].Text.Message != "Before" || result[2].Text.Message != "After" || result[1].Attachments.Attachments[0].URL == "" {
		t.Fatal("block order or signed URL was lost")
	}
	if blocks[1].Attachments.Attachments[0].URL != "" {
		t.Fatal("presentation mutated canonical blocks")
	}
}
