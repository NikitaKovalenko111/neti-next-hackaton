package objectstorage

import (
	"context"
	"net/url"
	"testing"

	"university-agent/internal/config"

	"github.com/minio/minio-go/v7"
)

func TestPublicURLsUseExternalEndpoint(t *testing.T) {
	internal, err := minio.New("minio:9000", &minio.Options{})
	if err != nil {
		t.Fatal(err)
	}

	storage, err := NewStorage(internal, config.Config{
		MinIOBucket: "images", MinIOPublicEndpoint: "https://files.example.test:9443",
		MinIOAccessKey: "minioadmin", MinIOSecretKey: "minioadmin", MinIORegion: "us-east-1",
	})
	if err != nil {
		t.Fatal(err)
	}
	if storage.client != internal {
		t.Fatal("public URL configuration replaced the internal storage client")
	}

	link, err := storage.URL(context.Background(), "images", "agent/image.png")
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := url.Parse(link)
	if err != nil {
		t.Fatal(err)
	}
	if parsed.Scheme != "https" || parsed.Host != "files.example.test:9443" || parsed.Path != "/images/agent/image.png" {
		t.Fatalf("unexpected public URL: %s", link)
	}
	if parsed.Query().Get("X-Amz-Signature") == "" || parsed.Query().Get("X-Amz-Expires") != "900" {
		t.Fatalf("missing signature or incorrect expiration: %s", link)
	}
}

func TestInvalidPublicEndpointIsRejected(t *testing.T) {
	for _, endpoint := range []string{"localhost:9000", "ftp://files.test", "https://files.test/path", "https://user:pass@files.test"} {
		if _, err := NewStorage(nil, config.Config{MinIOPublicEndpoint: endpoint}); err == nil {
			t.Errorf("invalid endpoint accepted: %s", endpoint)
		}
	}
}

func TestEmptyPublicEndpointKeepsOriginalSigner(t *testing.T) {
	internal, err := minio.New("minio:9000", &minio.Options{})
	if err != nil {
		t.Fatal(err)
	}
	storage, err := NewStorage(internal, config.Config{})
	if err != nil || storage.signer != internal {
		t.Fatalf("original signing behavior was not preserved: %v", err)
	}
}
