import json

import asyncpg

from app.material_support import find_ground, search_material_support

__all__ = [
    "find_ground",
    "get_programs",
    "list_channels",
    "list_grounds",
    "search_material_support",
]


async def list_grounds(
    connection: asyncpg.Connection,
    query: str | None,
    branch_id: str | None,
    number: int | None,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT g.id, g.program_id, g.number_in_regulation, g.title, g.frequency, g.source_pdf_pages,
               s.url AS source_url
        FROM rag.support_grounds g JOIN rag.support_sources s ON s.id = g.source_id
        WHERE ($1::text IS NULL OR g.id = lower($1) OR
               to_tsvector('russian', g.title || ' ' || g.description)
               @@ plainto_tsquery('russian', $1))
          AND ($2::text IS NULL OR EXISTS (
            SELECT 1 FROM rag.support_program_branches b
            WHERE b.program_id = g.program_id AND b.branch_id = $2
          ))
          AND ($3::int IS NULL OR g.number_in_regulation = $3)
        ORDER BY g.program_id, g.number_in_regulation
        """,
        query,
        branch_id,
        number,
    )
    return [dict(row) for row in rows]


async def get_programs(
    connection: asyncpg.Connection, branch_id: str | None, program_id: str | None
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT to_jsonb(p) - 'metadata' || jsonb_build_object(
            'source', to_jsonb(s),
            'regulation_pages', p.metadata#>'{policy,regulation_pages}',
            'eligible_student_levels', p.metadata#>'{policy,eligible_student_levels}',
            'branch_ids', ARRAY(SELECT b.branch_id FROM rag.support_program_branches b
                                WHERE b.program_id = p.id ORDER BY b.branch_id)
        ) AS data
        FROM rag.support_programs p JOIN rag.support_sources s ON s.id = p.source_id
        WHERE ($1::text IS NULL OR EXISTS (
            SELECT 1 FROM rag.support_program_branches b
            WHERE b.program_id = p.id AND b.branch_id = $1
        )) AND ($2::text IS NULL OR p.id = $2)
        ORDER BY p.effective_from DESC, p.id
        """,
        branch_id,
        program_id,
    )
    return [json.loads(row["data"]) for row in rows]


async def list_channels(
    connection: asyncpg.Connection, branch_id: str, include_consultations: bool
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT to_jsonb(c) || jsonb_build_object(
            'is_main_application_channel', c.program_id IS NOT NULL,
            'sources', ARRAY(SELECT to_jsonb(s) FROM rag.support_channel_sources cs
                             JOIN rag.support_sources s ON s.id = cs.source_id
                             WHERE cs.channel_id = c.id ORDER BY s.id)
        ) AS data
        FROM rag.support_channels c
        JOIN rag.support_channel_branches b ON b.channel_id = c.id
        WHERE b.branch_id = $1 AND ($2::boolean OR c.program_id IS NOT NULL)
        ORDER BY (c.program_id IS NOT NULL) DESC, c.id
        """,
        branch_id,
        include_consultations,
    )
    return [json.loads(row["data"]) for row in rows]
