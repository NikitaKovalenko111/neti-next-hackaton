ALTER TABLE messages
    ADD COLUMN role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'assistant')),
    ADD COLUMN request_message_id UUID UNIQUE REFERENCES messages(id);

CREATE TABLE agent_request_outbox (
    message_id UUID PRIMARY KEY REFERENCES messages(id),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
