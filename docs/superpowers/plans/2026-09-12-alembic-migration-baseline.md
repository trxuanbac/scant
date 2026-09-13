# Alembic Migration Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace startup-time schema mutation with an audited Alembic chain that upgrades empty and known legacy SCANT databases without losing existing rows.

**Architecture:** A model registry loads every SQLAlchemy table before Alembic compares metadata. Revision `0001` represents the known 30-table legacy schema, and revision `0002` adds the current columns, admin/billing tables, claims/evidence/image tables, and workbook ledger. A bootstrap runner fingerprints unversioned databases, stamps only a recognized legacy or current shape, then upgrades; application startup either runs this runner in explicit development compatibility mode or verifies that production is already at head.

**Tech Stack:** Python 3.14, SQLAlchemy 2 async engines, Alembic, SQLite, PostgreSQL 16, pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-existing-function-completion-program-design.md` — Phase 0C.

## Global Constraints

- Do not drop application tables or columns while adopting the baseline.
- Preserve retired historical tables already represented by SQLAlchemy metadata.
- Reject an unversioned database whose tables or columns do not match a recognized SCANT shape; never stamp it optimistically.
- Keep SQLite local development and PostgreSQL production on the same Alembic revisions.
- Production API startup must not call `Base.metadata.create_all`, issue `ALTER TABLE`, or stamp a database.
- Preserve the existing working-tree product changes and stage only Phase 0C files or hunks.

---

### Task 1: Complete model registry and schema fingerprints

**Files:**

- Create: `apps/api/app/migrations/schema_registry.py`
- Create: `apps/api/tests/test_migration_schema_registry.py`

**Interfaces:**

- Produces: `load_target_metadata() -> MetaData`.
- Produces: `inspect_schema(connection: Connection) -> SchemaSnapshot` where `SchemaSnapshot.tables` maps table names to ordered column names.
- Produces: `classify_unversioned_schema(snapshot: SchemaSnapshot) -> Literal["empty", "legacy", "head", "unknown"]`.
- The legacy signature contains the 30 tables in the checked-in SQLite baseline and excludes the seven head-only tables: `admin_configuration`, `billing_payments`, `billing_subscriptions`, `claims`, `evidences`, `image_assets`, and `workbook_actions`.
- The legacy signature records the missing columns currently observed in `auth_accounts`, `sources`, `citations`, `automations`, and `automation_runs`; head requires every current metadata column.

- [x] **Step 1: Write failing registry tests**

```python
def test_target_metadata_registers_every_current_table():
    metadata = load_target_metadata()
    assert set(metadata.tables) >= {
        "users", "auth_accounts", "admin_configuration",
        "billing_payments", "billing_subscriptions", "claims",
        "evidences", "image_assets", "workbook_actions",
    }

def test_unknown_unversioned_schema_is_rejected():
    snapshot = SchemaSnapshot(tables={"users": ("id", "invented_column")})
    assert classify_unversioned_schema(snapshot) == "unknown"
```

- [x] **Step 2: Run the focused tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_migration_schema_registry.py`

Expected: collection fails because `app.migrations.schema_registry` does not exist.

- [x] **Step 3: Add the explicit registry and immutable signatures**

```python
@dataclass(frozen=True)
class SchemaSnapshot:
    tables: Mapping[str, tuple[str, ...]]

def load_target_metadata() -> MetaData:
    import app.models.entities
    import app.models.admin_billing
    import app.models.admin_configuration
    import app.models.workbook_action
    return Base.metadata
```

`classify_unversioned_schema` must compare table and column sets, ignore only `alembic_version` and SQLite internal tables, accept an empty database, and return `unknown` for extra or conflicting application columns.

