CREATE TABLE chats (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE messages (
    id UUID PRIMARY KEY,
    chat_id UUID NOT NULL REFERENCES chats(id),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX messages_chat_id_idx ON messages (chat_id, created_at);

CREATE TABLE attachments (
    attachment_id UUID PRIMARY KEY,
    message_id UUID NOT NULL REFERENCES messages(id),
    bucket TEXT NOT NULL,
    object_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    UNIQUE (bucket, object_key)
);
CREATE INDEX attachments_message_id_idx ON attachments (message_id);
