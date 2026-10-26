# Legacy Test Suite

These tests were written for the original `src/` legacy tree (prior to the canonical `backend/app/` architecture migration).

- **Scope**: Covers legacy components (`src.backend.*`) including legacy models, security, database, and transport prototypes.
- **Maintenance Status**: Not maintained. Preserved strictly for historical and reference purposes.
- **Pass Guarantee**: No claim that these tests pass. They were written for the old tree and may require explicit mock mode or legacy environment configurations.
- **Execution**: Excluded from default canonical test runs via `--ignore=tests/legacy` in `pyproject.toml`.
