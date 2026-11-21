INSERT INTO knowledge_records (id, category, title, branch_id, reference_code, year, search_text, sources, data)
SELECT r.id, r.category, r.title, r.branch_id, r.reference_code, r.year, r.search_text, r.sources, r.data
FROM rag_seed
CROSS JOIN LATERAL jsonb_to_recordset(data->'records') AS r(
    id text, category text, title text, branch_id text, reference_code text, year integer,
    search_text text, sources text[], data jsonb
)
ON CONFLICT (id) DO UPDATE SET
    title = excluded.title, branch_id = excluded.branch_id, reference_code = excluded.reference_code,
    year = excluded.year, search_text = excluded.search_text, sources = excluded.sources,
    data = excluded.data;

INSERT INTO knowledge_notes (id, category, title, summary, sources, dates)
SELECT n.id, n.category, n.title, n.summary, n.sources, n.dates
FROM rag_seed
CROSS JOIN LATERAL jsonb_to_recordset(data->'notes') AS n(
    id text, category text, title text, summary text, sources text[], dates jsonb
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO campus_sources (id, url, authority, checked_on)
SELECT p.source_id, p.source_url, 'official', DATE '2026-11-21'
FROM rag_seed
CROSS JOIN LATERAL jsonb_to_recordset(data->'photos') AS p(source_id text, source_url text)
ON CONFLICT (id) DO NOTHING;

INSERT INTO campus_photos (id, branch_id, object_id, url, caption, attribution_status, payload)
SELECT p->>'id', p->>'branch_id', place.id, p->>'url', p->>'caption',
       p->>'attribution_status', p || jsonb_build_object('source_ids', jsonb_build_array(p->>'source_id'))
FROM rag_seed
CROSS JOIN LATERAL jsonb_array_elements(data->'photos') AS p
LEFT JOIN campus_places place ON place.id = p->>'object_id' AND place.branch_id = p->>'branch_id'
WHERE (p->>'object_id' IS NULL OR place.id IS NOT NULL)
  AND NOT EXISTS (SELECT 1 FROM campus_photos existing WHERE existing.url = p->>'url')
ON CONFLICT (id) DO NOTHING;
