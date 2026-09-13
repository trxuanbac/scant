"""Small async-safe API around Alembic commands."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine


API_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(database_url: str) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.attributes["database_url"] = database_url
    return config


async def upgrade_database(
    database_url: str,
    revision: str = "head",
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, revision)


async def stamp_database(database_url: str, revision: str) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.stamp, config, revision)


async def current_revision(database_url: str) -> str | None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: MigrationContext.configure(
                    sync_connection
                ).get_current_revision()
            )
    finally:
        await engine.dispose()
