package models

import (
	"bytes"
	"encoding/json"
	"fmt"
)

type TextBlock struct {
	Message  string   `json:"message"`
	Audience string   `json:"audience,omitempty"`
	Source   []string `json:"source,omitempty"`
}

type AttachmentsBlock struct {
	Attachments []AgentAttachment `json:"attachments"`
}

type MapPoint struct {
	Title     string  `json:"title"`
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
	Address   string  `json:"address,omitempty"`
}

func (p *MapPoint) UnmarshalJSON(data []byte) error {
	var value struct {
		Title     string   `json:"title"`
		Latitude  *float64 `json:"latitude"`
		Longitude *float64 `json:"longitude"`
		Address   string   `json:"address,omitempty"`
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&value); err != nil {
		return err
	}
	if value.Latitude == nil || value.Longitude == nil {
		return fmt.Errorf("map point requires latitude and longitude")
	}
	*p = MapPoint{Title: value.Title, Latitude: *value.Latitude, Longitude: *value.Longitude, Address: value.Address}
	return nil
}

type MapBlock struct {
	Points []MapPoint `json:"points,omitempty"`
	// Flat coordinates are present in previously stored chat history.
	Lat     *float64 `json:"lat,omitempty"`
	Lon     *float64 `json:"lon,omitempty"`
	Title   string   `json:"title,omitempty"`
	Address string   `json:"address,omitempty"`
}

// Block contains exactly one supported block payload.
type Block struct {
	Text        *TextBlock
	Attachments *AttachmentsBlock
	Map         *MapBlock
}

func (b Block) MarshalJSON() ([]byte, error) {
	switch {
	case b.Text != nil && b.Attachments == nil && b.Map == nil:
		return json.Marshal(struct {
			Type string `json:"type"`
			*TextBlock
		}{Type: "text", TextBlock: b.Text})

	case b.Attachments != nil && b.Text == nil && b.Map == nil:
		return json.Marshal(struct {
			Type string `json:"type"`
			*AttachmentsBlock
		}{Type: "attachments", AttachmentsBlock: b.Attachments})

	case b.Map != nil && b.Text == nil && b.Attachments == nil:
		return json.Marshal(struct {
			Type string `json:"type"`
			*MapBlock
		}{Type: "map", MapBlock: b.Map})

	default:
		return nil, fmt.Errorf("block must contain exactly one payload")
	}
}

func (b *Block) UnmarshalJSON(data []byte) error {
	var header struct {
		Type string `json:"type"`
	}
	if err := json.Unmarshal(data, &header); err != nil {
		return err
	}

	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()

	switch header.Type {
	case "text":
		var value struct {
			Type string `json:"type"`
			TextBlock
		}
		if err := decoder.Decode(&value); err != nil {
			return err
		}
		*b = Block{Text: &value.TextBlock}

	case "attachments":
		var value struct {
			Type string `json:"type"`
			AttachmentsBlock
		}
		if err := decoder.Decode(&value); err != nil {
			return err
		}
		*b = Block{Attachments: &value.AttachmentsBlock}

	case "map":
		var value struct {
			Type string `json:"type"`
			MapBlock
		}
		if err := decoder.Decode(&value); err != nil {
			return err
		}
		*b = Block{Map: &value.MapBlock}

	default:
		return fmt.Errorf("unsupported block type %q", header.Type)
	}

	return nil
}
