import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_agentic_workflow_launch_and_poll(
    client: AsyncClient,
    deterministic_ai_provider,
    background_task_tracker,
):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "agentic_user@corp.com",
        "password": "Password123!",
        "name": "Agentic Lead"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_res = await client.post("/api/v1/projects", json={
        "name": "Báo cáo Toàn cầu 2026",
        "type": "business_report"
    }, headers=headers)
    project_id = proj_res.json()["id"]

    report_res = await client.post("/api/v1/reports", json={
        "project_id": project_id,
        "title": "Báo cáo Kinh doanh Toàn cầu",
        "report_type": "business_report",
        "outline": [
            {"title": "1. Tổng quan thị trường", "level": 1, "position": 1, "children": []},
            {"title": "2. Chiến lược tăng trưởng", "level": 1, "position": 2, "children": []}
        ]
    }, headers=headers)
    report_id = report_res.json()["id"]

    # Start Agentic Generation
    gen_res = await client.post(f"/api/v1/reports/{report_id}/generate-all", headers=headers)
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert "job_id" in gen_data
    job_id = gen_data["job_id"]

    # Poll Job Status
    poll_res = await client.get(f"/api/v1/reports/jobs/{job_id}", headers=headers)
    assert poll_res.status_code == 200
    poll_data = poll_res.json()
    assert "progress_percent" in poll_data
    assert poll_data["job_id"] == job_id
