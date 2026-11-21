INSERT INTO campus_dataset (metadata)
SELECT data->'metadata' FROM rag_seed;

INSERT INTO campus_sources (id, url, authority, checked_on)
SELECT source.id, source.url, source.authority, source.checked_on
FROM rag_seed
CROSS JOIN LATERAL jsonb_to_recordset(data->'sources')
    AS source(id text, url text, authority text, checked_on date);

INSERT INTO campus_branches (id, kind, city, name, main_address, payload)
SELECT item->>'id', item->>'kind', item->>'city', item->>'name', item->>'main_address', item
FROM rag_seed CROSS JOIN LATERAL jsonb_array_elements(data->'branches') AS item;

INSERT INTO campus_places (id, branch_id, kind, name, city, address, full_address, address_conflict, payload)
SELECT item->>'id', item->>'branch_id', groups.kind, item->>'name', item->>'city',
       item->>'address', item->>'full_address', item->'address_conflict', item
FROM rag_seed
CROSS JOIN LATERAL (VALUES ('building', data->'buildings'), ('dormitory', data->'dormitories'))
    AS groups(kind, entries)
CROSS JOIN LATERAL jsonb_array_elements(groups.entries) AS item;

INSERT INTO campus_housing (branch_id, owned_dormitories_reported, individual_records, status, payload)
SELECT item->>'branch_id', (item->>'owned_dormitories_reported')::integer,
       (item->>'individual_records')::integer, item->>'status', item
FROM rag_seed CROSS JOIN LATERAL jsonb_array_elements(data->'housing_inventory') AS item;

INSERT INTO campus_photos (id, branch_id, object_id, url, caption, attribution_status, payload)
SELECT item->>'id', item->>'branch_id', item->>'object_id', item->>'url',
       item->>'caption', item->>'attribution_status', item
FROM rag_seed CROSS JOIN LATERAL jsonb_array_elements(data->'photos') AS item;
