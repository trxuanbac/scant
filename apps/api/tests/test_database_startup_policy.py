from pathlib import Path

import pytest

from app.core.config import Settings, settings
from app.core.database import init_db


def production_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "JWT_SECRET": "a-secure-production-secret-that-is-long-enough",
        "CORS_ORIGINS": ["https://app.example.com"],
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_production_rejects_startup_auto_migration():
    configured = production_settings(AUTO_MIGRATE_DATABASE=True)

    errors = configured.validate_production_safety()

    assert any("AUTO_MIGRATE_DATABASE" in error for error in errors)


def test_production_accepts_check_only_database_startup():
    configured = production_settings(AUTO_MIGRATE_DATABASE=False)

    assert configured.validate_production_safety() == []


@pytest.mark.asyncio
async def test_local_init_delegates_to_guarded_bootstrap(monkeypatch):
    import app.migrations.runner as runner

    calls = []

    async def fake_bootstrap(database_url):
        calls.append(("bootstrap", database_url))

    async def unexpected_assert(_database_url):
        raise AssertionError("check-only path must not run")

    monkeypatch.setattr(settings, "AUTO_MIGRATE_DATABASE", True)
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///local.sqlite")
    monkeypatch.setattr(runner, "bootstrap_database", fake_bootstrap)
    monkeypatch.setattr(runner, "assert_database_at_head", unexpected_assert)

    await init_db()

    assert calls == [("bootstrap", "sqlite+aiosqlite:///local.sqlite")]


@pytest.mark.asyncio
async def test_check_mode_performs_no_schema_mutation(monkeypatch):
    import app.migrations.runner as runner

    calls = []

    async def unexpected_bootstrap(_database_url):
        raise AssertionError("migration path must not run")

    async def fake_assert(database_url):
        calls.append(("assert_head", database_url))

    monkeypatch.setattr(settings, "AUTO_MIGRATE_DATABASE", False)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://db/scant")
    monkeypatch.setattr(runner, "bootstrap_database", unexpected_bootstrap)
    monkeypatch.setattr(runner, "assert_database_at_head", fake_assert)

    await init_db()

    assert calls == [("assert_head", "postgresql+asyncpg://db/scant")]


def test_compose_runs_one_shot_migration_before_api():
    repository = Path(__file__).resolve().parents[3]
    compose = (repository / "docker-compose.yml").read_text()
    dockerfile = repository / "apps" / "api" / "Dockerfile"

    assert "  migrate:" in compose
    assert "alembic upgrade head" in compose
    assert "condition: service_completed_successfully" in compose
    assert "AUTO_MIGRATE_DATABASE=false" in compose
    assert dockerfile.is_file()
    image = dockerfile.read_text()
    assert "COPY apps/api/alembic.ini" in image
    assert "COPY apps/api/alembic" in image
