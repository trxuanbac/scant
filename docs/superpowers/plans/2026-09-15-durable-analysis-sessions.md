# Durable Analysis Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist authenticated workbook analysis sessions, messages, findings, source versions, scopes, and workbook-action references so the same analysis can be restored across browsers and API restarts.

**Architecture:** Add three normalized tables and an optional session foreign key on the existing workbook action ledger through Alembic revision `0003`. A focused service owns authorization, conversation-key hashing, ordered message writes, finding extraction, and serialization; data routes call it after successful chat/action responses, while a dedicated read/update router exposes list, detail, scope update, finding acceptance, and archive operations. Persistence is additive for authenticated users; guest and legacy request behavior stays unchanged.

**Tech Stack:** FastAPI, SQLAlchemy 2 async ORM, Pydantic v2, Alembic, SQLite/PostgreSQL 16, pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-existing-function-completion-program-design.md` — Phase 1B.

## Global Constraints

- Every session, message, finding, and linked workbook action is owner-scoped through the authenticated user.
- Session identity includes exact `source_id`, `source_kind`, SHA-256 `source_version`, and validated scope from Phase 1A.
- Store structured responses and evidence; do not store workbook preview rows or duplicate source file bytes.
- Hash client conversation keys before persistence and never return the hash.
- Message sequence numbers are unique within one session and writes are serialized for concurrent requests.
- Guest requests remain deterministic and non-persistent.
- Schema changes are additive, upgrade from `0002` preserves rows, downgrade removes only Phase 1B objects, and Alembic metadata drift remains empty on SQLite and PostgreSQL 16.
- No browser-visible history panel is added here; restored-session UI belongs to Phase 1D.

---

### Task 1: Session models and Alembic revision 0003

**Files:**

- Create: `apps/api/app/models/analysis_session.py`
- Modify: `apps/api/app/models/workbook_action.py`
- Modify: `apps/api/app/migrations/schema_registry.py`
- Create: `apps/api/alembic/versions/0003_analysis_sessions.py`
- Modify: `apps/api/tests/test_migration_schema_registry.py`
- Modify: `apps/api/tests/test_migration_runner.py`
- Modify: `apps/api/tests/test_alembic_sqlite_matrix.py`
- Modify: `apps/api/tests/test_alembic_postgresql.py`

**Interfaces:**

- Produces: `AnalysisSession`, `AnalysisMessage`, and `AnalysisFinding` ORM models.
- `AnalysisSession` stores owner, source identity/version/display fields, the immutable `available_sheets_json` catalog, validated `scope_json`, hashed `client_key_hash`, title, status, and timestamps.
- `AnalysisMessage` stores session, monotonic `sequence`, role, content, structured `response_json`, and timestamp with a unique `(session_id, sequence)` constraint.
- `AnalysisFinding` stores session/message links, status, title, summary, `evidence_json`, `result_json`, `action_ids_json`, and timestamp.
- Adds nullable `WorkbookAction.analysis_session_id` with `ON DELETE SET NULL` and an index.

- [x] **Step 1: Write failing model and migration tests**

Assert the metadata has all columns, constraints, foreign keys, and owner/source indexes. Extend the SQLite revision matrix to require head `0003`, verify `0002 -> 0003` preserves a workbook action, verify downgrade to `0002`, and assert an empty schema upgrades without metadata drift. Extend PostgreSQL expectations from `0002` to `0003`.

- [x] **Step 2: Run migration tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_migration_schema_registry.py tests/test_migration_runner.py tests/test_alembic_sqlite_matrix.py tests/test_alembic_postgresql.py`

Expected: deterministic assertions fail because revision `0003` and the three models do not exist; PostgreSQL tests stay skipped without `--run-live`.

- [x] **Step 3: Implement models and additive migration**

