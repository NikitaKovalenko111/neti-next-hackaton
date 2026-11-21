import json

import asyncpg


def decode_rows(rows: list[asyncpg.Record]) -> list[dict]:
    return [{**dict(row), "data": json.loads(row["data"])} for row in rows]


async def get_admission_options(
    connection: asyncpg.Connection,
    query: str | None,
    codes: list[str],
    branch_id: str | None,
    metric: str,
    form: str | None,
    funding: str | None,
    exam_scope: str | None,
    year: int | None,
    max_annual_rub: int | None,
    max_passing_score: int | None,
) -> list[dict]:
    rows = await connection.fetch(
        """
        WITH ranked AS (
            SELECT id, category, title, branch_id, reference_code, year, sources, data,
                   row_number() OVER (
                       PARTITION BY category, CASE WHEN cardinality($2::text[]) > 0
                                                   THEN reference_code END
                       ORDER BY CASE WHEN $9::bigint IS NOT NULL
                                     THEN (data->>'annual_rub')::numeric END,
                                CASE WHEN $10::bigint IS NOT NULL
                                     THEN (data->>'passing_score')::numeric END,
                                year DESC NULLS LAST, branch_id, title, id
                   ) AS position
            FROM rag.knowledge_records
            WHERE category IN ('programs', 'tuition_fees', 'passing_scores', 'entrance_tests')
              AND ($4::text = 'all' OR category = $4)
              AND ($1::text IS NULL OR terms @@ plainto_tsquery('russian', $1)
                   OR strpos(lower(title), lower($1)) > 0)
              AND (cardinality($2::text[]) = 0 OR reference_code = ANY($2::text[]))
              AND ($3::text IS NULL OR branch_id = $3)
              AND ($5::text IS NULL OR category NOT IN ('tuition_fees', 'passing_scores')
                   OR lower(data->>'form') = lower($5))
              AND ($6::text IS NULL OR category <> 'passing_scores' OR data->>'funding' = $6)
              AND ($7::text IS NULL OR category <> 'entrance_tests' OR data->>'scope' = $7)
              AND ($8::int IS NULL OR year = $8)
              AND ($9::bigint IS NULL OR category <> 'tuition_fees'
                   OR (data->>'annual_rub')::numeric <= $9)
              AND ($10::bigint IS NULL OR category <> 'passing_scores'
                   OR (data->>'passing_score')::numeric <= $10)
        )
        SELECT id, category, title, branch_id, reference_code, year, sources, data
        FROM ranked
        WHERE position <= CASE WHEN $4::text = 'all' THEN 3 ELSE 8 END
        ORDER BY position, category, reference_code
        LIMIT 32
        """,
        query,
        codes,
        branch_id,
        metric,
        form,
        funding,
        exam_scope,
        year,
        max_annual_rub,
        max_passing_score,
    )
    return decode_rows(rows)


