import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import database
from app.core.database import get_db
from app.main import app
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
async def client(test_session_factory):
    async def override_get_db():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as api_client:
        yield api_client
