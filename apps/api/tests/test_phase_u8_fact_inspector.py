import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.main import app
from app.core.database import Base, get_db
from app.services.citations.fact_inspector import fact_inspector

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
async def test_fact_inspector_unit():
    sources = [
        {
            "title": "Báo cáo Doanh thu EV 2026",
            "summary": "Doanh số xe ô tô điện tại Việt Nam tăng trưởng 45% trong năm 2026 và đạt 70,000 xe."
        }
    ]
    text = "Theo số liệu thống kê, doanh số ô tô điện đạt mức tăng trưởng 45% trong năm 2026."

    res = await fact_inspector.inspect_facts(text=text, sources=sources)
    assert res is not None
    assert "overall_factual_score" in res
    assert "claims" in res


@pytest.mark.live
@pytest.mark.asyncio
async def test_fact_inspect_api(client: AsyncClient):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "fact_checker@corp.com",
        "password": "Password123!",
        "name": "Fact Checker"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_res = await client.post("/api/v1/projects", json={
        "name": "Báo cáo Kiểm tra Sự thật",
        "type": "research"
    }, headers=headers)
    project_id = proj_res.json()["id"]

    inspect_res = await client.post(
        f"/api/v1/ai/inspect-facts?project_id={project_id}&text=Thị+phần+năm+2026+đạt+70%",
        headers=headers
    )
    assert inspect_res.status_code == 200
    assert "claims" in inspect_res.json()
