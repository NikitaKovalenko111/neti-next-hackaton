from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.resources import files

import asyncpg

from app.config import Settings

MIGRATIONS = (
    ("001_campus", None),
    ("002_campus_seed", "all.json"),
    ("003_material_support", None),
    ("004_material_support_seed", "material_support.json"),
    ("005_campus_photo_objects", None),
    ("006_university_knowledge", None),
    ("007_university_knowledge_seed", "university_knowledge.json"),
)


@asynccontextmanager
async def connect_rag(settings: Settings) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(
        host=settings.rag_postgres_host,
        port=settings.rag_postgres_port,
        database=settings.rag_postgres_db,
        user=settings.rag_postgres_user,
        password=settings.rag_postgres_password.get_secret_value(),
        server_settings={"search_path": "rag"},
        timeout=10,
    )
    try:
        yield connection
    finally:
        await connection.close()


async def migrate(connection: asyncpg.Connection) -> None:
    resources = files("app.migrations")
    async with connection.transaction():
        await connection.execute("SET LOCAL search_path = rag")
        await connection.execute("SELECT pg_advisory_xact_lock(781234910)")
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS campus_migrations (
                version text PRIMARY KEY
            )
        """)
        applied = await connection.fetch("SELECT version FROM campus_migrations")
        versions = {row["version"] for row in applied}

        for version, seed in MIGRATIONS:
            if version in versions:
                continue

            if seed is not None:
                await connection.execute("""
                    CREATE TEMP TABLE rag_seed (data jsonb NOT NULL) ON COMMIT DROP
                """)
                await connection.execute(
                    "INSERT INTO pg_temp.rag_seed VALUES ($1::jsonb)",
                    resources.joinpath(seed).read_text(encoding="utf-8"),
                )

            await connection.execute(
                resources.joinpath(f"{version}.sql").read_text(encoding="utf-8")
            )
            if seed is not None:
                await connection.execute("DROP TABLE pg_temp.rag_seed")

            await connection.execute("INSERT INTO campus_migrations VALUES ($1)", version)
