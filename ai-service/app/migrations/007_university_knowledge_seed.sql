INSERT INTO knowledge_records (
    id, category, title, branch_id, reference_code, year, search_text, sources, data
)
SELECT r.id, r.category, r.title, r.branch_id, r.reference_code, r.year, r.search_text, r.sources, r.data
FROM rag_seed
CROSS JOIN LATERAL jsonb_to_recordset(data->'records') AS r(
    id text, category text, title text, branch_id text, reference_code text, year integer,
    search_text text, sources text[], data jsonb
);

INSERT INTO knowledge_notes (id, category, title, summary, sources, dates)
SELECT id, category, title, summary, sources, coalesce(dates, '[]'::jsonb)
FROM rag_seed
CROSS JOIN LATERAL jsonb_to_recordset(data->'notes') AS n(
    id text, category text, title text, summary text, sources text[], dates jsonb
);
