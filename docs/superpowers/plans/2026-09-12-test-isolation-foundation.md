# Shared Backend Test Isolation Implementation Plan

**Goal:** Replace duplicated module-level SQLite engines and global FastAPI override cleanup with one function-scoped test harness, then prove database and application state do not leak between deterministic tests.

**Architecture:** `tests/support/database.py` owns creation and disposal of an isolated SQLite database. Root `tests/conftest.py` exposes a session factory, database session, and ASGI client from that harness and snapshots FastAPI dependency overrides around every test. Existing modules consume these fixtures instead of creating engines at import time. Provider fakes and process-singleton resets remain explicit fixtures so tests declare the state they depend on.

**Spec:** `docs/superpowers/specs/2026-09-11-existing-function-completion-program-design.md` — Phase 0B.

## Global constraints

- Do not change product runtime behavior.
- Every database engine created by the shared harness is function-scoped and disposed.
- A test must not clear dependency overrides installed by another fixture; restore the exact snapshot instead.
- Deterministic provider behavior is injected at the provider boundary, never by allowing network.
- Preserve pre-existing working-tree changes and stage only Phase 0B hunks.
- Keep specialized migration, PostgreSQL, persistence/reopen, and transaction fixtures local when their topology is part of the behavior under test.

### Task 1: Shared isolated database and ASGI client

**Files:**

- Create: `apps/api/tests/support/database.py`
- Modify: `apps/api/tests/conftest.py`
- Create: `apps/api/tests/test_shared_test_fixtures.py`

- [x] Write a failing test that imports `create_isolated_database`, opens two databases in sequence, writes a user into the first, and proves the second contains no users.
- [x] Add an async context manager that creates an in-memory SQLite engine, creates `Base.metadata`, yields its `async_sessionmaker`, then drops/disposes it in `finally`.
- [x] Add root `test_session_factory`, `db_session`, and `client` fixtures. The client uses `ASGITransport(app=app)` and a database dependency that yields the same function-scoped session.
- [x] Patch `app.core.database.AsyncSessionLocal` and `async_session_maker` to the function-scoped factory so runtime services that intentionally open their own session stay inside the test database.
- [x] Add an autouse fixture that snapshots `app.dependency_overrides` and restores that exact mapping after each test.
- [x] Verify fixture tests, auth/project integration tests, and the full deterministic suite.

### Task 2: Migrate the standard duplicated fixtures

**Files:** migrate only modules whose local topology is the standard `Base.metadata` + SQLite + `get_db` + `ASGITransport` pattern.

- `test_auth_and_projects.py`
- `test_e2e_autonomous_workflow.py`
- `test_final_product_completion.py`
- `test_phase1b_parsers_and_outline.py`
- `test_phase1c_research_and_citations.py`
- `test_phase1d_editor_and_export.py`
- `test_phase_l1_to_l20_launch_readiness.py`
- `test_phase_u10_document_transformation.py`
- `test_phase_u11_auto_report.py`
- `test_phase_u12_document_agent.py`
- `test_phase_u13_changesets.py`
- `test_phase_u15_template_marketplace.py`
- `test_phase_u17_data_connectors.py`
- `test_phase_u1_generic_metadata.py`
- `test_phase_u2_intent_and_wizard.py`
- `test_phase_u3_template_reverse_engineer.py`
- `test_phase_u4_knowledge_retrieval.py`
- `test_phase_u5_copilot.py`
- `test_phase_u7_data_analysis.py`
- `test_phase_u8_fact_inspector.py`
- `test_source_library_and_citations.py`

Additional standard fixtures found during migration were removed from admin, billing, quota, storage, observability, production-readiness, document-intelligence, and agentic-workflow modules.

- [x] Remove module-level engine/sessionmaker declarations and the duplicated `db_session`/`client` fixtures.
- [x] Remove imports that existed only for those fixtures; retain `AsyncClient`/`AsyncSession` when test annotations or bodies use them.
- [x] Migrate three representative modules first and run them before converting the rest.
- [x] Run every migrated module together and confirm live functions remain skipped by default.
- [x] Stage only the fixture-removal hunks in files that already contained unrelated edits.

### Task 3: Isolate global overrides and mutable singleton state

**Files:**

- Modify: `apps/api/tests/conftest.py`
- Modify: tests that currently call `app.dependency_overrides.clear()` outside the standard fixture pattern.
- Create or modify focused policy tests in `apps/api/tests/test_shared_test_fixtures.py`.

- [x] Prove a temporary dependency override is restored after its scope rather than clearing unrelated entries.
- [x] Replace remaining unconditional override clears with snapshot restoration or the shared client fixture.
- [x] Reset mutable process state only when a focused test demonstrates leakage; reverse-order execution exposed `task_queue`, whose tests now use independent queue instances.
- [x] Keep state reset rules visible in named fixtures; do not introspect and mutate arbitrary singleton attributes.

### Task 4: Convert local-behavior AI tests to deterministic provider fixtures

**Files:**

- Modify: `apps/api/tests/conftest.py`
- Modify: the Phase 0A live-marked AI test modules whose assertions concern local orchestration rather than provider availability.

- [x] Add an explicit `deterministic_ai_provider` fixture that patches Gemini/OpenAI `generate` methods with complete offline response payloads.
- [x] Remove `live` only from tests that declare this fixture and make no public-provider assertion.
- [x] Keep Crossref, arXiv, DOI/URL verification, public research flows, and real PostgreSQL checks live; test the PayOS signing/response contract with a fake request boundary.
- [x] Run converted tests with the Python network guard active and verify their assertions exercise application behavior.
- [x] Recount live collection and document why each remaining live test needs an external dependency.

### Task 5: Order and completion verification

**Files:**

- Modify: `apps/api/TESTING.md`
- Modify: this plan after evidence exists.

- [x] Run the deterministic backend suite in normal collection order.
- [x] Collect deterministic node IDs and run the same set in reverse order.
- [x] Run representative database/client modules twice in one command to expose retained module state.
- [x] Run frontend tests, typecheck, lint, and build.
- [x] Record exact passed/skipped/warning counts and remaining specialized local fixtures in `TESTING.md`.
