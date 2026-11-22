import json

import asyncpg
import httpx

from app.embeddings import BATCH_SIZE, embed


async def index_knowledge(
    connection: asyncpg.Connection, client: httpx.AsyncClient, model: str
) -> int:
    pending = await connection.fetch(
        """
        SELECT n.id, n.title || E'\n' || n.summary AS content
        FROM rag.knowledge_notes n
        LEFT JOIN rag.knowledge_embeddings e ON e.note_id = n.id AND e.model = $1
        WHERE e.content IS DISTINCT FROM (n.title || E'\n' || n.summary)
        ORDER BY n.id
        """,
        model,
    )
    for offset in range(0, len(pending), BATCH_SIZE):
        batch = pending[offset : offset + BATCH_SIZE]
        vectors = await embed(client, model, [row["content"] for row in batch])
        await connection.executemany(
            """
            INSERT INTO rag.knowledge_embeddings (note_id, model, content, embedding)
            VALUES ($1, $2, $3, $4::text::rag.vector(1024))
            ON CONFLICT (note_id, model) DO UPDATE
            SET content = excluded.content, embedding = excluded.embedding
            """,
            [
                (row["id"], model, row["content"], vector)
                for row, vector in zip(batch, vectors, strict=True)
            ],
        )
    return len(pending)


async def search_records(
    connection: asyncpg.Connection,
    query: str | None,
    category: str | None,
    branch_id: str | None,
    reference_code: str | None,
) -> list[dict]:
    rows = await connection.fetch(
        """
        SELECT id, category, title, branch_id, reference_code, year, sources,
               data - ARRAY['disciplines', 'documents', 'entries', 'practice',
                            'calendar', 'registry', 'facilities', 'photos'] AS data
        FROM rag.knowledge_records
        WHERE ($1::text IS NULL OR terms @@ websearch_to_tsquery('russian', $1)
               OR strpos(lower(title), lower($1)) > 0 OR reference_code = $1)
          AND ($2::text IS NULL OR category = $2)
          AND ($3::text IS NULL OR branch_id = $3)
          AND ($4::text IS NULL OR reference_code = $4)
        ORDER BY coalesce(reference_code = $1, false) DESC,
                 coalesce(ts_rank(terms, websearch_to_tsquery('russian', $1)), 0) DESC,
                 year DESC NULLS LAST, id
        LIMIT 8
        """,
        query,
        category,
        branch_id,
        reference_code,
    )
    return [{**dict(row), "data": json.loads(row["data"])} for row in rows]


async def get_record(connection: asyncpg.Connection, record_id: str) -> dict | None:
    row = await connection.fetchrow(
        """
        SELECT id, category, title, branch_id, reference_code, year, sources, data
        FROM rag.knowledge_records WHERE id = $1
        """,
        record_id,
    )
    return {**dict(row), "data": json.loads(row["data"])} if row is not None else None


async def search_notes(
    connection: asyncpg.Connection,
    client: httpx.AsyncClient,
    model: str,
    *,
    query: str,
    category: str | None = None,
) -> list[dict]:
    (vector,) = await embed(client, model, [query])
    rows = await connection.fetch(
        """
        SELECT n.id, n.category, n.title, n.summary, n.sources, n.dates,
               1 - (e.embedding OPERATOR(rag.<=>) $1::text::rag.vector(1024)) AS similarity
        FROM rag.knowledge_notes n
        JOIN rag.knowledge_embeddings e ON e.note_id = n.id
        WHERE e.model = $2 AND ($3::text IS NULL OR n.category = $3)
          AND e.content = (n.title || E'\n' || n.summary)
        ORDER BY similarity DESC, n.id
        LIMIT 5
        """,
        vector,
        model,
        category,
    )
    return [{**dict(row), "dates": json.loads(row["dates"])} for row in rows]
