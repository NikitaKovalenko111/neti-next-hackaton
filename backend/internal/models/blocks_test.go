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
		{"legacy map", `{"type":"map","lat":54.720714,"lon":55.933422,"title":"Campus"}`, true},
		{"audience", `{"type":"text","message":"Hello","audience":"student"}`, true},
		{"map", `{"type":"map","points":[{"title":"Campus","latitude":0,"longitude":0}]}`, true},
		{"missing longitude", `{"type":"map","points":[{"title":"Campus","latitude":54}]}`, false},
		{"null latitude", `{"type":"map","points":[{"title":"Campus","latitude":null,"longitude":55}]}`, false},
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
