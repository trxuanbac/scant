import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.main import app
from app.core.database import Base, get_db
from app.schemas.ai import CopilotMessageRequest
from app.services.ai.copilot_service import copilot_service

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
async def test_copilot_chat_flow(client: AsyncClient):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "director@corp.com",
        "password": "Password123!",
        "name": "Director Lee"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_res = await client.post("/api/v1/projects", json={
        "name": "Kế hoạch Tài chính Q1/2026",
        "type": "financial"
    }, headers=headers)
    project_id = proj_res.json()["id"]

    # Send copilot chat
    copilot_res = await client.post("/api/v1/ai/copilot", json={
        "project_id": project_id,
        "message": "Tạo Executive Summary tóm tắt tình hình tài chính quý 1"
    }, headers=headers)

    assert copilot_res.status_code == 200
    data = copilot_res.json()
    assert "reply" in data
    assert len(data["reply"]) > 0


@pytest.mark.asyncio
async def test_copilot_small_talk_does_not_create_document_action():
    res = await copilot_service.chat(
        req=CopilotMessageRequest(project_id="project-1", message="xin chào"),
        project_metadata={
            "project_name": "So sánh kiến trúc ARM và x86",
            "report_title": "So sánh kiến trúc ARM và x86",
        },
        knowledge_docs=[],
        sources=[],
    )

    assert "Chào" in res.reply
    assert res.action_type is None
    assert res.payload is None


@pytest.mark.asyncio
async def test_copilot_answers_current_topic_directly():
    res = await copilot_service.chat(
        req=CopilotMessageRequest(project_id="project-1", message="đề tài của tôi là gì?"),
        project_metadata={
            "project_name": "So sánh kiến trúc ARM và x86 trong hệ thống máy tính hiện đại",
            "project_description": "Báo cáo học thuật về kiến trúc hệ thống máy tính.",
            "report_title": "So sánh kiến trúc ARM và x86 trong hệ thống máy tính hiện đại",
            "topic_details": {},
        },
        knowledge_docs=[],
        sources=[],
    )

    assert "So sánh kiến trúc ARM và x86" in res.reply
    assert "Báo cáo học thuật" in res.reply
    assert res.action_type is None
