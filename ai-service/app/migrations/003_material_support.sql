CREATE TABLE support_sources (
    id text PRIMARY KEY,
    title text NOT NULL,
    url text NOT NULL,
    kind text NOT NULL,
    published_at date,
    checked_at date NOT NULL,
    is_normative_source boolean NOT NULL
);

CREATE TABLE support_programs (
    id text PRIMARY KEY,
    name text NOT NULL,
    order_number text NOT NULL,
    effective_from date NOT NULL,
    source_id text NOT NULL REFERENCES support_sources(id),
    deadline_day_of_month smallint NOT NULL CHECK (deadline_day_of_month BETWEEN 1 AND 31),
    eligibility jsonb NOT NULL,
    submission jsonb NOT NULL,
    review_process jsonb NOT NULL,
    restrictions text[] NOT NULL,
    amount_basis jsonb NOT NULL,
    metadata jsonb NOT NULL
);

CREATE TABLE support_program_branches (
    program_id text REFERENCES support_programs(id),
    branch_id text REFERENCES campus_branches(id),
    PRIMARY KEY (program_id, branch_id)
);

CREATE TABLE support_grounds (
    id text PRIMARY KEY,
    program_id text NOT NULL REFERENCES support_programs(id),
    number_in_regulation smallint NOT NULL,
    title text NOT NULL,
    description text NOT NULL,
    frequency text NOT NULL,
    amount_type text NOT NULL,
    max_multiplier numeric,
    amount_rub numeric,
    decision_by_commission boolean NOT NULL,
    depends_on_available_funds boolean NOT NULL,
    deadline_period text,
    deadline_months smallint CHECK (deadline_months > 0),
    deadline_event text,
    important_notes text[] NOT NULL,
    restrictions text[] NOT NULL,
    source_id text NOT NULL REFERENCES support_sources(id),
    source_pdf_pages smallint[] NOT NULL,
    UNIQUE (program_id, number_in_regulation),
    CHECK ((deadline_period IS NULL) = (deadline_event IS NULL)),
    CHECK (
        (amount_type = 'scholarship_multiplier_up_to' AND max_multiplier > 0
            AND max_multiplier IS NOT NULL AND amount_rub IS NULL)
        OR (amount_type = 'fixed_rub' AND amount_rub > 0
            AND amount_rub IS NOT NULL AND max_multiplier IS NULL)
        OR (amount_type = 'individual_decision' AND max_multiplier IS NULL AND amount_rub IS NULL)
    )
);

CREATE TABLE support_required_documents (
    ground_id text REFERENCES support_grounds(id),
    position smallint,
    description text NOT NULL,
    PRIMARY KEY (ground_id, position)
);

CREATE TABLE support_channels (
    id text PRIMARY KEY,
    program_id text REFERENCES support_programs(id),
    channel text NOT NULL,
    places text[] NOT NULL,
    known_address text,
    online_submission boolean,
    deadline text,
    notes text[] NOT NULL
);

CREATE TABLE support_channel_branches (
    channel_id text REFERENCES support_channels(id),
    branch_id text REFERENCES campus_branches(id),
    PRIMARY KEY (channel_id, branch_id)
);

CREATE TABLE support_channel_sources (
    channel_id text REFERENCES support_channels(id),
    source_id text REFERENCES support_sources(id),
    PRIMARY KEY (channel_id, source_id)
);

CREATE VIEW support_ground_details AS
SELECT g.*, p.deadline_day_of_month, s.url AS source_url,
       ARRAY(SELECT d.description FROM support_required_documents d
             WHERE d.ground_id = g.id ORDER BY d.position) AS required_documents
FROM support_grounds g
JOIN support_programs p ON p.id = g.program_id
JOIN support_sources s ON s.id = g.source_id;

CREATE VIEW support_ground_texts AS
SELECT id, concat_ws(E'\n', title, NULLIF(description, title),
                     NULLIF(array_to_string(important_notes, E'\n'), '')) AS content
FROM support_grounds;

CREATE TABLE support_embeddings (
    ground_id text REFERENCES support_grounds(id) ON DELETE CASCADE,
    model text NOT NULL,
    content text NOT NULL,
    embedding rag.vector(1024) NOT NULL,
    PRIMARY KEY (ground_id, model)
);
