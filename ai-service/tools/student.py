import asyncpg

from tools.education import decode_rows


async def find_admission_seats(
    connection: asyncpg.Connection,
    query: str | None,
    branch_id: str | None,
    reference_code: str | None,
    level: str | None,
    form: str | None,
    year: int | None,
    campaign: str | None,
    seat_type: str | None,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, title, branch_id, reference_code, year, sources, data
        FROM rag.knowledge_records
        WHERE category = 'admission_seats'
          AND ($1::text IS NULL OR terms @@ plainto_tsquery('russian', $1)
               OR strpos(lower(title), lower($1)) > 0)
          AND ($2::text IS NULL OR branch_id = $2)
          AND ($3::text IS NULL OR reference_code = $3)
          AND ($4::text IS NULL OR data->>'level' = $4)
          AND ($5::text IS NULL OR data->>'form' = $5)
          AND ($6::int IS NULL OR year = $6)
          AND ($7::text IS NULL OR data->>'campaign' = $7)
          AND ($8::text IS NULL OR data->'seats'->>$8 IS NOT NULL)
        ORDER BY year DESC NULLS LAST, branch_id, reference_code, data->>'form', title, id
        LIMIT 24
        """,
        query,
        branch_id,
        reference_code,
        level,
        form,
        year,
        campaign,
        seat_type,
    )
    return decode_rows(rows)


async def find_transfer_vacancies(
    connection: asyncpg.Connection,
    query: str | None,
    branch_id: str | None,
    reference_code: str | None,
    form: str | None,
    course: int | None,
    funding: str | None,
    has_places: bool,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, title, branch_id, reference_code, year, sources, data
        FROM rag.knowledge_records r
        WHERE category = 'transfer_vacancies'
          AND ($1::text IS NULL OR terms @@ plainto_tsquery('russian', $1)
               OR strpos(lower(title), lower($1)) > 0)
          AND ($2::text IS NULL OR branch_id = $2)
          AND ($3::text IS NULL OR reference_code = $3)
          AND ($4::text IS NULL OR data->>'form' = $4)
          AND ($5::int IS NULL OR data->>'course' = $5::int::text)
          AND (NOT $7::boolean OR EXISTS (
                SELECT 1 FROM jsonb_each_text(r.data->'vacancies') AS v(kind, count)
                WHERE ($6::text IS NULL OR ($6 = 'budget' AND kind LIKE 'budget_%')
                       OR ($6 = 'contract' AND kind = 'contract'))
                  AND v.count::integer > 0
              ))
        ORDER BY data->>'as_of' DESC NULLS LAST, branch_id, reference_code,
                 (data->>'course')::integer NULLS LAST, title, id
        LIMIT 24
        """,
        query,
        branch_id,
        reference_code,
        form,
        course,
        funding,
        has_places,
    )
    return decode_rows(rows)


async def find_admission_calendar(
    connection: asyncpg.Connection,
    query: str | None,
    level: str | None,
    form: str | None,
    funding: str | None,
    campaign: str | None,
    year: int | None,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, title, year, sources, data
        FROM rag.knowledge_records
        WHERE category = 'admission_calendar'
          AND ($1::text IS NULL OR terms @@ plainto_tsquery('russian', $1)
               OR strpos(lower(title), lower($1)) > 0)
          AND ($2::text IS NULL OR data->>'level' = $2)
          AND ($3::text IS NULL OR NOT (data ? 'forms') OR data->'forms' ? $3)
          AND ($4::text IS NULL OR data->'funding' ? $4)
          AND ($5::text IS NULL OR data->>'campaign' = $5)
          AND ($6::int IS NULL OR year = $6)
        ORDER BY year DESC NULLS LAST, data->>'date', data->>'local_time', title, id
        LIMIT 30
        """,
        query,
        level,
        form,
        funding,
        campaign,
        year,
    )
    return decode_rows(rows)


async def find_housing_move_in(
    connection: asyncpg.Connection,
    branch_id: str | None,
    year: int | None,
    kind: str,
    query: str | None,
    date: str | None,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, category, title, branch_id, year, sources, data
        FROM rag.knowledge_records
        WHERE category = $3
          AND ($1::text IS NULL OR branch_id = $1)
          AND ($2::int IS NULL OR year = $2)
          AND ($4::text IS NULL OR terms @@ plainto_tsquery('russian', $4)
               OR strpos(lower(title), lower($4)) > 0)
          AND ($5::text IS NULL OR data->>'date' = $5 OR data->'dates' ? $5)
        ORDER BY year DESC NULLS LAST, branch_id, data->>'date', data->>'starts_at', id
        LIMIT 20
        """,
        branch_id,
        year,
        "housing_movements" if kind == "procedure" else "housing_sessions",
        query,
        date,
    )
    return decode_rows(rows)


async def find_student_resources(
    connection: asyncpg.Connection,
    catalog: str,
    query: str | None,
    branch_id: str | None,
    topic: str | None,
    year: int | None,
    reference_code: str | None,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, category, title, branch_id, reference_code, year, sources,
               data - ARRAY['staff', 'events', 'sections'] AS data
        FROM rag.knowledge_records
        WHERE category IN ('student_life', 'student_clubs', 'academic_mobility',
                           'program_projects', 'vuc_admission', 'university_history',
                           'research_events')
          AND ($1 = 'all' OR category = $1)
          AND ($2::text IS NULL OR terms @@ websearch_to_tsquery('russian', $2)
               OR strpos(lower(title), lower($2)) > 0)
          AND ($3::text IS NULL OR branch_id = $3 OR branch_id IS NULL)
          AND ($4::text IS NULL OR data->>'category' = $4)
          AND ($5::int IS NULL OR year = $5)
          AND ($6::text IS NULL OR reference_code = $6 OR data->'direction_codes' ? $6)
        ORDER BY coalesce(ts_rank(terms, websearch_to_tsquery('russian', $2)), 0) DESC,
                 year DESC NULLS LAST, title, id
        LIMIT 10
        """,
        catalog,
        query,
        branch_id,
        topic,
        year,
        reference_code,
    )
    return decode_rows(rows)


async def find_campus_services(
    connection: asyncpg.Connection,
    query: str | None,
    branch_id: str | None,
    topic: str | None,
    include_map: bool,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, title, branch_id, sources, data
        FROM rag.knowledge_records
        WHERE category = 'campus_services'
          AND ($1::text IS NULL OR terms @@ plainto_tsquery('russian', $1)
               OR strpos(lower(title), lower($1)) > 0 OR data->>'id' = $1)
          AND ($2::text IS NULL OR branch_id = $2)
          AND ($3::text IS NULL OR data->>'category' = $3)
          AND (NOT $4::boolean OR (jsonb_typeof(data->'latitude') = 'number'
                   AND jsonb_typeof(data->'longitude') = 'number'))
        ORDER BY coalesce(ts_rank(terms, plainto_tsquery('russian', $1)), 0) DESC, title, id
        LIMIT 15
        """,
        query,
        branch_id,
        topic,
        include_map,
    )
    return decode_rows(rows)
