ALTER TABLE campus_photos
    ADD COLUMN minio_bucket text,
    ADD COLUMN object_key text,
    ADD COLUMN content_type text,
    ADD CONSTRAINT campus_photos_object_fields CHECK (
        num_nonnulls(minio_bucket, object_key, content_type) IN (0, 3)
    );
