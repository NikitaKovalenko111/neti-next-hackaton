ALTER TABLE messages ADD COLUMN turn_number BIGINT;

WITH ordered AS (
    SELECT id, row_number() OVER (PARTITION BY chat_id ORDER BY created_at, id) AS number
    FROM messages
    WHERE role = 'user'
)
UPDATE messages SET turn_number = ordered.number
FROM ordered WHERE messages.id = ordered.id;

CREATE UNIQUE INDEX messages_chat_turn_idx ON messages (chat_id, turn_number)
    WHERE role = 'user';

ALTER TABLE chats
    ADD COLUMN history_summary TEXT NOT NULL DEFAULT '',
    ADD COLUMN history_summary_through BIGINT NOT NULL DEFAULT 0;
