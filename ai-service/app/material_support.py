import json

import asyncpg
import httpx

from app.embeddings import BATCH_SIZE, embed


async def index_material_support(
    connection: asyncpg.Connection, client: httpx.AsyncClient, model: str
) -> int:
    rows = await connection.fetch(
        """
        SELECT g.id, g.content
        FROM rag.support_ground_texts g
        LEFT JOIN rag.support_embeddings e ON e.ground_id = g.id AND e.model = $1
        WHERE e.content IS DISTINCT FROM g.content
        ORDER BY g.id
        """,
        model,
    )
    for offset in range(0, len(rows), BATCH_SIZE):
        batch = rows[offset : offset + BATCH_SIZE]
        vectors = await embed(client, model, [row["content"] for row in batch])
        await connection.executemany(
            """
            INSERT INTO rag.support_embeddings (ground_id, model, content, embedding)
            VALUES ($1, $2, $3, $4::text::rag.vector(1024))
            ON CONFLICT (ground_id, model) DO UPDATE
            SET content = excluded.content, embedding = excluded.embedding
            """,
            [
                (row["id"], model, row["content"], vector)
                for row, vector in zip(batch, vectors, strict=True)
            ],
        )
    return len(rows)


async def find_ground(
    connection: asyncpg.Connection, ground_id: str, branch: str | None = None
) -> dict | None:
    result = await connection.fetchval(
        """
        SELECT to_jsonb(d) || jsonb_build_object(
            'submission_channels', ARRAY(
                SELECT to_jsonb(c) FROM rag.support_channels c
                JOIN rag.support_channel_branches cb ON cb.channel_id = c.id
                WHERE c.program_id = d.program_id AND cb.branch_id = $2::text
                ORDER BY c.id
            )
        )
        FROM rag.support_ground_details d
        WHERE d.id = $1 AND ($2::text IS NULL OR EXISTS (
            SELECT 1 FROM rag.support_program_branches b
            WHERE b.program_id = d.program_id AND b.branch_id = $2
        ))
        """,
        ground_id,
        branch,
    )
    return json.loads(result) if result is not None else None


async def search_material_support(
    connection: asyncpg.Connection,
    client: httpx.AsyncClient,
    model: str,
    query: str,
    branch: str | None = None,
) -> list[dict]:
    (vector,) = await embed(client, model, [query])
    rows = await connection.fetch(
        """
        WITH candidates AS (
            SELECT g.id, e.embedding OPERATOR(rag.<=>) $1::text::rag.vector(1024) AS distance
            FROM rag.support_embeddings e
            JOIN rag.support_ground_texts t ON t.id = e.ground_id AND t.content = e.content
            JOIN rag.support_grounds g ON g.id = t.id
            WHERE e.model = $2 AND ($3::text IS NULL OR EXISTS (
                SELECT 1 FROM rag.support_program_branches b
                WHERE b.program_id = g.program_id AND b.branch_id = $3
            ))
            ORDER BY distance, g.id
            LIMIT 5
        )
        SELECT to_jsonb(d) || jsonb_build_object('similarity', 1 - c.distance) AS ground
        FROM candidates c JOIN rag.support_ground_details d ON d.id = c.id
        ORDER BY c.distance, c.id
        """,
        vector,
        model,
        branch,
    )
    return [json.loads(row["ground"]) for row in rows]
