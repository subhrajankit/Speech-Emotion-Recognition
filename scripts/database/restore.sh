#!/usr/bin/env bash
# ==============================================================================
# SenseAI Voice Assistant — Database & Vector Index Restore Script (Phase 15)
# Supports restoring SQLite / PostgreSQL databases and recovering the FAISS index.
# ==============================================================================
set -euo pipefail

usage() {
    echo "Usage: $0 --backup-file <path_to_backup_file> [--db-type <sqlite|postgres>] [--rebuild-faiss]"
    echo ""
    echo "Options:"
    echo "  --backup-file  Path to .db (SQLite) or .sql.gz (Postgres) backup file"
    echo "  --db-type      sqlite (default) or postgres"
    echo "  --rebuild-faiss Rebuild FAISS index from data/documents/ instead of binary archive"
    exit 1
}

BACKUP_FILE=""
DB_TYPE="${DB_TYPE:-sqlite}"
REBUILD_FAISS=false
SQLITE_DB_PATH="${DATABASE_PATH:-database/dev.db}"
PG_HOST="${POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-senseai}"
PG_DB="${POSTGRES_DB:-senseai}"
INDEX_DIR="${RAG_INDEX_DIR:-data/index}"
DOCS_DIR="${RAG_DOCS_DIR:-data/documents}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backup-file)
            BACKUP_FILE="$2"
            shift 2
            ;;
        --db-type)
            DB_TYPE="$2"
            shift 2
            ;;
        --rebuild-faiss)
            REBUILD_FAISS=true
            shift 1
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown argument: $1"
            usage
            ;;
    esac
done

if [ -z "${BACKUP_FILE}" ] && [ "${REBUILD_FAISS}" = false ]; then
    echo "[ERROR] Must provide --backup-file or --rebuild-faiss."
    usage
fi

echo "=================================================================="
echo " Starting SenseAI System Restoration"
echo " Database Engine : ${DB_TYPE}"
echo "=================================================================="

# ------------------------------------------------------------------------------
# 1. Database Restoration
# ------------------------------------------------------------------------------
if [ -n "${BACKUP_FILE}" ]; then
    if [ ! -f "${BACKUP_FILE}" ]; then
        echo "[ERROR] Specified backup file ${BACKUP_FILE} does not exist."
        exit 1
    fi

    # Verify SHA256 checksum if companion file exists
    if [ -f "${BACKUP_FILE}.sha256" ]; then
        echo "[1/3] Verifying SHA256 checksum for ${BACKUP_FILE}..."
        sha256sum -c "${BACKUP_FILE}.sha256"
        echo "[PASS] Checksum verified."
    fi

    if [ "${DB_TYPE}" = "sqlite" ]; then
        echo "[2/3] Restoring SQLite database to ${SQLITE_DB_PATH}..."
        # Take safety snapshot of existing database before overwriting
        if [ -f "${SQLITE_DB_PATH}" ]; then
            SAFETY_SNAPSHOT="${SQLITE_DB_PATH}.pre_restore_$(date +%Y%m%d_%H%M%S).bak"
            echo "       Taking safety snapshot of current database to ${SAFETY_SNAPSHOT}..."
            cp "${SQLITE_DB_PATH}" "${SAFETY_SNAPSHOT}"
        fi

        mkdir -p "$(dirname "${SQLITE_DB_PATH}")"
        cp "${BACKUP_FILE}" "${SQLITE_DB_PATH}"
        echo "[PASS] SQLite database restored."
    elif [ "${DB_TYPE}" = "postgres" ]; then
        echo "[2/3] Restoring PostgreSQL database (${PG_DB} on ${PG_HOST}:${PG_PORT})..."
        gunzip -c "${BACKUP_FILE}" | psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${PG_DB}"
        echo "[PASS] PostgreSQL database restored."
    fi
fi

# ------------------------------------------------------------------------------
# 2. FAISS Vector Index Recovery
# ------------------------------------------------------------------------------
if [ "${REBUILD_FAISS}" = true ]; then
    echo "[3/3] Rebuilding FAISS vector index directly from source documents in ${DOCS_DIR}..."
    python scripts/database/build_rag_index.py --docs-dir "${DOCS_DIR}" --output-dir "${INDEX_DIR}"
    echo "[PASS] FAISS vector index successfully rebuilt."
fi

echo "=================================================================="
echo " Restoration Completed Successfully (EXIT 0)"
echo "=================================================================="
