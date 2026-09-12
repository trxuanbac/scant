import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.main import app
from app.core.database import Base, get_db
from app.services.editor.document_transformer import document_transformer

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
async def test_document_transformation_unit():
    full_text = (
        "Thị trường xe điện tại Việt Nam tăng trưởng 45% trong năm 2026. "
        "Chiến lược của chúng tôi tập trung vào mở rộng trạm sạc nhanh tại các đô thị loại 2 và chính sách giá ưu đãi."
    )
    res = await document_transformer.transform(
        title="Báo cáo Xe Điện 2026",
        full_text=full_text,
        target_format="presentation_slides"
    )
    assert res["target_format"] == "presentation_slides"
    assert "formatted_title" in res
    assert len(res["content"]) > 0


@pytest.mark.live
@pytest.mark.asyncio
async def test_transform_document_api(client: AsyncClient):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "presenter@corp.com",
        "password": "Password123!",
        "name": "Presenter"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_res = await client.post("/api/v1/projects", json={
        "name": "Báo cáo Chuyển đổi Số",
        "type": "business_report"
    }, headers=headers)
    project_id = proj_res.json()["id"]

    report_res = await client.post("/api/v1/reports", json={
        "project_id": project_id,
        "title": "Báo cáo Chuyển đổi Số",
        "report_type": "business_report",
        "outline": [
            {"title": "1. Thực trạng", "level": 1, "position": 1, "children": []}
        ]
    }, headers=headers)
    report_id = report_res.json()["id"]

    trans_res = await client.post(
        f"/api/v1/ai/transform-document?report_id={report_id}&target_format=executive_summary",
        headers=headers
    )
    assert trans_res.status_code == 200
    assert trans_res.json()["target_format"] == "executive_summary"
