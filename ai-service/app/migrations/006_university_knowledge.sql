CREATE TABLE knowledge_records (
    id text PRIMARY KEY,
    category text NOT NULL,
    title text NOT NULL,
    branch_id text,
    reference_code text,
    year integer,
    search_text text NOT NULL,
    sources text[] NOT NULL CHECK (cardinality(sources) > 0),
    data jsonb NOT NULL,
    terms tsvector GENERATED ALWAYS AS (
        to_tsvector('russian', title || ' ' || search_text)
    ) STORED
);

CREATE INDEX knowledge_records_terms_idx ON knowledge_records USING gin (terms);
CREATE INDEX knowledge_records_category_code_idx
    ON knowledge_records (category, reference_code, branch_id);

CREATE TABLE knowledge_notes (
    id text PRIMARY KEY,
    category text NOT NULL,
    title text NOT NULL,
    summary text NOT NULL,
    sources text[] NOT NULL CHECK (cardinality(sources) > 0),
    dates jsonb NOT NULL DEFAULT '[]'
);

CREATE TABLE knowledge_embeddings (
    note_id text REFERENCES knowledge_notes(id) ON DELETE CASCADE,
    model text NOT NULL,
    content text NOT NULL,
    embedding rag.vector(1024) NOT NULL,
    PRIMARY KEY (note_id, model)
);
