package request

import (
	"bytes"
	"context"
	"errors"
	"io"
	"testing"
)

type fakeRepo struct {
	err    error
	record Record
}

func (r *fakeRepo) Save(_ context.Context, record Record) error { r.record = record; return r.err }

type fakeObjects struct{ uploaded, deleted []string }

func (o *fakeObjects) Put(_ context.Context, key string, _ io.Reader, _ int64, _ string) error {
	o.uploaded = append(o.uploaded, key)
	return nil
}
func (o *fakeObjects) Delete(_ context.Context, key string) error {
	o.deleted = append(o.deleted, key)
	return nil
}

type readSeekCloser struct{ *bytes.Reader }

func (readSeekCloser) Close() error { return nil }
func TestCreateCleanup(t *testing.T) {
	for _, tc := range []struct {
		name    string
		err     error
		deleted int
	}{{"success", nil, 0}, {"save failure", errors.New("failed"), 1}, {"uncertain commit", ErrCommitUnknown, 0}} {
		t.Run(tc.name, func(t *testing.T) {
			repo := &fakeRepo{err: tc.err}
			objects := &fakeObjects{}
			s := New(repo, objects, "images")
			data := []byte("\x89PNG\r\n\x1a\nimage")
			result, err := s.Create(context.Background(), Input{UserID: "11111111-1111-4111-8111-111111111111", Files: []File{{Filename: "a.png", Size: int64(len(data)), Open: func() (io.ReadSeekCloser, error) { return readSeekCloser{bytes.NewReader(data)}, nil }}}})
			if (err != nil) != (tc.err != nil) {
				t.Fatalf("unexpected error: %v", err)
			}
			if len(objects.uploaded) != 1 || len(objects.deleted) != tc.deleted {
				t.Fatalf("uploaded %v, deleted %v", objects.uploaded, objects.deleted)
			}
			if tc.err == nil && (len(result.Attachments) != 1 || repo.record.Result.MessageID != result.MessageID) {
				t.Fatal("message or attachment was not saved")
			}
		})
	}
}
