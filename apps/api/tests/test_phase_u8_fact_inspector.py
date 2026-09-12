import pytest
from httpx import AsyncClient
from app.services.citations.fact_inspector import fact_inspector


@pytest.mark.asyncio
async def test_fact_inspector_unit(deterministic_ai_provider):
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


@pytest.mark.asyncio
async def test_fact_inspect_api(client: AsyncClient, deterministic_ai_provider):
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
