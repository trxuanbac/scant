import asyncio
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
async def client():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with TestAsyncSession() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
    await asyncio.sleep(0.3)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.live
@pytest.mark.asyncio
async def test_full_autonomous_workspace_e2e_workflow(client: AsyncClient):
    """
    End-to-End Autonomous Workspace Scenario:
    1. Register & Auth
    2. One-Click Auto Report Generation
    3. Document Agent Turn Execution
    4. Review AI ChangeSet & Diff
    5. Accept AI Changes
    6. Verify Editor Data
    7. Export DOCX & PDF
    """
    # 1. Register & Auth
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "ceo@autonomous-enterprise.com",
        "password": "Password123!",
        "name": "CEO Executive"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. One-Click Auto Report Generation
    form_data = {
        "prompt": "Báo cáo Toàn cảnh Chiến lược Chuyển đổi Số và Tối ưu Chi phí Hoạt động Doanh nghiệp 2026"
    }
    auto_res = await client.post("/api/v1/reports/auto-create", data=form_data, headers=headers)
    assert auto_res.status_code == 200
    auto_data = auto_res.json()
    project_id = auto_data["project_id"]
    report_id = auto_data["report_id"]
    job_id = auto_data["job_id"]

    # Check Job
    job_res = await client.get(f"/api/v1/reports/jobs/{job_id}", headers=headers)
    assert job_res.status_code == 200

    # 3. Document Agent Execution
    agent_res = await client.post("/api/v1/ai/agent/execute-turn", json={
        "project_id": project_id,
        "report_id": report_id,
        "message": "Thêm mục Đánh giá rủi ro an ninh mạng"
    }, headers=headers)
    assert agent_res.status_code == 200
    assert "human_readable_activity" in agent_res.json()

    # 4. Review AI ChangeSet & Diff
    rep_info = await client.get(f"/api/v1/reports/{report_id}", headers=headers)
    sections = rep_info.json().get("sections", [])
    sec_id = sections[0]["id"] if sections else "00000000-0000-0000-0000-000000000000"

    cs_res = await client.post("/api/v1/changesets", json={
        "report_id": report_id,
        "summary": "AI đề xuất bổ sung lộ trình ROI 18 tháng",
        "changes": [
            {
                "section_id": sec_id,
                "change_type": "replace",
                "before_text": "Thời gian hoàn vốn dự kiến dài hạn.",
                "after_text": "Thời gian hoàn vốn dự kiến đạt 18 tháng với NPV dương 4.2 tỷ VNĐ.",
            }
        ]
    }, headers=headers)
    assert cs_res.status_code == 200
    change_set_id = cs_res.json()["id"]

    # 5. Accept AI Changes
    acc_res = await client.post(f"/api/v1/changesets/{change_set_id}/accept-all", headers=headers)
    assert acc_res.status_code == 200
    assert acc_res.json()["status"] == "accepted"

    # 6. Verify Report details
    rep_detail = await client.get(f"/api/v1/reports/{report_id}", headers=headers)
    assert rep_detail.status_code == 200

    # 7. Export DOCX
    docx_res = await client.post("/api/v1/exports/docx", json={
        "report_id": report_id,
        "theme": "modern_business",
        "include_cover": True,
        "include_toc": True
    }, headers=headers)
    assert docx_res.status_code == 200
    assert "download_url" in docx_res.json()
