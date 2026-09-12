from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.database import Base


TestSessionFactory = async_sessionmaker[AsyncSession]


@asynccontextmanager
async def create_isolated_database() -> AsyncIterator[TestSessionFactory]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    schema_created = False
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        schema_created = True
        yield factory
    finally:
        try:
            if schema_created:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()
