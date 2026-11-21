CREATE TABLE users (
    id UUID PRIMARY KEY,
    login TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE chats ADD COLUMN guest_expires_at TIMESTAMPTZ DEFAULT (now() + interval '24 hours');
CREATE INDEX chats_account_history_idx ON chats (user_id, created_at DESC, id)
    WHERE guest_expires_at IS NULL;
