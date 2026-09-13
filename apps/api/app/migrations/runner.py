"""Guarded database adoption and migration policy."""

import argparse
import asyncio
from dataclasses import dataclass

from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine

from app.migrations.alembic_api import (
    alembic_config,
    current_revision,
    stamp_database,
    upgrade_database,
)
from app.migrations.schema_registry import (
    classify_unversioned_schema,
    inspect_schema,
    is_known_prerelease_admin_schema,
)


class UnknownSchemaError(RuntimeError):
    """Raised when an unversioned database is not a recognized SCANT shape."""


class DatabaseRevisionError(RuntimeError):
    """Raised when check-only startup finds a database outside exact head."""


@dataclass(frozen=True)
class MigrationResult:
    initial_state: str
    initial_revision: str | None
    final_revision: str
    upgraded: bool


def head_revision() -> str:
    config = alembic_config("sqlite+aiosqlite://")
    revision = ScriptDirectory.from_config(config).get_current_head()
    if revision is None:
        raise DatabaseRevisionError("Alembic has no head revision.")
    return revision


async def _schema_state(database_url: str) -> str:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            snapshot = await connection.run_sync(inspect_schema)
    finally:
        await engine.dispose()
    state = classify_unversioned_schema(snapshot)
    if state == "unknown" and is_known_prerelease_admin_schema(snapshot):
        return "legacy_prerelease_admin"
    return state


async def bootstrap_database(database_url: str) -> MigrationResult:
    """Adopt only known unversioned schemas, then upgrade to Alembic head."""
    target = head_revision()
    revision = await current_revision(database_url)
    if revision is not None:
        upgraded = revision != target
        if upgraded:
            await upgrade_database(database_url)
        return MigrationResult(
            initial_state="versioned",
            initial_revision=revision,
            final_revision=target,
            upgraded=upgraded,
        )

    state = await _schema_state(database_url)
    if state == "empty":
        await upgrade_database(database_url)
        return MigrationResult(state, None, target, True)
    if state == "legacy":
        await stamp_database(database_url, "0001")
        await upgrade_database(database_url)
        return MigrationResult(state, None, target, True)
    if state == "legacy_prerelease_admin":
        await stamp_database(database_url, "0001")
        await upgrade_database(database_url)
        return MigrationResult(state, None, target, True)
    if state == "head":
        await stamp_database(database_url, target)
        return MigrationResult(state, None, target, False)
    raise UnknownSchemaError(
        "Unrecognized database schema; back up and inspect it before migration."
    )


async def assert_database_at_head(database_url: str) -> None:
    """Verify the revision and schema shape without issuing schema changes."""
    expected = head_revision()
    revision = await current_revision(database_url)
    if revision != expected:
        raise DatabaseRevisionError(
            f"Database revision is {revision or 'unversioned'}, expected {expected}."
        )
    state = await _schema_state(database_url)
    if state != "head":
        raise DatabaseRevisionError(
            f"Database is stamped {expected}, but its schema shape is {state}."
        )


async def _run_cli(action: str) -> None:
    from app.core.config import settings

    if action == "check":
        await assert_database_at_head(settings.DATABASE_URL)
        print({"state": "head", "revision": head_revision()})
        return
    result = await bootstrap_database(settings.DATABASE_URL)
    print(
        {
            "initial_state": result.initial_state,
            "initial_revision": result.initial_revision,
            "final_revision": result.final_revision,
            "upgraded": result.upgraded,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="SCANT database migration guard")
    parser.add_argument("action", choices=("bootstrap", "check"))
    arguments = parser.parse_args()
    asyncio.run(_run_cli(arguments.action))


if __name__ == "__main__":
    main()
