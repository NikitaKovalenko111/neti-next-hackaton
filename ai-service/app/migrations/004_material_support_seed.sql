INSERT INTO support_sources (id, title, url, kind, published_at, checked_at, is_normative_source)
SELECT s.id, s.title, s.url, s.kind, s.published_at, s.checked_at, s.is_normative_source
FROM rag_seed
CROSS JOIN LATERAL jsonb_to_recordset(data->'sources') AS s(
    id text, title text, url text, kind text, published_at date, checked_at date,
    is_normative_source boolean
);

INSERT INTO support_programs (
    id, name, order_number, effective_from, source_id, deadline_day_of_month,
    eligibility, submission, review_process, restrictions, amount_basis, metadata
)
SELECT p->>'id', p->>'name', p#>>'{normative_order,number}',
       (p#>>'{normative_order,effective_from}')::date, p->>'source_id',
       (p#>>'{submission,deadline_day_of_month}')::smallint,
       p->'eligibility', p->'submission', p->'review_process',
       ARRAY(SELECT jsonb_array_elements_text(p->'restrictions')), p->'amount_basis',
       jsonb_build_object('dataset', data->'metadata', 'policy', p)
FROM rag_seed CROSS JOIN LATERAL (SELECT data->'policy') AS policy(p);

INSERT INTO support_program_branches (program_id, branch_id)
SELECT data#>>'{policy,id}', branch_id
FROM rag_seed CROSS JOIN LATERAL jsonb_array_elements_text(data#>'{policy,branches_scope}') AS branch_id;

INSERT INTO support_grounds (
    id, program_id, number_in_regulation, title, description, frequency, amount_type,
    max_multiplier, amount_rub, decision_by_commission, depends_on_available_funds,
    deadline_period, deadline_months, deadline_event, important_notes, restrictions,
    source_id, source_pdf_pages
)
SELECT g.id, data#>>'{policy,id}', g.number_in_regulation, g.title, g.description, g.frequency,
       g.amount->>'type', (g.amount->>'max_multiplier')::numeric, (g.amount->>'amount_rub')::numeric,
       g.decision_by_commission, g.depends_on_available_funds,
       g.application_deadline_special->>'period',
       substring(g.application_deadline_special->>'period' FROM '^([0-9]+)_months$')::smallint,
       g.application_deadline_special->>'from', g.important_notes, g.restrictions,
       g.source_id, g.source_pdf_pages
FROM rag_seed
CROSS JOIN LATERAL jsonb_to_recordset(data->'grounds') AS g(
    id text, number_in_regulation smallint, title text, description text, frequency text,
    amount jsonb, decision_by_commission boolean, depends_on_available_funds boolean,
    application_deadline_special jsonb, important_notes text[], restrictions text[],
    source_id text, source_pdf_pages smallint[]
);

INSERT INTO support_required_documents (ground_id, position, description)
SELECT g.value->>'id', document.position, document.description
FROM rag_seed
CROSS JOIN LATERAL jsonb_array_elements(data->'grounds') AS g(value)
CROSS JOIN LATERAL jsonb_array_elements_text(g.value->'required_documents')
    WITH ORDINALITY AS document(description, position);

INSERT INTO support_channels (id, program_id, channel, places, known_address, online_submission, deadline, notes)
SELECT c.id, c.program_id, c.channel, c.places, c.known_address, c.online_submission,
       c.deadline, coalesce(c.notes, '{}')
FROM rag_seed
CROSS JOIN LATERAL jsonb_to_recordset(data->'submission_channels') AS c(
    id text, program_id text, channel text, places text[], known_address text,
    online_submission boolean, deadline text, notes text[]
);

INSERT INTO support_channel_branches (channel_id, branch_id)
SELECT c.value->>'id', branch_id
FROM rag_seed
CROSS JOIN LATERAL jsonb_array_elements(data->'submission_channels') AS c(value)
CROSS JOIN LATERAL jsonb_array_elements_text(c.value->'scope') AS branch_id;

INSERT INTO support_channel_sources (channel_id, source_id)
SELECT c.value->>'id', source_id
FROM rag_seed
CROSS JOIN LATERAL jsonb_array_elements(data->'submission_channels') AS c(value)
CROSS JOIN LATERAL jsonb_array_elements_text(c.value->'source_ids') AS source_id;
