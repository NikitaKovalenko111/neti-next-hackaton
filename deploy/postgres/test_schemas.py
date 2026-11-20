import os
import subprocess
import unittest
from pathlib import Path
from uuid import uuid4


@unittest.skipUnless(
    os.getenv("TEST_POSTGRES_SCHEMAS") == "1", "requires a PostgreSQL administrator"
)
class SchemaIsolationTest(unittest.TestCase):
    def test_migration_permissions_and_repeat_provisioning(self):
        suffix = uuid4().hex
        database = f"schema_test_{suffix}"
        backend = f"backend_test_{suffix}"
        rag = f"rag_test_{suffix}"
        admin = os.getenv("PGUSER", "postgres")
        admin_database = os.getenv("PGDATABASE", "postgres")

        def sql(statement, user=admin, db=database, success=True):
            result = subprocess.run(
                [
                    "psql",
                    "--no-psqlrc",
                    "--set=ON_ERROR_STOP=1",
                    "--tuples-only",
                    "--no-align",
                    "--username",
                    user,
                    "--dbname",
                    db,
                ],
                input=statement,
                text=True,
                capture_output=True,
                check=False,
                env={**os.environ, "PGPASSWORD": "test_password"} if user != admin else None,
            )
            if success:
                self.assertEqual(result.returncode, 0, result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0, "unexpectedly allowed: " + statement)
            return result.stdout.strip()

        sql(f'CREATE DATABASE "{database}"', db=admin_database)
        try:
            root = Path(__file__).resolve().parents[2]
            migrations = root / "backend/internal/migrations"
            legacy = "\n".join(
                (migrations / name).read_text()
                for name in (
                    "001_chats.sql",
                    "002_agent_messages.sql",
                    "003_message_blocks.sql",
                )
            )
            sql(
                legacy
                + """
                CREATE TABLE schema_migrations (version integer PRIMARY KEY);
                INSERT INTO schema_migrations VALUES (1), (2), (3);
                INSERT INTO chats (id, user_id) VALUES
                ('11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222');
                INSERT INTO messages (id, chat_id, content) VALUES
                ('33333333-3333-4333-8333-333333333333',
                 '11111111-1111-4111-8111-111111111111', 'History');
            """
            )

            environment = {
                **os.environ,
                "POSTGRES_USER": admin,
                "POSTGRES_PASSWORD": os.getenv("PGPASSWORD", "test_admin_password"),
                "POSTGRES_DB": database,
                "BACKEND_POSTGRES_USER": backend,
                "BACKEND_POSTGRES_PASSWORD": "test_password",
                "RAG_POSTGRES_USER": rag,
                "RAG_POSTGRES_PASSWORD": "test_password",
            }

            def provision(success=True):
                result = subprocess.run(
                    ["bash", str(root / "deploy/postgres/provision.sh")],
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if success:
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    self.assertNotEqual(result.returncode, 0)

            provision()
            provision()

            self.assertEqual(sql("SELECT current_schema()", user=backend), "backend")
            self.assertEqual(sql("SELECT current_schema()", user=rag), "rag")
            self.assertEqual(sql("SELECT content FROM messages", user=backend), "History")
            self.assertEqual(sql("SELECT count(*) FROM backend.schema_migrations"), "3")
            self.assertEqual(sql("SELECT to_regclass('public.chats') IS NULL"), "t")
            self.assertEqual(sql("SELECT count(*) FROM pg_tables WHERE schemaname='rag'"), "0")

            sql("CREATE TABLE probe (id integer); INSERT INTO probe VALUES (1)", user=backend)
            sql("CREATE TABLE probe (id integer); INSERT INTO probe VALUES (2)", user=rag)
            self.assertEqual(sql("SELECT id FROM backend.probe", user=backend), "1")
            self.assertEqual(sql("SELECT id FROM rag.probe", user=rag), "2")

            for user, other in ((backend, "rag"), (rag, "backend")):
                sql(f"SELECT * FROM {other}.probe", user=user, success=False)
                sql(f"INSERT INTO {other}.probe VALUES (3)", user=user, success=False)
                sql(f"CREATE TABLE {other}.forbidden (id integer)", user=user, success=False)
                sql("CREATE TABLE public.forbidden (id integer)", user=user, success=False)
                sql("CREATE SCHEMA forbidden", user=user, success=False)

            sql(f'SET ROLE "{rag}"', user=backend, success=False)
            provision()
            self.assertEqual(sql("SELECT id FROM probe", user=rag), "2")

            # Ambiguous legacy layouts fail atomically rather than overwrite data.
            sql("CREATE TABLE public.chats (id integer)")
            provision(success=False)
            self.assertEqual(sql("SELECT content FROM messages", user=backend), "History")
        finally:
            sql(f'DROP DATABASE "{database}"', db=admin_database)
            sql(f'DROP ROLE IF EXISTS "{backend}"', db=admin_database)
            sql(f'DROP ROLE IF EXISTS "{rag}"', db=admin_database)


if __name__ == "__main__":
    unittest.main()
