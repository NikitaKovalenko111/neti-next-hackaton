#!/usr/bin/env bash
set -euo pipefail

export POSTGRES_USER="${POSTGRES_USER:-postgres}"
export POSTGRES_DB="${POSTGRES_DB:-university}"
export BACKEND_POSTGRES_USER="${BACKEND_POSTGRES_USER:-backend_app}"
export BACKEND_POSTGRES_PASSWORD="${BACKEND_POSTGRES_PASSWORD:-backend_app}"
export RAG_POSTGRES_USER="${RAG_POSTGRES_USER:-rag_app}"
export RAG_POSTGRES_PASSWORD="${RAG_POSTGRES_PASSWORD:-rag_app}"

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

if [[ "$BACKEND_POSTGRES_USER" == "$RAG_POSTGRES_USER" ||
      "$BACKEND_POSTGRES_USER" == "$POSTGRES_USER" ||
      "$RAG_POSTGRES_USER" == "$POSTGRES_USER" ]]; then
    echo 'Backend, RAG and administrator roles must have different names.' >&2
    exit 1
fi

export PGPASSWORD="$POSTGRES_PASSWORD"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

exec psql --no-psqlrc --set=ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --file "$script_dir/schemas.sql"
