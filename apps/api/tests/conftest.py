from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import database
from app.core.database import get_db
from app.main import app
from support.background_tasks import BackgroundTaskTracker
from support.database import create_isolated_database
from support.network_guard import install_network_guard


def pytest_addoption(parser):
    group = parser.getgroup("scant-live")
    group.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run tests that require external network or configured services",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skipped = pytest.mark.skip(
        reason="live test disabled; rerun with --run-live and required services configured"
    )
    for item in items:
        if item.get_closest_marker("live") is not None:
            item.add_marker(skipped)


@pytest.fixture(autouse=True)
def preserve_app_dependency_overrides():
    original = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


@pytest.fixture
def dependency_override_scope():
    @contextmanager
    def apply_overrides(overrides):
        original = dict(app.dependency_overrides)
        app.dependency_overrides.update(overrides)
        try:
            yield
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original)

    return apply_overrides


@pytest.fixture(autouse=True)
def block_network_in_deterministic_tests(request, monkeypatch):
    is_live = request.node.get_closest_marker("live") is not None
    if is_live and request.config.getoption("--run-live"):
        return
    install_network_guard(monkeypatch)


@pytest_asyncio.fixture
async def test_session_factory(monkeypatch):
    async with create_isolated_database() as factory:
        monkeypatch.setattr(database, "AsyncSessionLocal", factory)
        monkeypatch.setattr(database, "async_session_maker", factory)
        yield factory


@pytest_asyncio.fixture
async def db_session(test_session_factory):
    async with test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_session_factory, dependency_override_scope):
    async def override_get_db():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    transport = ASGITransport(app=app)
    with dependency_override_scope({get_db: override_get_db}):
        async with AsyncClient(transport=transport, base_url="http://test") as api_client:
            yield api_client


@pytest_asyncio.fixture
async def background_task_tracker(monkeypatch, test_session_factory):
    from app.api.v1 import reports

    tracker = BackgroundTaskTracker()
    monkeypatch.setattr(
        reports,
        "asyncio",
        SimpleNamespace(create_task=tracker.create_task),
    )
    try:
        yield tracker
    finally:
        await tracker.close()


@pytest.fixture
def deterministic_ai_provider(monkeypatch):
    from app.services.ai.gemini_provider import GeminiProvider
    from app.services.ai.openai_provider import OpenAIProvider

    async def generate(
        self,
        prompt,
        system_prompt=None,
        model=None,
        temperature=0.7,
        max_tokens=4096,
        response_format=None,
    ):
        return GeminiProvider()._mock_academic_fallback(prompt, response_format)

    monkeypatch.setattr(GeminiProvider, "generate", generate)
    monkeypatch.setattr(OpenAIProvider, "generate", generate)
    return generate
