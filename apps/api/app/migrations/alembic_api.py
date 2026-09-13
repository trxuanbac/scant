"""Small async-safe API around Alembic commands."""

import asyncio
from pathlib import Path
import re

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine


API_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def database_connect_args(schema: str | None = None) -> dict:
    if schema is None:
        return {}
    if not SCHEMA_NAME.fullmatch(schema):
        raise ValueError("PostgreSQL schema name contains unsupported characters.")
    return {"server_settings": {"search_path": f'"{schema}",public'}}


def alembic_config(database_url: str, schema: str | None = None) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.attributes["database_url"] = database_url
    config.attributes["connect_args"] = database_connect_args(schema)
    return config


async def upgrade_database(
    database_url: str,
    revision: str = "head",
    *,
    schema: str | None = None,
) -> None:
    config = alembic_config(database_url, schema)
    await asyncio.to_thread(command.upgrade, config, revision)


async def stamp_database(
    database_url: str,
    revision: str,
    *,
    schema: str | None = None,
) -> None:
    config = alembic_config(database_url, schema)
    await asyncio.to_thread(command.stamp, config, revision)


async def current_revision(
    database_url: str,
    *,
    schema: str | None = None,
) -> str | None:
    engine = create_async_engine(
        database_url,
        connect_args=database_connect_args(schema),
    )
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: MigrationContext.configure(
                    sync_connection
                ).get_current_revision()
            )
    finally:
        await engine.dispose()
