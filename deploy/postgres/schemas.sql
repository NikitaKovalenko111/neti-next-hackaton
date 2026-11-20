\getenv db_name POSTGRES_DB
\getenv backend_user BACKEND_POSTGRES_USER
\getenv backend_password BACKEND_POSTGRES_PASSWORD
\getenv rag_user RAG_POSTGRES_USER
\getenv rag_password RAG_POSTGRES_PASSWORD

BEGIN;
SELECT pg_advisory_xact_lock(781234902);

SELECT format('CREATE ROLE %I LOGIN', :'backend_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'backend_user') \gexec

SELECT format('CREATE ROLE %I LOGIN', :'rag_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'rag_user') \gexec

ALTER ROLE :"backend_user" NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS
    PASSWORD :'backend_password';
ALTER ROLE :"rag_user" NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS
    PASSWORD :'rag_password';

GRANT CONNECT ON DATABASE :"db_name" TO :"backend_user", :"rag_user";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA IF NOT EXISTS backend AUTHORIZATION :"backend_user";
CREATE SCHEMA IF NOT EXISTS rag AUTHORIZATION :"rag_user";
ALTER SCHEMA backend OWNER TO :"backend_user";
ALTER SCHEMA rag OWNER TO :"rag_user";

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA rag;

REVOKE ALL ON SCHEMA backend FROM PUBLIC, :"rag_user";
REVOKE ALL ON SCHEMA rag FROM PUBLIC, :"backend_user";

-- Upgrade the original layout without recreating tables or losing history.
DO $migration$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'schema_migrations', 'chats', 'messages', 'attachments', 'agent_request_outbox'
    ] LOOP
        IF to_regclass(format('public.%I', table_name)) IS NOT NULL THEN
            IF to_regclass(format('backend.%I', table_name)) IS NOT NULL THEN
                RAISE EXCEPTION 'Both public.% and backend.% exist; resolve the conflict before provisioning',
                    table_name, table_name;
            END IF;

            EXECUTE format('ALTER TABLE public.%I SET SCHEMA backend', table_name);
        END IF;
    END LOOP;
END
$migration$;

SELECT format('ALTER TABLE backend.%I OWNER TO %I', tablename, :'backend_user')
FROM pg_tables WHERE schemaname = 'backend' \gexec

SELECT format('ALTER SEQUENCE backend.%I OWNER TO %I', c.relname, :'backend_user')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'backend' AND c.relkind = 'S' \gexec

REVOKE ALL ON ALL TABLES IN SCHEMA backend FROM PUBLIC, :"rag_user";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA backend FROM PUBLIC, :"rag_user";
REVOKE ALL ON ALL TABLES IN SCHEMA rag FROM PUBLIC, :"backend_user";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA rag FROM PUBLIC, :"backend_user";

ALTER ROLE :"backend_user" IN DATABASE :"db_name" SET search_path = backend;
ALTER ROLE :"rag_user" IN DATABASE :"db_name" SET search_path = rag;

COMMIT;
