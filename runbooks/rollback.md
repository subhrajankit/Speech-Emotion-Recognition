# Runbook: Production Rollback Procedure

**Target System:** SenseAI Voice Assistant Production Deployment  
**Severity:** Critical (Emergency reversion of degraded or broken production release)  
**Last Updated:** Phase 12 Docker & Deployment

---

## 1. Rollback Triggers

Initiate this rollback procedure immediately if any of the following conditions occur post-deployment:
- **Health Check Failure**: `/health` reports `status: "degraded"` or fails continuously for > 2 minutes.
- **Latency SLA Breach**: End-to-end P95 turn latency exceeds 600ms (budget: 500ms) or TTFT exceeds 200ms across multiple requests.
- **ASR / Audio Pipeline Failure**: Synthesis or speech recognition error rate spikes > 1%.
- **Container Crash Loop**: Backend or LLM server exits repeatedly with exit codes 1 or 137.
- **Security Defect**: Immediate vulnerability or authentication bypass identified in release.

---

## 2. Emergency Rollback Execution Checklist

### Phase A: Stop Degraded Services
```bash
# 1. Stop active production containers gracefully
docker compose -f docker-compose.prod.yml down --timeout 15
```

### Phase B: Revert Git Release Tag
```bash
# 2. Identify previous known-good git tag or commit
git tag -l "v*" --sort=-v:refname

# 3. Checkout previous stable release (e.g. v0.11.0)
git checkout tags/v0.11.0
```

### Phase C: Revert Database Schema (If Migrated)
If the failed release introduced a database schema change:
```bash
# For SQLite dev/demo: restore pre-migration backup
cp database/backups/dev.db.pre-deploy database/dev.db

# For PostgreSQL: run downgrade script or restore pg_dump snapshot
# docker exec -i senseai-postgres-prod psql -U senseai -d senseai_prod < database/backups/pre_deploy_backup.sql
```

### Phase D: Revert Configuration (`.env`)
```bash
# Restore previous stable environment configuration
cp .env.backup .env
```

### Phase E: Rebuild & Restart Stable Stack
```bash
# Launch previous stable stack
docker compose -f docker-compose.prod.yml up -d --build

# Follow startup logs
docker compose -f docker-compose.prod.yml logs -f --tail=50
```

---

## 3. Post-Rollback Verification

Execute the health check audit script immediately following stack restart:

```bash
# 1. Execute automated operational health check
python monitoring/health-checks/check_health.py

# 2. Verify all models report READY
curl -s http://127.0.0.1:8000/health | jq .

# 3. Verify dual transport capabilities
curl -s http://127.0.0.1:8000/api/transport/capabilities | jq .

# 4. Perform single audio test utterance via WebSocket
# Verify response latency is within budget (< 500ms)
```

---

## 4. Post-Incident Requirements

1. **Do not redeploy failed commit** directly to production.
2. File an incident post-mortem documenting:
   - Specific failure symptoms and root cause.
   - Time to detect (TTD) and time to recover (TTR).
   - Missing unit or integration test that failed to catch the regression.
3. Add a reproducible regression test in `tests/` before attempting next release.
