from pathlib import Path
from datetime import datetime, timezone

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.schema import CreateTable
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.migrations.alembic_api import current_revision, upgrade_database
from app.migrations.schema_registry import (
    classify_unversioned_schema,
    inspect_schema,
    load_target_metadata,
)
from app.models.entities import User
from app.models.admin_billing import Payment, Subscription


ADMIN_INDEXES = {
    "ix_admin_users_created",
    "ix_admin_usage_user_date",
    "ix_admin_usage_date",
    "ix_admin_jobs_status_date",
    "ix_admin_jobs_project_date",
    "ix_admin_audit_target_date",
    "ix_admin_audit_date",
    "ix_admin_projects_user_date",
    "ix_admin_files_project",
    "ix_admin_payments_date",
}


def sqlite_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


async def read_schema(database_url: str):
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(inspect_schema)
    finally:
        await engine.dispose()


async def read_metadata_diff(database_url: str):
    engine = create_async_engine(database_url)
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_empty_sqlite_upgrades_to_exact_head(tmp_path):
    database_url = sqlite_url(tmp_path / "empty.sqlite")

    await upgrade_database(database_url)

    assert await current_revision(database_url) == "0002"
    assert classify_unversioned_schema(await read_schema(database_url)) == "head"
    assert await read_metadata_diff(database_url) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_legacy_revision_upgrades_without_losing_rows(tmp_path):
    database_url = sqlite_url(tmp_path / "legacy.sqlite")
    await upgrade_database(database_url, revision="0001")
    assert classify_unversioned_schema(await read_schema(database_url)) == "legacy"

    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            User(
                id="legacy-user",
                email="legacy@example.com",
                name="Legacy User",
            )
        )
        await session.commit()
    await engine.dispose()

    await upgrade_database(database_url)

    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = await session.scalar(
            select(User).where(User.id == "legacy-user")
        )
    await engine.dispose()

    assert user is not None
    assert user.email == "legacy@example.com"
    assert await current_revision(database_url) == "0002"
    assert classify_unversioned_schema(await read_schema(database_url)) == "head"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upgrade_is_repeatable_at_head(tmp_path):
    database_url = sqlite_url(tmp_path / "repeat.sqlite")

    await upgrade_database(database_url)
    await upgrade_database(database_url)

    assert await current_revision(database_url) == "0002"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_legacy_rows_receive_safe_defaults_and_quota_backfill(tmp_path):
    database_url = sqlite_url(tmp_path / "legacy-rows.sqlite")
    await upgrade_database(database_url, revision="0001")
    timestamp = datetime.now(timezone.utc).isoformat()
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        statements = [
            """INSERT INTO users
               (id, email, name, preferred_locale, theme, document_language,
                plan, role, is_superuser, is_active, created_at, updated_at)
               VALUES ('u1', 'u1@example.com', 'User', 'vi', 'system', 'vi',
                       'pro', 'user', 0, 1, :ts, :ts)""",
            """INSERT INTO ai_usage_events
               (id, user_id, task_type, provider, model, input_tokens,
                output_tokens, cached_tokens, total_tokens, estimated_cost_usd,
                latency_ms, status, created_at)
               VALUES ('usage1', 'u1', 'analysis', 'test', 'test', 20, 20, 2,
                       42, 0.1, 10, 'success', :ts)""",
            """INSERT INTO projects
               (id, user_id, name, type, settings_json, metadata_json,
                topic_details_json, created_at, updated_at)
               VALUES ('p1', 'u1', 'Project', 'data_analysis', '{}', '{}', '{}',
                       :ts, :ts)""",
            """INSERT INTO reports
               (id, project_id, title, report_type, quality_profile, status,
                revision, document_settings_json, created_at, updated_at)
               VALUES ('r1', 'p1', 'Report', 'data_analysis', 'data_analysis',
                       'draft', 1, '{}', :ts, :ts)""",
            """INSERT INTO report_sections
               (id, report_id, title, position, level, status, content_json,
                plain_text, word_count, structured_summary_json, created_at,
                updated_at)
               VALUES ('section1', 'r1', 'Section', 1, 1, 'draft', '{}', '', 0,
                       '{}', :ts, :ts)""",
            """INSERT INTO sources
               (id, project_id, title, accessed_date, source_type,
                reliability_score, metadata_json, created_at)
               VALUES ('source1', 'p1', 'Source', :ts, 'WEB_ARTICLE', 0.8,
                       '{}', :ts)""",
            """INSERT INTO citations
               (id, report_section_id, source_id, citation_style, citation_key,
                created_at)
               VALUES ('citation1', 'section1', 'source1', 'IEEE', '[1]', :ts)""",
            """INSERT INTO automations
               (id, project_id, user_id, name, trigger_type,
                report_title_pattern, export_formats_json, is_active,
                created_at, updated_at)
               VALUES ('automation1', 'p1', 'u1', 'Automation', 'manual',
                       'Report {date}', '[]', 1, :ts, :ts)""",
            """INSERT INTO automation_runs
               (id, automation_id, status, trigger_source, retry_count,
                log_messages_json, started_at)
               VALUES ('run1', 'automation1', 'queued', 'manual', 0, '[]', :ts)""",
        ]
        for statement in statements:
            await connection.execute(text(statement), {"ts": timestamp})
    await engine.dispose()

    await upgrade_database(database_url)

    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        source = (
            await connection.execute(
                text(
                    "SELECT language, access_status, verification_status, "
                    "verification_score, verification_details_json, "
                    "domain_trust, updated_at FROM sources WHERE id='source1'"
                )
            )
        ).one()
        citation = (
            await connection.execute(
                text(
                    "SELECT citation_number, verification_status, support_level "
                    "FROM citations WHERE id='citation1'"
                )
            )
        ).one()
        automation = (
            await connection.execute(
                text(
                    "SELECT timezone, source_type, source_config_json, "
                    "analysis_mode FROM automations WHERE id='automation1'"
                )
            )
        ).one()
        run = (
            await connection.execute(
                text(
                    "SELECT duration_ms, source_snapshot_json, output_files_json "
                    "FROM automation_runs WHERE id='run1'"
                )
            )
        ).one()
        quota = (
            await connection.execute(
                text(
                    "SELECT monthly_token_limit, tokens_used_this_month "
                    "FROM user_quotas WHERE user_id='u1'"
                )
            )
        ).one()
    await engine.dispose()

    assert tuple(source[:6]) == ("vi", "open", "UNVERIFIED", 0, "{}", "UNKNOWN")
    assert source.updated_at is not None
    assert tuple(citation) == (1, "VERIFIED", "STRONG")
    assert tuple(automation) == ("Asia/Ho_Chi_Minh", "file", "{}", "comprehensive")
    assert tuple(run) == (0, "{}", "[]")
    assert tuple(quota) == (2_500_000, 42)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_head_contains_admin_query_indexes(tmp_path):
    database_url = sqlite_url(tmp_path / "indexes.sqlite")
    await upgrade_database(database_url)
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            index_names = await connection.run_sync(
                lambda sync_connection: {
                    index["name"]
                    for table_name in inspect(sync_connection).get_table_names()
                    for index in inspect(sync_connection).get_indexes(table_name)
                }
            )
    finally:
        await engine.dispose()

    assert ADMIN_INDEXES <= index_names


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prerelease_billing_tables_upgrade_without_losing_payment(tmp_path):
    database_url = sqlite_url(tmp_path / "prerelease-billing.sqlite")
    await upgrade_database(database_url, revision="0001")
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Payment.__table__.create(sync_connection)
        )
        ddl = str(CreateTable(Subscription.__table__).compile(dialect=engine.dialect))
        ddl = ddl.replace(
            "payment_id VARCHAR(36)",
            "payment_id VARCHAR(36) NOT NULL",
        )
        await connection.execute(text(ddl))
        await connection.execute(
            text(
                """INSERT INTO users
                   (id, email, name, preferred_locale, theme, document_language,
                    plan, role, is_superuser, is_active, created_at, updated_at)
                   VALUES ('payer', 'payer@example.com', 'Payer', 'vi', 'system',
                           'vi', 'pro', 'user', 0, 1, CURRENT_TIMESTAMP,
                           CURRENT_TIMESTAMP)"""
            )
        )
        await connection.execute(
            text(
                """INSERT INTO billing_payments
                   (id, user_id, plan, amount, currency, status, provider,
                    provider_session_id, order_code, created_at)
                   VALUES ('paid', 'payer', 'pro', 100, 'VND', 'paid', 'test',
                           'session', 'order', CURRENT_TIMESTAMP)"""
            )
        )
        await connection.execute(
            text(
                """INSERT INTO billing_subscriptions
                   (id, user_id, plan, status, provider, payment_id, started_at)
                   VALUES ('original', 'payer', 'pro', 'active', 'test', 'paid',
                           CURRENT_TIMESTAMP)"""
            )
        )
    await engine.dispose()

    await upgrade_database(database_url)

    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        payment_id = await connection.scalar(
            text(
                "SELECT payment_id FROM billing_subscriptions "
                "WHERE id='original'"
            )
        )
        nullable = await connection.run_sync(
            lambda sync_connection: next(
                column["nullable"]
                for column in inspect(sync_connection).get_columns(
                    "billing_subscriptions"
                )
                if column["name"] == "payment_id"
            )
        )
    await engine.dispose()

    assert payment_id == "paid"
    assert nullable is True
    assert classify_unversioned_schema(await read_schema(database_url)) == "head"
