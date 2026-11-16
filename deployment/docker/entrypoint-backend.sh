#!/bin/sh
set -eu

# Load optional runtime Hugging Face token from Docker secret without exposing it in image or compose env
if [ -z "${HF_TOKEN:-}" ] && [ -f /run/secrets/hf_token ]; then
    HF_TOKEN_VALUE="$(tr -d '\r\n' < /run/secrets/hf_token)"
    if [ -n "${HF_TOKEN_VALUE}" ]; then
        export HF_TOKEN="${HF_TOKEN_VALUE}"
    fi
fi

# Run Alembic schema migrations when explicitly enabled (production Postgres / fresh DB init)
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "[entrypoint] Running database migrations (alembic upgrade head)..."
    alembic upgrade head
fi

exec "$@"

