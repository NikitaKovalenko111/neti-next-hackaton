ALTER TABLE messages
    ADD COLUMN blocks JSONB NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(blocks) = 'array');

-- Each message owns its attachment metadata, but may reference a shared object.
ALTER TABLE attachments DROP CONSTRAINT attachments_bucket_object_key_key;

-- Preserve existing text and attachment metadata in their original message.
UPDATE messages m
SET blocks =
    CASE WHEN m.content <> '' THEN
        jsonb_build_array(jsonb_build_object('type', 'text', 'message', m.content))
    ELSE '[]'::jsonb END
    || COALESCE((
        SELECT jsonb_build_array(jsonb_build_object(
            'type', 'attachments',
            'attachments', jsonb_agg(jsonb_build_object(
                'attachment_id', a.attachment_id,
                'bucket', a.bucket,
                'object_key', a.object_key,
                'filename', a.filename,
                'content_type', a.content_type,
                'size_bytes', a.size_bytes
            ) ORDER BY a.attachment_id)
        ))
        FROM attachments a
        WHERE a.message_id = m.id
        HAVING count(*) > 0
    ), '[]'::jsonb);
