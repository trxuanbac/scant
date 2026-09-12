from sqlalchemy import select

import pytest

from app.main import app
from app.services.ai.gemini_provider import GeminiProvider
from app.models.entities import User
from support.database import create_isolated_database


@pytest.mark.integration
@pytest.mark.asyncio
async def test_isolated_database_contexts_do_not_share_rows():
    async with create_isolated_database() as first_factory:
        async with first_factory() as session:
            session.add(
                User(
                    id="isolated-user",
                    email="isolated@example.test",
                    name="Isolated User",
                    password_hash="unused",
                )
            )
            await session.commit()

    async with create_isolated_database() as second_factory:
        async with second_factory() as session:
            users = (await session.scalars(select(User))).all()

    assert users == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_shared_client_and_session_use_the_same_database(client, db_session):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "shared-fixture@example.com",
            "password": "SecurePassword123!",
            "name": "Shared Fixture",
        },
    )

    assert response.status_code == 200
    user = await db_session.scalar(
        select(User).where(User.email == "shared-fixture@example.com")
    )
    assert user is not None


@pytest.mark.unit
def test_dependency_override_scope_restores_the_exact_mapping(
    dependency_override_scope,
):
    def existing_dependency():
        return "existing"

    def existing_override():
        return "existing override"

    def temporary_dependency():
        return "temporary"

    def temporary_override():
        return "temporary override"

    app.dependency_overrides.clear()
    app.dependency_overrides[existing_dependency] = existing_override

    with dependency_override_scope(
        {temporary_dependency: temporary_override}
    ):
        assert app.dependency_overrides == {
            existing_dependency: existing_override,
            temporary_dependency: temporary_override,
        }

    assert app.dependency_overrides == {
        existing_dependency: existing_override,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deterministic_ai_provider_returns_an_offline_payload(
    deterministic_ai_provider,
):
    response = await GeminiProvider().generate("Viết phần mở đầu ngắn")

    assert response["text"]
    assert response["provider"] == "gemini"
    assert response["is_demo"] is True