async def find_curricula(
    connection: asyncpg.Connection,
    query: str | None,
    branch_id: str | None,
    reference_code: str | None,
    form: str | None,
    entry_year: int | None,
    subject: str | None,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, title, branch_id, reference_code, year, sources,
               (data - 'disciplines' - 'practice' - 'description') || jsonb_build_object(
                   CASE WHEN $6::text IS NULL THEN 'example_disciplines'
                        ELSE 'matching_disciplines' END, matched.disciplines,
                   'discipline_count', jsonb_array_length(coalesce(data->'disciplines', '[]')),
                   'practice_examples', jsonb_path_query_array(
                       coalesce(data->'practice', '[]'), '$[0 to 7]'
                   )
               ) AS data
        FROM rag.knowledge_records
        CROSS JOIN LATERAL (
            SELECT coalesce(jsonb_agg(x.name), '[]') AS disciplines
            FROM (
                SELECT d.name
                FROM jsonb_array_elements_text(coalesce(data->'disciplines', '[]')) AS d(name)
                WHERE $6::text IS NULL
                   OR to_tsvector('russian', d.name) @@ plainto_tsquery('russian', $6)
                   OR strpos(lower(d.name), lower($6)) > 0
                LIMIT 12
            ) x
        ) matched
        WHERE category = 'curricula'
          AND ($1::text IS NULL OR terms @@ plainto_tsquery('russian', $1)
               OR strpos(lower(title), lower($1)) > 0)
          AND ($2::text IS NULL OR branch_id = $2)
          AND ($3::text IS NULL OR reference_code = $3)
          AND ($4::text IS NULL OR lower(data->>'form') = lower($4))
          AND ($5::int IS NULL OR year = $5)
          AND ($6::text IS NULL OR jsonb_array_length(matched.disciplines) > 0)
        ORDER BY year DESC NULLS LAST, title, id
        LIMIT 8
        """,
        query,
        branch_id,
        reference_code,
        form,
        entry_year,
        subject,
    )
    return decode_rows(rows)


async def get_admission_rules(
    connection: asyncpg.Connection,
    topic: str,
    reference_code: str | None,
    year: int | None,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, title, reference_code, year, sources, data
        FROM rag.knowledge_records
        WHERE (
            category = 'admissions_rules' AND CASE $1::text
                WHEN 'olympiads' THEN data ? 'olympiad_routes'
                WHEN 'achievements' THEN data ? 'admission_year'
                WHEN 'medical_exam' THEN data ? 'legal_basis_url'
            END
            OR category = 'medical_exam' AND $1::text = 'medical_exam'
               AND ($2::text IS NULL OR reference_code = $2)
        ) AND ($3::int IS NULL OR year = $3 OR ($1::text = 'medical_exam' AND year IS NULL))
        ORDER BY (category = 'admissions_rules') DESC, reference_code, title
        """,
        topic,
        reference_code,
        year,
    )
    return decode_rows(rows)


async def find_university_contacts(
    connection: asyncpg.Connection,
    person: str | None,
    unit: str | None,
    branch_id: str | None,
    kind: str,
) -> list[dict]:
    rows = await connection.fetch(
        """
        WITH units AS (
            SELECT id, category, title, branch_id, sources, data
            FROM rag.knowledge_records
            WHERE category IN ('institutes', 'departments')
        )
        SELECT r.id, r.category, r.title, coalesce(r.branch_id, u.branch_id) AS branch_id,
               r.sources,
               (r.data - ARRAY['entries', 'department_ids', 'child_unit_ids']) ||
                   jsonb_build_object('unit_name', u.title) AS data
        FROM rag.knowledge_records r
        LEFT JOIN units u ON u.data->>'id' = coalesce(r.data->>'department_id', r.data->>'unit_id')
        WHERE r.category IN (
            'institutes', 'departments', 'staff', 'leadership', 'pedagogical_register'
        )
          AND ($4::text = 'all' OR r.category = $4)
          AND ($1::text IS NULL OR r.terms @@ plainto_tsquery('russian', $1))
          AND ($2::text IS NULL
               OR to_tsvector('russian', coalesce(u.title, '')) @@ plainto_tsquery('russian', $2)
               OR (r.category IN ('institutes', 'departments')
                   AND r.terms @@ plainto_tsquery('russian', $2)))
          AND ($3::text IS NULL OR coalesce(r.branch_id, u.branch_id) = $3)
        ORDER BY CASE WHEN $1::text IS NULL AND $2::text IS NOT NULL
                      AND r.category IN ('institutes', 'departments') THEN 0 ELSE 1 END,
                 CASE WHEN r.data->'emails' <> '[]' OR r.data->'office_emails' <> '[]'
                           OR r.data->'phones' <> '[]' THEN 0 ELSE 1 END,
                 r.title, r.id
        LIMIT 12
        """,
        person,
        unit,
        branch_id,
        kind,
    )
    return decode_rows(rows)


