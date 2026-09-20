# Runbook: Backup & Disaster Recovery

## Project: SenseAI Voice Assistant
**Operational Scope**: SQLite (`database/dev.db`), PostgreSQL (`senseai` DB), and FAISS Vector Index (`data/index/`).

---

## 1. Backup Targets & Strategy Overview

| Subsystem | Storage Format | Backup Method | RPO (Recovery Point Objective) | RTO (Recovery Time Objective) |
| :--- | :--- | :--- | :--- | :--- |
| **SQLite (Dev)** | Single `.db` file | Safe `.backup` snapshot + SHA256 checksum | 24 Hours (Daily) | < 2 Minutes |
| **PostgreSQL (Prod)** | Relational tables | `pg_dump` compressed SQL (`.sql.gz`) | 24 Hours (Daily) | < 5 Minutes |
| **RAG Source Documents** | `data/documents/` (.pdf/.docx/.txt/.md) | Git / Persistent Volume Snapshot | Real-Time | < 5 Minutes |
| **FAISS Vector Index** | `data/index/*.faiss` | **Rebuild from Source Documents** (or tarball archive) | Rebuildable on demand | < 30 Seconds |

> [!IMPORTANT]
> **Why FAISS Rebuild is the Preferred Recovery Path**:
> FAISS vector indexes are tightly coupled to the embedding model weights (`multilingual-e5-small`) and chunking tokenizer. Binary index files can suffer cross-platform endianness or FAISS library version drift. Because all source files remain safely persisted in `data/documents/`, executing `python scripts/database/build_rag_index.py` completely eliminates synchronization drift and generates a fresh, optimized index directly from verified documents.

---

## 2. Standard Backup Procedures

### 2.1 Automated Nightly Backup
Backups run automatically via the scheduled GitHub Actions workflow or the production host crontab at 02:00 UTC. Backups are stored in `./backups/` with companion `.sha256` checksums.

### 2.2 Manual On-Demand Backup Execution
Run before applying database migrations, system upgrades, or significant model changes:

```bash
# Using POSIX bash script (Linux / Docker host):
bash scripts/database/backup.sh

# Or using cross-platform Python backup manager (Windows / Linux):
python scripts/database/backup_manager.py --action backup --db-type sqlite
```

### 2.3 Backup Integrity Verification
Always verify checksum and internal integrity before archiving:
```bash
# 1. Verify file hash
sha256sum -c backups/sqlite_backup_YYYYMMDD_HHMMSS.db.sha256

# 2. Verify internal SQLite table structure
sqlite3 backups/sqlite_backup_YYYYMMDD_HHMMSS.db "PRAGMA integrity_check;"
# Must output: ok
```

---

## 3. Disaster Recovery Procedures

### Scenario A: Restoring SQLite (Development / Single-Node)
1. **Stop the backend server**:
   ```bash
   # Kill running uvicorn instance
   # (or manage_task kill in Antigravity)
   ```
2. **Execute restoration**:
   ```bash
   # Via shell script:
   bash scripts/database/restore.sh --backup-file backups/sqlite_backup_YYYYMMDD_HHMMSS.db --db-type sqlite

   # Or via Python manager:
   python scripts/database/backup_manager.py --action restore --db-type sqlite --backup-file backups/sqlite_backup_YYYYMMDD_HHMMSS.db
   ```
3. **Verify restored database**:
   ```bash
   sqlite3 database/dev.db "SELECT count(*) FROM emotion_history;"
   ```
4. **Restart FastAPI backend**:
   ```bash
   python -m uvicorn src.backend.main:app --host 127.0.0.1 --port 8000
   ```

### Scenario B: Restoring PostgreSQL (Production)
1. **Locate valid backup archive**:
   ```bash
   ls -lt backups/postgres_*.sql.gz | head -n 1
   ```
2. **Execute restore into container**:
   ```bash
   # Verify checksum
   sha256sum -c backups/postgres_YYYYMMDD_HHMMSS.sql.gz.sha256

   # Restore into PostgreSQL service
   gunzip -c backups/postgres_YYYYMMDD_HHMMSS.sql.gz | docker compose -f docker-compose.prod.yml exec -T postgres psql -U senseai -d senseai
   ```
3. **Verify table counts**:
   ```bash
   docker compose -f docker-compose.prod.yml exec postgres psql -U senseai -d senseai -c "SELECT count(*) FROM emotion_history;"
   ```

### Scenario C: Rebuilding FAISS Index from Source Documents
If `data/index/index.faiss` is missing, corrupt, or throws dimension mismatch errors:
1. **Ensure source documents are present**:
   ```bash
   ls -lh data/documents/
   ```
2. **Trigger standalone index build**:
   ```bash
   python scripts/database/build_rag_index.py --docs-dir data/documents --output-dir data/index
   ```
3. **Verify new index files**:
   ```bash
   ls -lh data/index/
   # Must list index.faiss and chunks_metadata.json
   ```
4. **Reload retriever in running backend**:
   The backend auto-loads the index at startup, or run `check_health.py` to confirm retriever status:
   ```bash
   python monitoring/health-checks/check_health.py
   ```

---

## 4. Disaster Recovery Drill Schedule
- **Frequency**: Execute every 30 days on staging environment.
- **Verification**: Assert that `tests/integration/test_rag_pipeline.py` and `tests/unit/test_storage.py` pass cleanly against the restored environment.
