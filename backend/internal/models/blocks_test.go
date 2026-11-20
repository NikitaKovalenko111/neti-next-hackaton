package models

import (
	"encoding/json"
	"testing"
)

func TestBlockDecoding(t *testing.T) {
	for _, tc := range []struct {
		name    string
		payload string
		valid   bool
	}{
		{"text", `{"type":"text","message":"Hello"}`, true},
		{"attachments", `{"type":"attachments","attachments":[]}`, true},
		{"unknown type", `{"type":"video"}`, false},
		{"missing type", `{"message":"Hello"}`, false},
		{"mixed payload", `{"type":"text","message":"Hello","attachments":[]}`, false},
		{"null block", `null`, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var block Block
			err := json.Unmarshal([]byte(tc.payload), &block)
			if (err == nil) != tc.valid {
				t.Fatalf("decode error: %v", err)
			}

			if tc.valid {
				data, err := json.Marshal(block)
				if err != nil {
					t.Fatal(err)
				}
				var roundTrip Block
				if err := json.Unmarshal(data, &roundTrip); err != nil {
					t.Fatal(err)
				}
			}
		})
	}
}