- [x] **Step 4: Run registry tests and the model import smoke test**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_migration_schema_registry.py tests/test_shared_test_fixtures.py`

Expected: all pass with no network access.

- [x] **Step 5: Commit the registry**

```bash
git add apps/api/app/migrations/schema_registry.py apps/api/tests/test_migration_schema_registry.py
git commit -m "test: fingerprint migration schemas"
```

### Task 2: Alembic environment and two-revision baseline

**Files:**

- Modify: `apps/api/requirements.txt`
- Create: `apps/api/alembic.ini`
- Create: `apps/api/alembic/env.py`
- Create: `apps/api/alembic/script.py.mako`
- Create: `apps/api/alembic/versions/0001_legacy_baseline.py`
- Create: `apps/api/alembic/versions/0002_current_schema.py`
- Create: `apps/api/app/migrations/alembic_api.py`
- Create: `apps/api/tests/test_alembic_sqlite_matrix.py`

**Interfaces:**

- Alembic reads `DATABASE_URL` through `app.core.config.settings` and uses `async_engine_from_config` with `connection.run_sync`.
- `async upgrade_database(database_url: str, revision: str = "head") -> None` and `async current_revision(database_url: str) -> str | None` provide the low-level programmatic API used by tests and the guarded bootstrap runner.
- Revision `0001` creates the known legacy tables and columns on an empty database.
- Revision `0002` adds the 39 observed legacy-missing columns, creates the seven head-only tables, makes `billing_subscriptions.payment_id` nullable when upgrading a prerelease billing schema, creates the admin/workbook indexes, and invokes the existing quota backfill without resetting customized quota rows.

- [x] **Step 1: Add Alembic to requirements and install it in the project venv**

```text
alembic>=1.16.0,<2.0.0
```

Run: `cd apps/api && venv/bin/python -m pip install "alembic>=1.16.0,<2.0.0"`

- [x] **Step 2: Write failing empty/legacy/current SQLite matrix tests**

```python
@pytest.mark.asyncio
async def test_empty_sqlite_upgrades_to_exact_head(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'empty.sqlite'}"
    await upgrade_database(url)
    assert await current_revision(url) == head_revision()
    assert await metadata_diff(url) == []

@pytest.mark.asyncio
async def test_legacy_sqlite_upgrade_preserves_rows(legacy_database_url):
    await bootstrap_database(legacy_database_url)
    assert await scalar(legacy_database_url, "select count(*) from users") == 1
    assert await metadata_diff(legacy_database_url) == []
```

- [x] **Step 3: Run the matrix tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_alembic_sqlite_matrix.py`

Expected: failure because the Alembic configuration, revisions, and runner do not exist.

- [x] **Step 4: Configure the async Alembic environment**

`env.py` must set `target_metadata = load_target_metadata()`, enable `compare_type=True`, render batch operations for SQLite, and accept a programmatic URL through `config.attributes["database_url"]`. It must not import the FastAPI app or execute application lifespan code.

- [x] **Step 5: Generate and audit revision `0001`**

Build a temporary legacy `MetaData` from the immutable signature, autogenerate against an empty SQLite database, and check in explicit `op.create_table`, `op.create_index`, and foreign-key operations. The revision body must contain no `Base.metadata.create_all`, `drop_all`, raw interpolated identifiers, or runtime settings access.

- [x] **Step 6: Generate and audit revision `0002`**

Autogenerate from a database upgraded to `0001` against `load_target_metadata()`. Keep explicit operations for the five altered legacy tables and seven new tables. Reuse `upgrade_subscription_grants(connection)` and a transaction-safe quota backfill helper from `admin_console.py`; do not call the script's engine-owning `migrate()` function from a revision.