async def get_university_dates(
    connection: asyncpg.Connection,
    topic: str,
    branch_id: str | None,
    year: int | None,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, title, branch_id, year, sources, data
        FROM rag.knowledge_records
        WHERE category = $1
          AND ($2::text IS NULL OR branch_id = $2
               OR (category = 'admission_deadlines' AND branch_id IS NULL))
          AND ($3::int IS NULL OR year = $3)
        ORDER BY year DESC NULLS LAST, data->>'date', data->>'table_number', title, id
        LIMIT 12
        """,
        topic,
        branch_id,
        year,
    )
    return decode_rows(rows)


async def find_scholarships(
    connection: asyncpg.Connection,
    query: str | None,
    kind: str | None,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, title, branch_id, year, sources, data
        FROM rag.knowledge_records
        WHERE (
            category = 'scholarships' AND ($2::text IS NULL OR data->>'kind' = $2)
            OR category = 'admissions_rules' AND data ? 'award_rows'
               AND ($2::text IS NULL OR $2 = 'freshmen')
        )
          AND ($1::text IS NULL OR terms @@ plainto_tsquery('russian', $1)
               OR strpos(lower(title), lower($1)) > 0)
        ORDER BY data->>'effective_from' DESC NULLS LAST,
                 data->>'starts_at' DESC NULLS LAST, title, id
        LIMIT 12
        """,
        query,
        kind,
    )
    return decode_rows(rows)


async def find_university_document_links(
    connection: asyncpg.Connection,
    query: str | None,
    act_number: str | None,
    year: int | None,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, category, title, year, sources,
               data - ARRAY['listed_by', 'download_error'] AS data
        FROM rag.knowledge_records
        WHERE category IN ('documents', 'regulations')
          AND ($1::text IS NULL OR terms @@ plainto_tsquery('russian', $1)
               OR strpos(lower(title), lower($1)) > 0)
          AND ($2::text IS NULL OR data->>'act_number' = $2
               OR regexp_replace(data->>'act_number', '^0+', '') =
                  regexp_replace($2, '^0+', '')
               OR title ~ ('№[[:space:]]*0*' || regexp_replace($2, '^0+', '') || '([^0-9]|$)'))
          AND ($3::int IS NULL OR year = $3
               OR title ~ ('(^|[^0-9])' || $3::text || '([^0-9]|$)'))
        ORDER BY (category = 'regulations') DESC, year DESC NULLS LAST,
                 data->>'date' DESC NULLS LAST, id
        LIMIT 10
        """,
        query,
        act_number,
        year,
    )
    return decode_rows(rows)


async def find_campus_details(
    connection: asyncpg.Connection,
    query: str | None,
    branch_id: str | None,
    kind: str | None,
    purpose: str,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, category, title, branch_id, sources,
               CASE WHEN $4::text = 'accessibility'
                    THEN jsonb_build_object(
                        'address', data->'address', 'address_conflict', data->'address_conflict',
                        'facilities', (
                            SELECT coalesce(jsonb_agg(item), '[]')
                            FROM (
                                SELECT item FROM jsonb_array_elements(
                                    coalesce(data->'facilities', '[]')
                                ) AS facilities(item)
                                WHERE item ? 'accessibility' LIMIT 8
                            ) entries
                        ),
                        'documents', data->'documents'
                    )
                    WHEN $4::text = 'map' THEN jsonb_build_object(
                        'address', data->'address', 'kind', data->'kind',
                        'latitude', data->'latitude', 'longitude', data->'longitude'
                    )
                    ELSE data - ARRAY['facilities', 'registry', 'photos', 'documents']
               END AS data
        FROM rag.knowledge_records
        WHERE category = CASE WHEN $4::text = 'history'
                              THEN 'building_history' ELSE 'campus_places' END
          AND ($1::text IS NULL OR terms @@ plainto_tsquery('russian', $1)
               OR strpos(lower(title), lower($1)) > 0)
          AND ($2::text IS NULL OR branch_id = $2)
          AND ($3::text IS NULL OR $4::text = 'history' OR data->>'kind' = $3)
          AND ($4::text <> 'map'
               OR (jsonb_typeof(data->'latitude') = 'number'
                   AND jsonb_typeof(data->'longitude') = 'number'))
        ORDER BY CASE WHEN $4::text = 'map' AND lower(title) = lower($1) THEN 0 ELSE 1 END,
                 title, id
        LIMIT CASE WHEN $4::text = 'map' AND $1::text IS NULL AND $3::text IS NOT NULL THEN 100
                   WHEN $4::text = 'map' THEN 20 ELSE 6 END
        """,
        query,
        branch_id,
        kind,
        purpose,
    )
    return decode_rows(rows)
