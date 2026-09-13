import pytest
import importlib
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.migrations.alembic_api import current_revision, upgrade_database
from app.migrations.runner import (
    DatabaseRevisionError,
    MigrationResult,
    UnknownSchemaError,
    assert_database_at_head,
    bootstrap_database,
    head_revision,
)
from app.models.admin_billing import Payment, Subscription
from app.models.admin_configuration import AdminConfiguration


def sqlite_url(path) -> str:
    return f"sqlite+aiosqlite:///{path}"


async def remove_version_table(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP TABLE alembic_version"))
    finally:
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_empty_database_is_repeatable(tmp_path):
    database_url = sqlite_url(tmp_path / "empty.sqlite")

    first = await bootstrap_database(database_url)
    second = await bootstrap_database(database_url)

    assert first.initial_state == "empty"
    assert first.initial_revision is None
    assert first.final_revision == head_revision() == "0002"
    assert first.upgraded is True
    assert second.initial_state == "versioned"
    assert second.initial_revision == "0002"
    assert second.final_revision == "0002"
    assert second.upgraded is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_stamps_legacy_then_preserves_rows(tmp_path):
    database_url = sqlite_url(tmp_path / "legacy.sqlite")
    await upgrade_database(database_url, "0001")
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """INSERT INTO users
                   (id, email, name, preferred_locale, theme, document_language,
                    plan, role, is_superuser, is_active, created_at, updated_at)
                   VALUES ('legacy', 'legacy@example.com', 'Legacy', 'vi',
                           'system', 'vi', 'free', 'user', 0, 1,
                           CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""
            )
        )
    await engine.dispose()
    await remove_version_table(database_url)

    result = await bootstrap_database(database_url)

    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        email = await connection.scalar(
            text("SELECT email FROM users WHERE id='legacy'")
        )
    await engine.dispose()
    assert result.initial_state == "legacy"
    assert result.final_revision == "0002"
    assert result.upgraded is True
    assert email == "legacy@example.com"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_stamps_unversioned_head_without_replaying_ddl(tmp_path):
    database_url = sqlite_url(tmp_path / "head.sqlite")
    await upgrade_database(database_url)
    await remove_version_table(database_url)

    result = await bootstrap_database(database_url)

    assert result.initial_state == "head"
    assert result.initial_revision is None
    assert result.final_revision == "0002"
    assert result.upgraded is False
    assert await current_revision(database_url) == "0002"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_refuses_unknown_unversioned_database(tmp_path):
    database_url = sqlite_url(tmp_path / "unknown.sqlite")
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.execute(
            text("CREATE TABLE users (id VARCHAR(36), invented_column TEXT)")
        )
    await engine.dispose()

    with pytest.raises(UnknownSchemaError, match="back up"):
        await bootstrap_database(database_url)

    assert await current_revision(database_url) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_assert_at_head_never_upgrades_old_revision(tmp_path):
    database_url = sqlite_url(tmp_path / "old.sqlite")
    await upgrade_database(database_url, "0001")

    with pytest.raises(DatabaseRevisionError, match="0001"):
        await assert_database_at_head(database_url)

    assert await current_revision(database_url) == "0001"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_assert_at_head_rejects_a_false_head_stamp(tmp_path):
    database_url = sqlite_url(tmp_path / "false-head.sqlite")
    await upgrade_database(database_url, "0001")
    from app.migrations.alembic_api import stamp_database

    await stamp_database(database_url, "0002")

    with pytest.raises(DatabaseRevisionError, match="schema shape"):
        await assert_database_at_head(database_url)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_adopts_exact_prerelease_admin_schema(tmp_path):
    database_url = sqlite_url(tmp_path / "prerelease-admin.sqlite")
    await upgrade_database(database_url, "0001")
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        for table in (
            Payment.__table__,
            Subscription.__table__,
            AdminConfiguration.__table__,
        ):
            await connection.run_sync(table.create)
    await engine.dispose()
    await remove_version_table(database_url)

    result = await bootstrap_database(database_url)

    assert result.initial_state == "legacy_prerelease_admin"
    assert result.final_revision == "0002"
    assert result.upgraded is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module_name",
    ["app.migrations.admin_console", "app.migrations.workbook_actions"],
)
async def test_legacy_cli_uses_guarded_runner_without_printing_url(
    module_name,
    monkeypatch,
    capsys,
):
    from app.core.config import settings
    import app.migrations.runner as runner

    database_url = "sqlite+aiosqlite:////tmp/private-name.sqlite"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    calls = []

    async def fake_bootstrap(received_url):
        calls.append(received_url)
        return MigrationResult("head", None, "0002", False)

    monkeypatch.setattr(runner, "bootstrap_database", fake_bootstrap)
    module = importlib.import_module(module_name)

    await module.main()

    assert calls == [database_url]
    assert database_url not in capsys.readouterr().out
