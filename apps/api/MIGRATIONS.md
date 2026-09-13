# Database migrations

SCANT uses Alembic for SQLite development databases and PostgreSQL production databases. The current head is `0002`. Production API startup is check-only: migration runs as a separate deployment step before the API starts.

## Before every production migration

Stop writers and create a database backup. Keep the backup until application validation is complete.

PostgreSQL example:

```bash
pg_dump --format=custom --file=scant-before-migration.dump "$DATABASE_URL"
```

SQLite example:

```bash
sqlite3 storage/ai_report_studio.db ".backup 'scant-before-migration.sqlite'"
```

Never put a database URL or password in source control, shell history, tickets, or migration logs.

## Inspect the migration state

Run these commands from `apps/api` with `DATABASE_URL` configured:

```bash
venv/bin/alembic heads
venv/bin/alembic history
venv/bin/alembic current
```

`alembic current` prints nothing for an unversioned database. Do not stamp it manually.

## Adopt an existing database once

The guarded bootstrap command fingerprints an unversioned database before it stamps anything:

```bash
venv/bin/python -m app.migrations.runner bootstrap
```

It accepts only these exact shapes:

- an empty database;
- the known 30-table legacy schema;
- the legacy schema plus the former admin/billing tables;
- the complete current schema.

The command aborts on extra tables, missing tables, or conflicting columns and asks for a backup and inspection. An unknown schema is never stamped automatically.

## Apply and verify a normal upgrade

After the one-time adoption, use Alembic directly:

```bash
venv/bin/alembic upgrade head
venv/bin/python -m app.migrations.runner check
```

For local development, `AUTO_MIGRATE_DATABASE=true` lets startup call the guarded bootstrap. Production must set `AUTO_MIGRATE_DATABASE=false`. Docker Compose runs `alembic upgrade head` in the one-shot `migrate` service and starts the API only after that service succeeds.

## Recover from a failed or unknown migration

Do not use `alembic stamp` to bypass an unknown fingerprint. Stop the API, retain the failed database for inspection, and restore the pre-migration backup to a separate database. Compare its tables and columns with the checked-in revisions, then add a reviewed revision for that exact shape.

Rollback for the adoption baseline uses database restore. Do not run `alembic downgrade` on production data: reversing the baseline removes columns and tables introduced by the adoption revisions.

After restore or repair, run:

```bash
venv/bin/alembic current
venv/bin/python -m app.migrations.runner check
```

Start the API only after the check succeeds.