Use 36-character UUID primary keys, timezone-aware timestamps, JSON columns with callable defaults, explicit status strings, foreign keys with the delete behavior above, and indexes for `(user_id, source_id, source_version, updated_at)` and `(session_id, created_at)`. Import the model in `load_target_metadata`, add the three tables to `HEAD_ONLY_TABLES`, and use `batch_alter_table` for the workbook action column/index/foreign key.

- [x] **Step 4: Verify SQLite model and migration gates**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_migration_schema_registry.py tests/test_migration_runner.py tests/test_alembic_sqlite_matrix.py tests/test_alembic_postgresql.py`

Expected: SQLite tests pass, PostgreSQL tests skip by default, Alembic reports one head `0003`, and metadata comparison is empty.

- [x] **Step 5: Commit schema increment**

```bash
git add apps/api/app/models/analysis_session.py apps/api/app/models/workbook_action.py apps/api/app/migrations/schema_registry.py apps/api/alembic/versions/0003_analysis_sessions.py apps/api/tests/test_migration_schema_registry.py apps/api/tests/test_migration_runner.py apps/api/tests/test_alembic_sqlite_matrix.py apps/api/tests/test_alembic_postgresql.py
git commit -m "feat: add durable analysis session schema"
```

### Task 2: Owner-scoped session service and API

**Files:**

- Create: `apps/api/app/services/data/analysis_session_service.py`
- Create: `apps/api/app/api/v1/analysis_sessions.py`
- Modify: `apps/api/app/api/v1/__init__.py`
- Create: `apps/api/tests/test_analysis_sessions.py`

**Interfaces:**

- Produces: `get_or_create_session(db, user, source_version, available_sheets, scope, client_key) -> AnalysisSession`.
- Produces: `record_exchange(db, session, question, response) -> tuple[AnalysisMessage, AnalysisMessage, AnalysisFinding | None]`.
- Produces authenticated endpoints: `GET /data/analysis-sessions`, `GET /data/analysis-sessions/{id}`, `PATCH /data/analysis-sessions/{id}/scope`, `POST /data/analysis-sessions/{id}/findings/{finding_id}/accept`, and `POST /data/analysis-sessions/{id}/archive`.
- Detail responses include session source/scope, ordered messages, findings, and linked workbook action IDs without preview/file blobs.

- [x] **Step 1: Write failing service/API tests**

Create two owners and two source versions. Assert creation/reuse by hashed conversation key, separation after a source version change, stable message order, deterministic finding extraction from dictionary evidence, list filtering by source ID/version, detail restoration, validated scope update, idempotent finding acceptance/archive, foreign-owner 404 responses, and absence of raw client keys and workbook preview blobs in serialized output.

- [x] **Step 2: Run tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_sessions.py`

Expected: collection fails because the session service and router do not exist.

- [x] **Step 3: Implement service and router**

Hash `client_key` with SHA-256, lock the owner row before selecting/creating or assigning the next sequence, persist the resolved source's immutable sheet catalog, validate stored scope through the Phase 1A contract, and return 404 for every missing/foreign resource. Create one proposed finding only when a response has dictionary evidence plus a non-empty numeric/structured result or `analysis_history_item`; greetings/help remain messages without findings. Serialize timestamps as ISO 8601 and expose no internal hash.

