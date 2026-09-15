import os
import uuid

import pytest
import pytest_asyncio
from asyncpg import PostgresError
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.migrations.alembic_api import current_revision, upgrade_database
from app.migrations.schema_registry import load_target_metadata


def schema_connect_args(schema_name: str) -> dict:
    return {"server_settings": {"search_path": f'"{schema_name}",public'}}


@pytest_asyncio.fixture
async def postgresql_schema():
    database_url = os.getenv("SCANT_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("SCANT_TEST_POSTGRES_URL is not configured")
    schema_name = f"scant_migration_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    created = False
    try:
        try:
            async with admin_engine.begin() as connection:
                await connection.execute(CreateSchema(schema_name))
            created = True
        except (SQLAlchemyError, PostgresError, OSError):
            pytest.skip("configured PostgreSQL migration server is unavailable")
        yield database_url, schema_name
    finally:
        try:
            if created:
                async with admin_engine.begin() as connection:
                    await connection.execute(
                        DropSchema(schema_name, cascade=True, if_exists=True)
                    )
        finally:
            await admin_engine.dispose()


async def metadata_diff(database_url: str, schema_name: str):
    engine = create_async_engine(
        database_url,
        connect_args=schema_connect_args(schema_name),
    )
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: compare_metadata(
                    MigrationContext.configure(
                        sync_connection,
                        opts={"compare_type": True},
                    ),
                    load_target_metadata(),
                )
            )
    finally:
        await engine.dispose()


@pytest.mark.live
@pytest.mark.asyncio
async def test_postgresql_empty_schema_upgrades_to_exact_head(postgresql_schema):
    database_url, schema_name = postgresql_schema

    await upgrade_database(database_url, schema=schema_name)

    assert await current_revision(database_url, schema=schema_name) == "0003"
    assert await metadata_diff(database_url, schema_name) == []


@pytest.mark.live
@pytest.mark.asyncio
async def test_postgresql_legacy_upgrade_preserves_rows(postgresql_schema):
    database_url, schema_name = postgresql_schema
    await upgrade_database(database_url, "0001", schema=schema_name)
    engine = create_async_engine(
        database_url,
        connect_args=schema_connect_args(schema_name),
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """INSERT INTO users
                   (id, email, name, preferred_locale, theme, document_language,
                    plan, role, is_superuser, is_active, created_at, updated_at)
                   VALUES ('legacy-pg', 'legacy-pg@example.com', 'Legacy PG', 'vi',
                           'system', 'vi', 'free', 'user', false, true,
                           CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""
            )
        )
    await engine.dispose()

    await upgrade_database(database_url, schema=schema_name)

    engine = create_async_engine(
        database_url,
        connect_args=schema_connect_args(schema_name),
    )
    async with engine.connect() as connection:
        email = await connection.scalar(
            text("SELECT email FROM users WHERE id='legacy-pg'")
        )
    await engine.dispose()
    assert email == "legacy-pg@example.com"
    assert await current_revision(database_url, schema=schema_name) == "0003"
    assert await metadata_diff(database_url, schema_name) == []
