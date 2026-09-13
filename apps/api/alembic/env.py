from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.migrations.schema_registry import load_target_metadata


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = config.attributes.get(
    "target_metadata_override",
    load_target_metadata(),
)


def database_url() -> str:
    return config.attributes.get("database_url", settings.DATABASE_URL)


def configure_context(connection=None) -> None:
    options = {
        "target_metadata": target_metadata,
        "compare_type": True,
        "render_as_batch": database_url().startswith("sqlite"),
    }
    if connection is None:
        context.configure(
            url=database_url(),
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            **options,
        )
    else:
        context.configure(connection=connection, **options)


def run_migrations_offline() -> None:
    configure_context()
    with context.begin_transaction():
        context.run_migrations()


def run_sync_migrations(connection) -> None:
    configure_context(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(run_sync_migrations)
    finally:
        await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