- [x] **Step 7: Run the SQLite migration matrix**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_alembic_sqlite_matrix.py tests/test_admin_migration.py tests/test_workbook_action_ledger.py`

Expected: empty, legacy, already-head, repeat-upgrade, prerelease billing, workbook persistence, and row-preservation cases all pass.

- [x] **Step 8: Commit the Alembic chain**

```bash
git add apps/api/requirements.txt apps/api/alembic.ini apps/api/alembic apps/api/app/migrations/alembic_api.py apps/api/tests/test_alembic_sqlite_matrix.py
git commit -m "feat: add audited Alembic baseline"
```

### Task 3: Safe bootstrap runner and legacy script bridge

**Files:**

- Create: `apps/api/app/migrations/runner.py`
- Modify: `apps/api/app/migrations/admin_console.py`
- Modify: `apps/api/app/migrations/workbook_actions.py`
- Create: `apps/api/tests/test_migration_runner.py`

**Interfaces:**

- Produces: `async bootstrap_database(database_url: str) -> MigrationResult`.
- Produces: `async assert_database_at_head(database_url: str) -> None`.
- Produces: `head_revision() -> str` and `async current_revision(database_url: str) -> str | None`.
- `MigrationResult` reports `initial_state`, `initial_revision`, `final_revision`, and `upgraded`; it contains no credentials.

- [x] **Step 1: Write failing bootstrap safety tests**

```python
@pytest.mark.asyncio
async def test_bootstrap_refuses_unknown_unversioned_database(tmp_path):
    url = await database_with_unknown_column(tmp_path)
    with pytest.raises(UnknownSchemaError, match="backup"):
        await bootstrap_database(url)

@pytest.mark.asyncio
async def test_bootstrap_is_repeatable_at_head(empty_database_url):
    first = await bootstrap_database(empty_database_url)
    second = await bootstrap_database(empty_database_url)
    assert first.final_revision == second.final_revision == head_revision()
    assert second.upgraded is False
```

- [x] **Step 2: Run runner tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_migration_runner.py`

Expected: import failure for `app.migrations.runner`.

- [x] **Step 3: Implement guarded stamp-and-upgrade behavior**

```python
async def bootstrap_database(database_url: str) -> MigrationResult:
    revision = await current_revision(database_url)
    if revision is not None:
        return await upgrade_database(database_url)
    state = await inspect_and_classify(database_url)
    if state == "empty":
        return await upgrade_database(database_url)
    if state == "legacy":
        await stamp_database(database_url, "0001")
        return await upgrade_database(database_url)
    if state == "head":
        await stamp_database(database_url, head_revision())
        return MigrationResult(
            initial_state="head",
            initial_revision=None,
            final_revision=head_revision(),
            upgraded=False,
        )
    raise UnknownSchemaError("Unrecognized database schema; back up and inspect it before migration.")
```

All Alembic command calls run in a worker thread so they do not nest event loops, and the URL is passed through Alembic config attributes rather than command-line text.

- [x] **Step 4: Bridge standalone scripts**

Keep reusable data/DDL helpers in `admin_console.py` for revision `0002`. Change both modules' CLI entry points to call `bootstrap_database(settings.DATABASE_URL)` and print only revision/state fields. This prevents standalone scripts and Alembic from evolving separate schemas.

- [x] **Step 5: Verify bootstrap, legacy scripts, and deterministic backend suite**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_migration_runner.py tests/test_admin_migration.py tests/test_workbook_action_ledger.py`

Then run: `cd apps/api && venv/bin/python -m pytest -q`

- [x] **Step 6: Commit the runner**

```bash
git add apps/api/app/migrations/runner.py apps/api/app/migrations/admin_console.py apps/api/app/migrations/workbook_actions.py apps/api/tests/test_migration_runner.py
git commit -m "feat: guard legacy database bootstrap"
```

### Task 4: Remove production startup mutation

**Files:**

- Modify: `apps/api/app/core/config.py`
- Modify: `apps/api/app/core/database.py`
- Modify: `apps/api/app/main.py`
- Modify: `.env.example`
- Create: `apps/api/Dockerfile`
- Modify: `docker-compose.yml`
- Create: `apps/api/tests/test_database_startup_policy.py`

**Interfaces:**

- Adds `AUTO_MIGRATE_DATABASE: bool = True` for local development compatibility.
- Production validation rejects `AUTO_MIGRATE_DATABASE=true`.
- `init_db()` calls `bootstrap_database` only when the flag is true; otherwise it calls `assert_database_at_head` and performs no DDL.

- [x] **Step 1: Write failing production startup policy tests**

```python
def test_production_rejects_startup_auto_migration():
    settings = Settings(
        ENVIRONMENT="production",
        AUTO_MIGRATE_DATABASE=True,
        DEBUG=False,
        JWT_SECRET="a-secure-production-secret-that-is-long-enough",
        CORS_ORIGINS=["https://app.example.com"],
        _env_file=None,
    )
    assert "AUTO_MIGRATE_DATABASE" in " ".join(settings.validate_production_safety())

