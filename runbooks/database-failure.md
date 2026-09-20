# Runbook: Database Failure & Remediation

## Project: SenseAI Voice Assistant
**Target Systems**: SQLite (`database/dev.db`, local development) & PostgreSQL (production container/service)

---

## 1. Quick Severity & Triage Matrix

| Symptom Signature | Observed Error Message | Severity | Probable Root Cause | Immediate Action |
| :--- | :--- | :--- | :--- | :--- |
| **SQLite Concurrency Lock** | `sqlite3.OperationalError: database is locked` | **SEV-2** | Multiple threads/processes holding concurrent write transactions. | Check active connections; enable SQLite WAL mode (`PRAGMA journal_mode=WAL;`). |
| **SQLite File Corruption** | `sqlite3.DatabaseError: file is encrypted or is not a database` or disk I/O error | **SEV-1** | Abrupt power termination, ungraceful container kill, filesystem corruption. | Run `PRAGMA integrity_check;`, attempt `.recover`, or execute restore drill. |
| **Postgres Connection Refused** | `could not connect to server: Connection refused` (port 5432) | **SEV-1** | Postgres container exited, port binding issue, or host network down. | Check container status: `docker compose ps postgres`, inspect logs. |
| **Postgres Max Connections** | `FATAL: remaining connection slots are reserved for non-replication superuser connections` | **SEV-2** | Connection leak or unpooled connection storms. | Terminate idle connections, tune `max_connections` or connection pooling. |
| **Disk Space Saturation** | `No space left on device` / Write failure | **SEV-1** | Unpruned logs or uncompacted database WAL files. | Prune old backups with `prune_old_backups`, clear temp caches, expand volume. |

---

## 2. SQLite Troubleshooting & Recovery Workflows

### Scenario A: `database is locked`
**Symptoms**: FastAPI pipeline logs show `OperationalError: database is locked` when writing to `emotion_history`.
1. **Inspect locks**:
   Check if another process (e.g. background backup script or test runner) is holding the database:
   ```bash
   # On Linux/macOS:
   fuser database/dev.db
   lsof database/dev.db

   # On Windows (PowerShell):
   Get-Process | Where-Object { $_.Modules.FileName -like "*dev.db*" }
   ```
2. **Enable WAL Mode**:
   Write-Ahead Logging allows concurrent readers alongside a writer:
   ```bash
   sqlite3 database/dev.db "PRAGMA journal_mode=WAL;"
   sqlite3 database/dev.db "PRAGMA busy_timeout=5000;"
   ```
3. **Verify lock release**:
   ```bash
   sqlite3 database/dev.db "SELECT count(*) FROM emotion_history;"
   ```

### Scenario B: SQLite Corruption / Malformed Image
**Symptoms**: Application logs indicate `database disk image is malformed`.
1. **Audit integrity**:
   ```bash
   sqlite3 database/dev.db "PRAGMA integrity_check;"
   ```
2. **Attempt Online Emergency Dump & Recover**:
   If corrupt, attempt rebuilding a clean database from SQL dump:
   ```bash
   # Create emergency dump of readable records
   sqlite3 database/dev.db ".recover" > database/recovered.sql
   
   # Re-import into fresh database
   mv database/dev.db database/dev.db.corrupt_$(date +%Y%m%d_%H%M%S)
   sqlite3 database/dev.db < database/recovered.sql
   
   # Verify recovered database
   sqlite3 database/dev.db "PRAGMA integrity_check;"
   ```
3. **Fallback**: If `.recover` produces 0 rows, proceed to [runbooks/backup-restore.md](file:///d:/Capstone%20Project/NewSenseVoice/runbooks/backup-restore.md) to restore from the latest daily snapshot.

---

## 3. PostgreSQL Troubleshooting & Recovery Workflows

### Scenario A: PostgreSQL Service Unreachable
1. **Verify container status**:
   ```bash
   docker compose -f docker/docker-compose.yml ps postgres
   # or production
   docker compose -f docker-compose.prod.yml ps postgres
   ```
2. **Inspect crash logs**:
   ```bash
   docker compose -f docker-compose.prod.yml logs --tail 100 postgres
   ```
3. **Restart service**:
   ```bash
   docker compose -f docker-compose.prod.yml restart postgres
   ```
4. **Test direct connection**:
   ```bash
   docker compose -f docker-compose.prod.yml exec postgres psql -U senseai -d senseai -c "SELECT 1;"
   ```

### Scenario B: Connection Pool Exhaustion
1. **Identify long-running or idle connections**:
   ```sql
   SELECT pid, usename, client_addr, state, query_start, query 
   FROM pg_stat_activity 
   WHERE datname = 'senseai' AND state != 'idle';
   ```
2. **Terminate stuck connections**:
   ```sql
   SELECT pg_terminate_backend(pid) 
   FROM pg_stat_activity 
   WHERE datname = 'senseai' AND state = 'idle in transaction' 
     AND query_start < NOW() - INTERVAL '5 minutes';
   ```

---

## 4. Post-Incident Verification Checklist
- [ ] Database is accessible to FastAPI backend: `curl -s http://127.0.0.1:8000/health | jq .status` returns `"healthy"`.
- [ ] Test record can be written to `emotion_history`: run `python -m pytest tests/unit/test_storage.py`.
- [ ] Pre-incident safety snapshot archived for forensic root-cause analysis.
