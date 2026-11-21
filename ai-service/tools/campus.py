import json
from typing import Any

import asyncpg

from app.index_campus import search_campus

__all__ = [
    "find_place",
    "get_housing",
    "list_branches",
    "list_photos",
    "search_campus",
    "search_places",
]


async def list_branches(connection: asyncpg.Connection, query: str | None = None) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT to_jsonb(b) - 'payload' || jsonb_build_object(
            'abbreviation', b.payload->>'abbreviation', 'website', b.payload->>'website',
            'history', b.payload->>'history', 'formed_year', b.payload->'formed_year',
            'sources', ARRAY(SELECT to_jsonb(s) FROM rag.campus_sources s
                             WHERE b.payload->'sources' ? s.id ORDER BY s.id)
        ) AS data
        FROM rag.campus_branches b
        WHERE $1::text IS NULL
           OR strpos(lower(b.id || ' ' || b.city || ' ' || b.name), lower($1)) > 0
           OR to_tsvector('russian', b.city || ' ' || b.name)
              @@ plainto_tsquery('russian', $1)
        ORDER BY (b.kind = 'main_campus') DESC, b.city
        """,
        query,
    )
    return [json.loads(row["data"]) for row in rows]


async def search_places(
    connection: asyncpg.Connection,
    *,
    query: str | None = None,
    branch_id: str | None = None,
    kind: str | None = None,
    number: int | None = None,
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    rows = await connection.fetch(
        """
        WITH places AS (
            SELECT p.id, p.branch_id, p.kind, p.name, p.full_address, p.address_conflict,
                   coalesce((p.payload->>'number')::integer,
                            substring(p.name FROM '№[[:space:]]*([0-9]+)')::integer) AS number,
                   lower(concat_ws(' ', p.name, p.full_address, p.address_conflict::text)) AS text
            FROM rag.campus_places p
            WHERE ($2::text IS NULL OR p.branch_id = $2)
              AND ($3::text IS NULL OR p.kind = $3)
        )
        SELECT id, branch_id, kind, name, full_address, address_conflict::text, number
        FROM places
        WHERE ($1::text IS NULL OR id = lower($1) OR strpos(text, lower($1)) > 0
               OR to_tsvector('russian', text) @@ plainto_tsquery('russian', $1))
          AND ($4::integer IS NULL OR number = $4)
        ORDER BY (id = lower($1)) DESC NULLS LAST,
                 (strpos(lower(name), lower($1)) > 0) DESC NULLS LAST,
                 branch_id, number NULLS LAST, name, id
        LIMIT $5 OFFSET $6
        """,
        query,
        branch_id,
        kind,
        number,
        limit + 1,
        offset,
    )
    items = []
    for row in rows[:limit]:
        item = dict(row)
        if item["address_conflict"] is not None:
            item["address_conflict"] = json.loads(item["address_conflict"])
        items.append(item)
    return {"items": items, "next_offset": offset + limit if len(rows) > limit else None}


async def find_place(connection: asyncpg.Connection, place_id: str) -> dict | None:
    row = await connection.fetchval(
        """
        SELECT p.payload - 'photo_ids' - 'candidate_photo_ids' - 'source_ids'
               || jsonb_build_object(
                   'kind', p.kind,
                   'sources', ARRAY(SELECT to_jsonb(s) FROM rag.campus_sources s
                                    WHERE p.payload->'source_ids' ? s.id ORDER BY s.id)
               )
        FROM rag.campus_places p WHERE p.id = $1
        """,
        place_id,
    )
    return json.loads(row) if row is not None else None


async def get_housing(connection: asyncpg.Connection, branch_id: str) -> dict | None:
    row = await connection.fetchval(
        """
        SELECT h.payload - 'source_ids' || jsonb_build_object(
            'city', b.city,
            'branch_name', b.name,
            'sources', ARRAY(SELECT to_jsonb(s) FROM rag.campus_sources s
                             WHERE h.payload->'source_ids' ? s.id ORDER BY s.id),
            'dormitories', ARRAY(SELECT jsonb_build_object(
                    'id', p.id, 'name', p.name, 'address', p.full_address,
                    'address_conflict', p.address_conflict
                )
                FROM rag.campus_places p
                WHERE p.branch_id = h.branch_id AND p.kind = 'dormitory'
                ORDER BY (p.payload->>'number')::integer NULLS LAST, p.id)
        )
        FROM rag.campus_housing h
        JOIN rag.campus_branches b ON b.id = h.branch_id
        WHERE h.branch_id = $1
        """,
        branch_id,
    )
    return json.loads(row) if row is not None else None


async def list_photos(
    connection: asyncpg.Connection,
    branch_id: str | None,
    place_id: str | None,
    include_unverified: bool,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT ph.payload - 'source_ids' || jsonb_build_object(
            'sources', ARRAY(SELECT to_jsonb(s) FROM rag.campus_sources s
                             WHERE ph.payload->'source_ids' ? s.id ORDER BY s.id)
        ) AS data
        FROM rag.campus_photos ph
        WHERE ($1::text IS NULL OR ph.branch_id = $1)
          AND ($2::text IS NULL OR ph.object_id = $2)
          AND ($3::boolean OR ph.attribution_status = 'object_verified')
        ORDER BY (ph.attribution_status = 'object_verified') DESC, ph.id
        """,
        branch_id,
        place_id,
        include_unverified,
    )
    return [json.loads(row["data"]) for row in rows]


async def get_data_scope(connection: asyncpg.Connection) -> dict:
    row = await connection.fetchrow("""
        SELECT (SELECT metadata::text FROM rag.campus_dataset) AS campus,
               (SELECT max(metadata#>>'{dataset,as_of}') FROM rag.support_programs) AS support_as_of
    """)
    return {
        "campus": json.loads(row["campus"]) if row["campus"] is not None else None,
        "material_support_as_of": row["support_as_of"],
        "topics_not_covered": [
            "Текущее количество свободных мест, стоимость и графики заселения",
            "Расписание занятий, номера аудиторий и маршруты внутри зданий",
            "GPS-координаты, доступность входов и транспорт в реальном времени",
            "Персональный статус заявления и назначенная конкретному студенту выплата",
        ],
    }
