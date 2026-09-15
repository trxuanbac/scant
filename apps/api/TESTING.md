# Backend testing

The default suite is deterministic and rejects outbound TCP, DNS, and UDP access through Python sockets:

```bash
cd apps/api
venv/bin/python -m pytest -q
```

Run only live checks after configuring their required providers and services:

```bash
cd apps/api
venv/bin/python -m pytest --run-live -m live -q
```

Test classes:

- `unit`: pure deterministic logic.
- `integration`: deterministic application boundaries with isolated local dependencies.
- `browser`: browser tests against running SCANT processes.
- `live`: public network, configured provider, payment sandbox, or separately running service.

New tests are deterministic by default. A live marker must describe the real dependency in the test name or docstring. Do not use `live` to hide a product regression.

The socket guard catches application-level Python clients. CI also runs deterministic test and build commands in a Linux network namespace with no external interface, so subprocesses and native libraries cannot bypass this policy.

## CI release gates

`.github/workflows/ci.yml` runs on every push and pull request with read-only repository permission:

- `policy`: reject tracked credentials, environment files, databases, uploads, exports, and generated caches;
- `backend`: install dependencies, then run the full default pytest suite without external networking;
- `frontend`: run unit tests, typecheck, the lint error gate, and the production build without external networking;
- `migrations`: validate SQLite, PostgreSQL 16, the Alembic revision graph, and metadata drift.

Public-provider live tests remain manual. The PostgreSQL migration tests are the only live-marked tests enabled by the migration job, and they use the job's disposable local service.

## Current verification

Verified on 2026-09-15:

- Backend default suite: 343 passed, 12 live tests skipped, 0 failed; 170 existing deprecation warnings.
- Backend deterministic suite in reverse collection order: 343 passed, 12 live tests skipped, 0 failed; 170 existing deprecation warnings.
- Phase 1A source/scope/evidence gate: 104 focused tests passed. Stored files, direct uploads, and linked workbooks use the SHA-256 of the exact analyzed bytes; owner checks still hide foreign file IDs.
- Analysis preview, profile, sheet analysis, workbook chat, and deterministic actions expose an additive `analysis_context`. Dictionary evidence carries the same validated source version and workbook/sheets/sheet/range scope; legacy response fields remain available.
- Phase 1B durable-session gate: 49 focused schema, API, scope, and access-control tests passed, with 2 PostgreSQL tests skipped until the live gate. Authenticated chat/action exchanges restore with stable ordering; guests and failed analyses write no session rows; workbook actions reject foreign or stale session links.
- Alembic SQLite/revision `0003` gate: 21 passed and 2 live checks skipped by default across schema fingerprint, revision matrix, and guarded bootstrap; one head reported, and `alembic check` found no pending schema operations after upgrading a fresh SQLite database.
- Alembic PostgreSQL gate: 2 passed against PostgreSQL 16 in isolated temporary schemas, including fresh upgrade and legacy-row preservation through `0003`.
- Shared fixture stress run: four database/client modules collected twice in one process, 40 passed and 0 failed.
- Backend live collection: 12 live tests collected without executing them.
- Frontend unit suite: 95 passed, 0 failed, 0 skipped.
- TypeScript typecheck: passed.
- ESLint: passed with 0 errors and 51 existing warnings.
- Next.js production build: passed; Next.js reported the existing middleware convention deprecation warning.

The 12-test live collection includes two Alembic PostgreSQL checks. Configure `SCANT_TEST_POSTGRES_URL` and run them explicitly:

```bash
SCANT_TEST_POSTGRES_URL=postgresql+asyncpg://user:password@localhost:5432/database \
  venv/bin/python -m pytest --run-live -q tests/test_alembic_postgresql.py
```

Each migration test creates a uniquely named schema, runs the revision chain, and drops only that schema in teardown.

The remaining local test engines are intentional because their database or application topology is the subject of the test:

- `test_admin_billing_security.py` builds a minimal FastAPI app around billing routers and a controlled payment provider.
- `test_admin_migration.py` constructs incomplete and prerelease schemas to test additive migration behavior.
- `test_seed_sample.py` injects a standalone engine into the seed command to test repeated execution and repair.
- `test_workbook_action_ledger.py` uses file-backed databases to test migration and reopen persistence.
- `test_phase_u27_5_production_reality_audit.py` connects to the separately configured PostgreSQL audit database only when live tests are enabled.
