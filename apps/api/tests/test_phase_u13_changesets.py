import pytest
from httpx import AsyncClient
from app.services.changeset.changeset_service import changeset_service


def test_compute_diff_unit():
    before = "Doanh thu năm 2025 đạt 10 tỷ đồng"
    after = "Doanh thu năm 2026 đạt 15 tỷ đồng"
    diff = changeset_service.compute_diff(before, after)
    assert len(diff) > 0
    types = [d["type"] for d in diff]
    assert "unchanged" in types
    assert "removed" in types or "added" in types


@pytest.mark.asyncio
async def test_changeset_lifecycle_api(client: AsyncClient):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "reviewer@corp.com",
        "password": "Password123!",
        "name": "Reviewer"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_res = await client.post("/api/v1/projects", json={
        "name": "Dự án Đề xuất Thay đổi",
        "type": "business_report"
    }, headers=headers)
    project_id = proj_res.json()["id"]

    rep_res = await client.post("/api/v1/reports", json={
        "project_id": project_id,
        "title": "Báo cáo Đánh giá",
        "report_type": "business_report",
        "outline": [
            {"title": "1. Tổng kết", "level": 1, "position": 1, "children": []}
        ]
    }, headers=headers)
    report_id = rep_res.json()["id"]
    section_id = rep_res.json()["sections"][0]["id"]

    # 1. Create ChangeSet
    cs_res = await client.post("/api/v1/changesets", json={
        "report_id": report_id,
        "summary": "AI đề xuất tinh chỉnh số liệu doanh thu và kế hoạch",
        "changes": [
            {
                "section_id": section_id,
                "change_type": "replace",
                "description": "Cập nhật số liệu Q1/2026",
                "before_text": "Doanh thu Q1 đạt 5 tỷ",
                "after_text": "Doanh thu Q1 đạt 8.5 tỷ vượt chỉ tiêu 15%",
            }
        ]
    }, headers=headers)

    assert cs_res.status_code == 200
    cs_data = cs_res.json()
    assert cs_data["status"] == "pending"
    change_set_id = cs_data["id"]

    # 2. List ChangeSets for Report
    list_res = await client.get(f"/api/v1/changesets/report/{report_id}", headers=headers)
    assert list_res.status_code == 200
    cs_list = list_res.json()
    assert len(cs_list) == 1
    assert len(cs_list[0]["changes"]) == 1
    change_id = cs_list[0]["changes"][0]["id"]

    # 3. Accept Single Change
    acc_res = await client.post(f"/api/v1/changesets/changes/{change_id}/accept", headers=headers)
    assert acc_res.status_code == 200
    assert acc_res.json()["status"] == "accepted"

    # 4. Verify section updated in report
    rep_check = await client.get(f"/api/v1/reports/{report_id}", headers=headers)
    assert "8.5 tỷ" in rep_check.json()["sections"][0]["plain_text"]