@pytest.mark.asyncio
async def test_check_mode_performs_no_schema_mutation(monkeypatch):
    monkeypatch.setattr(settings, "AUTO_MIGRATE_DATABASE", False)
    await init_db()
    assert migration_spy.calls == ["assert_head"]
```

- [x] **Step 2: Run startup tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_database_startup_policy.py`

- [x] **Step 3: Replace `_sync_schema` with the migration policy**

Delete the SQLite PRAGMA/`ALTER TABLE` loop and its swallowed exceptions. `init_db` must delegate to the runner with `settings.DATABASE_URL`; it must never synthesize SQL from model column names.

- [x] **Step 4: Make deployment intent explicit**

Document `AUTO_MIGRATE_DATABASE=true` for local development and set `AUTO_MIGRATE_DATABASE=false` for the production API service. Add `apps/api/Dockerfile` with `/app` as its working directory and Alembic files copied beside the application. Add a one-shot Compose `migrate` service using the API image and command `alembic upgrade head`; configure the API with `depends_on.migrate.condition: service_completed_successfully`.

- [x] **Step 5: Verify startup policy and production configuration**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_database_startup_policy.py tests/test_production_security.py`

- [x] **Step 6: Commit startup policy**

```bash
git add apps/api/app/core/config.py apps/api/app/core/database.py apps/api/app/main.py apps/api/tests/test_database_startup_policy.py apps/api/Dockerfile .env.example docker-compose.yml
git commit -m "fix: stop production startup schema mutation"
```

### Task 5: SQLite/PostgreSQL matrix and operator documentation

**Files:**

- Create: `apps/api/tests/test_alembic_postgresql.py`
- Create: `apps/api/MIGRATIONS.md`
- Modify: `apps/api/TESTING.md`
- Modify: `docs/superpowers/plans/2026-09-12-alembic-migration-baseline.md`

**Interfaces:**

- PostgreSQL tests use `SCANT_TEST_POSTGRES_URL`; they are marked `live` and skip with an explicit reason when the variable or server is unavailable.
- Operator commands cover backup, inspect/current, bootstrap, upgrade, check-at-head, and recovery from an unknown fingerprint.

- [ ] **Step 1: Add PostgreSQL empty and legacy-upgrade tests**

The tests create a uniquely named temporary schema, set PostgreSQL `search_path` for the migration connection, run the same `0001 -> 0002` chain, compare metadata, verify preserved rows, and drop only that temporary schema in `finally`.

- [ ] **Step 2: Run SQLite and PostgreSQL migration gates**

Run deterministic SQLite gate:

```bash
cd apps/api
venv/bin/python -m pytest -q tests/test_migration_schema_registry.py tests/test_alembic_sqlite_matrix.py tests/test_migration_runner.py tests/test_database_startup_policy.py
```

Run PostgreSQL when configured:

```bash
cd apps/api
SCANT_TEST_POSTGRES_URL=postgresql+asyncpg://postgres:postgrespassword@localhost:5432/ai_report_studio_audit venv/bin/python -m pytest --run-live -q tests/test_alembic_postgresql.py
```

- [ ] **Step 3: Document safe operator workflow**

`MIGRATIONS.md` must state that unknown schemas are never stamped automatically, production requires a backup before bootstrap, and rollback uses a database restore because the adoption revisions do not drop user data automatically.

- [ ] **Step 4: Run final release evidence**

Run backend normal and reverse deterministic orders, frontend tests/typecheck/lint/build, Alembic `heads`, `history`, and `check` against a migrated temporary SQLite database.

- [ ] **Step 5: Record evidence and commit documentation**

```bash
git add apps/api/tests/test_alembic_postgresql.py apps/api/MIGRATIONS.md apps/api/TESTING.md docs/superpowers/plans/2026-09-12-alembic-migration-baseline.md
git commit -m "docs: record migration baseline verification"
```
