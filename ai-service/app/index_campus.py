import argparse
import asyncio
import json
import logging

import asyncpg
import httpx

from app.clients.openrouter import openrouter_http
from app.config import Settings
from app.embeddings import BATCH_SIZE, embed
from app.material_support import find_ground, index_material_support, search_material_support
from app.storage import connect_rag, migrate

logger = logging.getLogger(__name__)


async def index_campus(
    connection: asyncpg.Connection, client: httpx.AsyncClient, model: str
) -> int:
    rows = await connection.fetch(
        """
        SELECT d.kind, d.id, d.content
        FROM rag.campus_documents d
        LEFT JOIN rag.campus_embeddings e
            ON e.kind = d.kind AND e.record_id = d.id AND e.model = $1
        WHERE e.content IS DISTINCT FROM d.content
        ORDER BY d.kind, d.id
        """,
        model,
    )
    for offset in range(0, len(rows), BATCH_SIZE):
        batch = rows[offset : offset + BATCH_SIZE]
        vectors = await embed(client, model, [row["content"] for row in batch])
        await connection.executemany(
            """
            INSERT INTO rag.campus_embeddings (kind, record_id, model, content, embedding)
            VALUES ($1, $2, $3, $4, $5::text::rag.vector(1024))
            ON CONFLICT (kind, record_id, model) DO UPDATE
            SET content = excluded.content, embedding = excluded.embedding
            """,
            [
                (row["kind"], row["id"], model, row["content"], vector)
                for row, vector in zip(batch, vectors, strict=True)
            ],
        )
    return len(rows)


async def search_campus(
    connection: asyncpg.Connection,
    client: httpx.AsyncClient,
    model: str,
    query: str,
    branch: str | None = None,
    kind: str | None = None,
) -> list[dict]:
    (vector,) = await embed(client, model, [query])
    rows = await connection.fetch(
        """
        SELECT d.kind, d.id, d.branch_id, d.title, d.content,
               ARRAY(SELECT s.url FROM rag.campus_sources s
                     WHERE d.source_ids ? s.id ORDER BY s.id) AS sources,
               1 - (e.embedding OPERATOR(rag.<=>) $1::text::rag.vector(1024)) AS similarity
        FROM rag.campus_documents d
        JOIN rag.campus_embeddings e
            ON e.kind = d.kind AND e.record_id = d.id AND e.content = d.content
        WHERE e.model = $2
          AND ($3::text IS NULL OR d.branch_id = $3)
          AND ($4::text IS NULL OR d.kind = $4)
        ORDER BY similarity DESC, d.kind, d.id
        LIMIT 5
        """,
        vector,
        model,
        branch,
        kind,
    )
    return [dict(row) for row in rows]


async def main(args: argparse.Namespace) -> None:
    settings = Settings()
    async with connect_rag(settings) as connection:
        if args.import_only:
            await migrate(connection)
            return

        if args.ground is not None:
            result = await find_ground(connection, args.ground, args.branch)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        async with openrouter_http(settings) as client:
            model = settings.openrouter_embedding_model
            if args.query is not None:
                matches = await search_campus(
                    connection, client, model, args.query, args.branch, args.kind
                )
                print(json.dumps(matches, ensure_ascii=False, indent=2))
                return

            if args.support_query is not None:
                matches = await search_material_support(
                    connection, client, model, args.support_query, args.branch
                )
                print(json.dumps(matches, ensure_ascii=False, indent=2))
                return

            await migrate(connection)
            await connection.execute("SELECT pg_advisory_lock(781234911)")
            try:
                count = await index_campus(connection, client, model)
                grounds = await index_material_support(connection, client, model)
            finally:
                await connection.execute("SELECT pg_advisory_unlock(781234911)")
            logger.info(
                "Indexed %d campus documents and %d support grounds with %s", count, grounds, model
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Import and search campus and material support data"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--import-only", action="store_true", help="Import with PostgreSQL only")
    mode.add_argument("--query", help="Find related campus documents")
    mode.add_argument("--support-query", help="Find material support grounds by meaning")
    mode.add_argument("--ground", help="Look up a material support ground by ID in PostgreSQL")
    parser.add_argument("--branch", help="Filter search by branch ID")
    parser.add_argument("--kind", choices=("branch", "building", "dormitory", "housing"))
    asyncio.run(main(parser.parse_args()))
