#!/usr/bin/env bash
# ==============================================================================
# SenseAI Voice Assistant — Database & Vector Index Backup Script (Phase 15)
# Supports: SQLite (dev) & PostgreSQL (prod), plus FAISS vector index archive.
# ==============================================================================
set -euo pipefail

# Configuration defaults
BACKUP_DIR="${BACKUP_DIR:-backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DB_TYPE="${DB_TYPE:-sqlite}"
SQLITE_DB_PATH="${DATABASE_PATH:-database/dev.db}"
PG_HOST="${POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-senseai}"
PG_DB="${POSTGRES_DB:-senseai}"
INDEX_DIR="${RAG_INDEX_DIR:-data/index}"
DOCS_DIR="${RAG_DOCS_DIR:-data/documents}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

mkdir -p "${BACKUP_DIR}"

echo "=================================================================="
echo " Starting SenseAI System Backup [${TIMESTAMP}]"
echo " Target Directory: ${BACKUP_DIR}"
echo " Database Engine : ${DB_TYPE}"
echo "=================================================================="

# ------------------------------------------------------------------------------
# 1. Relational Database Backup
# ------------------------------------------------------------------------------
if [ "${DB_TYPE}" = "sqlite" ]; then
    if [ -f "${SQLITE_DB_PATH}" ]; then
        DB_BACKUP_FILE="${BACKUP_DIR}/sqlite_${TIMESTAMP}.db"
        echo "[1/3] Backing up SQLite database from ${SQLITE_DB_PATH}..."
        # Use safe online SQLite .backup to prevent dirty reads during writes
        if command -v sqlite3 >/dev/null 2>&1; then
            sqlite3 "${SQLITE_DB_PATH}" ".backup '${DB_BACKUP_FILE}'"
        else
            cp "${SQLITE_DB_PATH}" "${DB_BACKUP_FILE}"
        fi
        sha256sum "${DB_BACKUP_FILE}" > "${DB_BACKUP_FILE}.sha256"
        echo "[PASS] SQLite backup created: ${DB_BACKUP_FILE}"
    else
        echo "[WARN] SQLite database file ${SQLITE_DB_PATH} not found. Skipping DB backup."
    fi
elif [ "${DB_TYPE}" = "postgres" ]; then
    PG_BACKUP_FILE="${BACKUP_DIR}/postgres_${TIMESTAMP}.sql.gz"
    echo "[1/3] Backing up PostgreSQL database (${PG_DB} on ${PG_HOST}:${PG_PORT})..."
    pg_dump -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" "${PG_DB}" | gzip -c > "${PG_BACKUP_FILE}"
    sha256sum "${PG_BACKUP_FILE}" > "${PG_BACKUP_FILE}.sha256"
    echo "[PASS] PostgreSQL backup created: ${PG_BACKUP_FILE}"
fi

# ------------------------------------------------------------------------------
# 2. FAISS Vector Index Archive (Optional snapshot; fully rebuildable from docs)
# ------------------------------------------------------------------------------
echo "[2/3] Checking FAISS Vector Index in ${INDEX_DIR}..."
if [ -d "${INDEX_DIR}" ] && [ "$(ls -A "${INDEX_DIR}")" ]; then
    INDEX_BACKUP_FILE="${BACKUP_DIR}/faiss_index_${TIMESTAMP}.tar.gz"
    tar -czf "${INDEX_BACKUP_FILE}" -C "${INDEX_DIR}" .
    sha256sum "${INDEX_BACKUP_FILE}" > "${INDEX_BACKUP_FILE}.sha256"
    echo "[PASS] FAISS index archive created: ${INDEX_BACKUP_FILE}"
    echo "       Note: FAISS index is rebuildable at any time from ${DOCS_DIR}"
    echo "       via: python scripts/database/build_rag_index.py"
else
    echo "[INFO] No pre-built FAISS index in ${INDEX_DIR}. Rebuild path from ${DOCS_DIR} active."
fi

# ------------------------------------------------------------------------------
# 3. Clean up expired backups older than RETENTION_DAYS
# ------------------------------------------------------------------------------
echo "[3/3] Pruning backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -type f -name "*.*" -mtime +"${RETENTION_DAYS}" -delete || true

echo "=================================================================="
echo " Backup Completed Successfully (EXIT 0)"
echo "=================================================================="
