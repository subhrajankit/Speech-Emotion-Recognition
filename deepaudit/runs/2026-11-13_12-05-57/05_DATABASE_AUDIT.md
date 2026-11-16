# 05 — Database Audit

## Engine & config

- SQLAlchemy 2.x (`create_engine`), `DATABASE_URL` default `sqlite:///./database/dev.db`; PostgreSQL supported via URL swap (`database.py:24-49`). Sync sessions (`sessionmaker`) yielded via `get_db` / `get_db_session`.
- Alembic: `alembic.ini` + `alembic/env.py` reading `settings.DATABASE_URL`, `render_as_batch=True` for SQLite. Single migration `4acca05d22ce_001_initial_schema.py` — verified upgrade/downgrade/upgrade cycle by `tests/backend/test_database_crud.py::test_alembic_upgrade_downgrade_cycle`.
- **Runtime does NOT auto-migrate.** `main.py` lifespan does not run Alembic; `deployment/docker/entrypoint-backend.sh` runs `alembic upgrade head` only when `RUN_MIGRATIONS=true`. Fresh local checkout → empty DB → auth/history fail until manual `alembic upgrade head` (documented in SETUP.md).
- Live check this audit: `database/dev.db` contains all 7 tables + legacy `emotion_history` + `alembic_version`; **86 user rows** — real dev data exists.

## Schema (7 canonical tables, migration-verified)

| Table | PK | FKs | Notes |
|---|---|---|---|
| users | id str36 | — | username unique+index, scrypt hash, is_active |
| sessions | id str64 (`sess_*`) | user_id→users CASCADE | primary_language, timestamps |
| predictions | id str36 | session_id CASCADE, model_version_id SET NULL | audio_duration_ms, processing_time_ms, confidence, created_at idx |
| transcripts | id str36 | prediction_id CASCADE (unique), session_id CASCADE | text, language, script, mixed_language, audio_events JSON |
| emotion_results | id str36 | prediction_id CASCADE (unique), session_id CASCADE | primary_emotion, confidence, valence, arousal, raw_tags JSON |
| messages | id str36 | session_id CASCADE, prediction_id SET NULL | role, text, sources JSON |
| model_versions | id str36 | — | unique(engine,model_id,revision,decoder) |

Indexes on all FKs + created_at where queried; cascade deletes correct; `unique` on transcript/emotion per prediction prevents dup turns.

## Findings

1. **Fabricated metrics persisted as real** (`history_service.py:185-195`): `confidence=1.0` (or 0.8 for neutral) hardcoded; `valence`/`arousal` from static `_map_emotion_coords` lookup — NOT model outputs. Dashboard/history consumers will read invented values. **High.**
2. `emotion_results.confidence` NOT NULL but receives fabricated constant — schema implies measured confidence. Same finding.
3. `prediction.confidence` stores `speech_result.confidence` which is **always None** for both engines (SenseVoice: "does not provide calibrated confidence"; IndicConformer: None) — column permanently null in practice.
4. Legacy `emotion_history` table exists in dev.db alongside canonical schema; `database/migrations/001_create_emotion_history.py` and `database/schemas/001_emotion_history.sql` are manual duplicates outside Alembic — orphaned, two sources of truth.
5. Sync SQLAlchemy in async handlers — blocking but low-impact at this scale.
6. No audio blobs stored anywhere — zero-retention invariant holds (verified: no audio column; uploads processed in-memory only; TTS temp WAV deleted in `finally`).
7. No retention/TTL job, no soft-delete; purge is manual via DELETE /api/history.
8. `get_or_create_model_version` cache validates against current session each call — handles multi-DB/test isolation correctly.
9. Transactions: single `db.commit()` per turn — atomic across session+prediction+transcript+emotion+messages. Good.
10. `sessions.user_id` FK has `ondelete="CASCADE"` in DDL — user deletion cascades (no user-delete endpoint exists anyway).
