CREATE TABLE campus_dataset (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    metadata jsonb NOT NULL
);

CREATE TABLE campus_sources (
    id text PRIMARY KEY,
    url text NOT NULL,
    authority text NOT NULL,
    checked_on date NOT NULL
);

CREATE TABLE campus_branches (
    id text PRIMARY KEY,
    kind text NOT NULL,
    city text NOT NULL,
    name text NOT NULL,
    main_address text NOT NULL,
    payload jsonb NOT NULL
);

CREATE TABLE campus_places (
    id text PRIMARY KEY,
    branch_id text NOT NULL REFERENCES campus_branches(id),
    kind text NOT NULL CHECK (kind IN ('building', 'dormitory')),
    name text NOT NULL,
    city text NOT NULL,
    address text NOT NULL,
    full_address text NOT NULL,
    address_conflict jsonb,
    payload jsonb NOT NULL,
    UNIQUE (branch_id, id)
);
CREATE INDEX campus_places_branch_kind_idx ON campus_places(branch_id, kind);

CREATE TABLE campus_housing (
    branch_id text PRIMARY KEY REFERENCES campus_branches(id),
    owned_dormitories_reported integer,
    individual_records integer NOT NULL,
    status text NOT NULL,
    payload jsonb NOT NULL
);

CREATE TABLE campus_photos (
    id text PRIMARY KEY,
    branch_id text NOT NULL REFERENCES campus_branches(id),
    object_id text,
    url text NOT NULL,
    caption text NOT NULL,
    attribution_status text NOT NULL,
    payload jsonb NOT NULL,
    FOREIGN KEY (branch_id, object_id) REFERENCES campus_places(branch_id, id)
);
CREATE INDEX campus_photos_object_idx ON campus_photos(object_id) WHERE object_id IS NOT NULL;

CREATE VIEW campus_documents AS
SELECT 'branch' AS kind, id, id AS branch_id, name AS title,
       concat_ws(E'\n', name, payload->>'abbreviation', city, 'Адрес: ' || main_address,
                 payload->>'history') AS content,
       payload->'sources' AS source_ids
FROM campus_branches
UNION ALL
SELECT kind, id, branch_id, name,
       concat_ws(E'\n', CASE WHEN kind = 'dormitory' THEN 'Общежитие' ELSE 'Корпус' END,
                 name, full_address, 'Телефон: ' || (payload->>'phone'),
                 'Вместимость по источнику: ' || (payload->>'capacity_as_published'),
                 'Этажей: ' || (payload->>'floors'), 'Год постройки: ' || (payload->>'construction_year'),
                 payload->>'capacity_note', payload->>'address_basis', payload->>'note',
                 'Адрес требует проверки: ' || address_conflict::text),
       payload->'source_ids'
FROM campus_places
UNION ALL
SELECT 'housing', h.branch_id, h.branch_id, 'Общежития — ' || b.city,
       concat_ws(E'\n', 'Общежития — ' || b.city, b.name,
                 'Собственных общежитий по источнику: ' || h.owned_dormitories_reported,
                 'Общежитий с отдельной карточкой: ' || h.individual_records,
                 h.payload->>'note'),
       h.payload->'source_ids'
FROM campus_housing h JOIN campus_branches b ON b.id = h.branch_id;

CREATE TABLE campus_embeddings (
    kind text NOT NULL,
    record_id text NOT NULL,
    model text NOT NULL,
    content text NOT NULL,
    embedding rag.vector(1024) NOT NULL,
    PRIMARY KEY (kind, record_id, model)
);