- [x] **Step 4: Run session and authorization tests**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_sessions.py tests/test_analysis_contracts.py tests/test_data_access_safety.py`

Expected: all tests pass; cross-owner list/detail/update/accept/archive access reveals no resource existence.

- [x] **Step 5: Commit service/API**

```bash
git add apps/api/app/services/data/analysis_session_service.py apps/api/app/api/v1/analysis_sessions.py apps/api/app/api/v1/__init__.py apps/api/tests/test_analysis_sessions.py
git commit -m "feat: add analysis session API"
```

### Task 3: Persist successful workbook exchanges and action references

**Files:**

- Modify: `apps/api/app/api/v1/data.py`
- Modify: `apps/api/app/api/v1/workbook_actions.py`
- Create: `apps/api/tests/test_analysis_session_flow.py`

**Interfaces:**

- Workbook chat/action responses gain additive `analysis_session_id` for authenticated users.
- Successful authenticated exchanges call `get_or_create_session` and `record_exchange` in the request transaction; provider/analysis failures write no partial exchange.
- Workbook action preview accepts optional `analysis_session_id`, validates ownership and matching source version, and stores the foreign key.
- Guest responses retain their current shape except for the already-added Phase 1A context and do not write session rows.

- [x] **Step 1: Write failing end-to-end persistence tests**

Post two chat requests with the same conversation key and assert one session with four ordered messages; post a deterministic analysis action and assert its finding contains the exact Phase 1A evidence/source/scope; change source bytes and assert a new session; send a failed request and assert no partial rows; verify guest calls create none; attach a workbook action and reject foreign-session or stale-source attachment.

- [x] **Step 2: Run flow tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_session_flow.py`

Expected: assertions fail because data routes do not persist exchanges or return a session ID.

- [x] **Step 3: Integrate persistence after successful analysis**

Use the raw client `conversation_id` only as input to the service hash. Bind source/scope first, persist the bound assistant response, then add `analysis_session_id` to the returned payload. Reuse the service's owner-scoped session lookup in workbook action preview and compare `session.source_version` with the resolved workbook SHA-256 before assigning the relation.

- [x] **Step 4: Run workbook and session regression gates**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_session_flow.py tests/test_analysis_sessions.py tests/test_analysis_evidence_api.py tests/test_workbook_action_ledger.py tests/test_excel_ai_workspace_upgrade.py tests/test_phase_u7_data_analysis.py`

Expected: all tests pass and existing request/response fields remain available.

- [x] **Step 5: Commit runtime persistence**

```bash
git add apps/api/app/api/v1/data.py apps/api/app/api/v1/workbook_actions.py apps/api/tests/test_analysis_session_flow.py
git commit -m "feat: persist workbook analysis exchanges"
```

### Task 4: Migration matrix, documentation, and phase verification

**Files:**

- Modify: `apps/api/MIGRATIONS.md`
- Modify: `apps/api/TESTING.md`
- Modify: `docs/superpowers/plans/2026-09-15-durable-analysis-sessions.md`

**Interfaces:**

- Documents revision `0003`, session retention behavior, guest limitation, and exact restore API.
- Records SQLite/PostgreSQL migration evidence plus complete backend/frontend regression totals.

- [x] **Step 1: Run SQLite and Alembic graph checks**

Run the complete deterministic migration gate, `venv/bin/alembic heads`, `venv/bin/alembic history`, and `venv/bin/alembic check` against a temporary SQLite database upgraded to head.

- [x] **Step 2: Run PostgreSQL 16 migration checks**

Start the existing Compose PostgreSQL service on an available host port, set `SCANT_TEST_POSTGRES_URL`, and run `venv/bin/python -m pytest --run-live -q tests/test_alembic_postgresql.py`. Stop the service after the test without removing its volume.

- [x] **Step 3: Run all release regressions**

Run the full backend suite in normal and reversed node-ID order, then run frontend test, typecheck, lint, and production build sequentially. Record exact pass/skip/warning totals; do not convert existing warnings into pass claims.

- [x] **Step 4: Update operator documentation**

Document that `0003` is additive, sessions persist only for authenticated analysis, source changes create a distinct session, guests retain browser-only state, and `/data/analysis-sessions` is the restore boundary. Mark every completed checkbox in this plan.

- [x] **Step 5: Final safety checks and commit**

Run `git diff --check` and `bash scripts/check-secrets.sh`, then commit only documentation/evidence files:

```bash
git add apps/api/MIGRATIONS.md apps/api/TESTING.md docs/superpowers/plans/2026-09-15-durable-analysis-sessions.md
git commit -m "docs: record durable session verification"
```
