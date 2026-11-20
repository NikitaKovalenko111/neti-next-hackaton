package objectstorage

import (
	"context"
	"fmt"
	"io"
	"net/url"
	"time"

	"university-agent/internal/config"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type Storage struct {
	client *minio.Client
	signer *minio.Client
	bucket string
}

func Wrap(client *minio.Client, bucket string) *Storage {
	return &Storage{client: client, signer: client, bucket: bucket}
}

func NewStorage(client *minio.Client, cfg config.Config) (*Storage, error) {
	storage := Wrap(client, cfg.MinIOBucket)
	if cfg.MinIOPublicEndpoint == "" {
		return storage, nil
	}

	endpoint, err := url.Parse(cfg.MinIOPublicEndpoint)
	if err != nil || endpoint.Host == "" ||
		(endpoint.Scheme != "http" && endpoint.Scheme != "https") ||
		(endpoint.Path != "" && endpoint.Path != "/") || endpoint.User != nil ||
		endpoint.RawQuery != "" || endpoint.Fragment != "" {
		return nil, fmt.Errorf("MINIO_PUBLIC_ENDPOINT must be an http(s) URL without a path, credentials or query")
	}

	region := cfg.MinIORegion
	if region == "" {
		region = "us-east-1"
	}
	storage.signer, err = minio.New(endpoint.Host, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.MinIOAccessKey, cfg.MinIOSecretKey, ""),
		Secure: endpoint.Scheme == "https",
		Region: region,
	})
	if err != nil {
		return nil, fmt.Errorf("create public MinIO signer: %w", err)
	}

	return storage, nil
}

func (s *Storage) Put(ctx context.Context, key string, reader io.Reader, size int64, contentType string) error {
	_, err := s.client.PutObject(ctx, s.bucket, key, reader, size, minio.PutObjectOptions{ContentType: contentType})
	return err
}

func (s *Storage) Delete(ctx context.Context, key string) error {
	return s.client.RemoveObject(ctx, s.bucket, key, minio.RemoveObjectOptions{})
}

func (s *Storage) Stat(ctx context.Context, bucket, key string) (int64, bool, error) {
	info, err := s.client.StatObject(ctx, bucket, key, minio.StatObjectOptions{})
	if err != nil {
		code := minio.ToErrorResponse(err).Code
		if code == "NoSuchKey" || code == "NoSuchObject" || code == "NoSuchBucket" {
			return 0, false, nil
		}
		return 0, false, err
	}

	return info.Size, true, nil
}

func (s *Storage) URL(ctx context.Context, bucket, key string) (string, error) {
	url, err := s.signer.PresignedGetObject(ctx, bucket, key, 15*time.Minute, nil)
	if err != nil {
		return "", err
	}

	return url.String(), nil
}

func New(ctx context.Context, cfg config.Config) (*minio.Client, error) {
	client, err := minio.New(cfg.MinIOEndpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.MinIOAccessKey, cfg.MinIOSecretKey, ""),
		Secure: cfg.MinIOSecure,
		Region: cfg.MinIORegion,
	})
	if err != nil {
		return nil, err
	}
	exists, err := client.BucketExists(ctx, cfg.MinIOBucket)
	if err != nil {
		return nil, fmt.Errorf("check bucket: %w", err)
	}
	if !exists {
		if err := client.MakeBucket(ctx, cfg.MinIOBucket, minio.MakeBucketOptions{}); err != nil {
			return nil, fmt.Errorf("create bucket: %w", err)
		}
	}
	return client, nil
}
