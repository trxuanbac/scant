import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.main import app
from app.core.database import Base, get_db

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestAsyncSession = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestAsyncSession() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.live
@pytest.mark.asyncio
async def test_ai_analyze_intent_flow(client: AsyncClient):
    # 1. Register
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "strategist@corp.com",
        "password": "Password123!",
        "name": "David Tran"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Call analyze-intent
    prompt = "Phân tích thị trường xe điện Việt Nam năm 2026 và đề xuất chiến lược thâm nhập thị trường"
    analyze_res = await client.post("/api/v1/ai/analyze-intent", json={
        "user_prompt": prompt,
        "selected_type": "business_report"
    }, headers=headers)

    assert analyze_res.status_code == 200
    data = analyze_res.json()
    assert "suggested_title" in data
    assert "suggested_type" in data
    assert len(data["suggested_custom_fields"]) > 0
    assert len(data["key_themes"]) > 0
