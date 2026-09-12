import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_auth_and_project_flow(client: AsyncClient):
    # 1. Register User
    reg_payload = {
        "email": "student@university.edu.vn",
        "password": "SecurePassword123!",
        "name": "Nguyen Van A"
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 200
    reg_data = reg_res.json()
    assert "access_token" in reg_data
    assert reg_data["user"]["email"] == "student@university.edu.vn"
    token = reg_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get Me
    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["name"] == "Nguyen Van A"

    # 3. Create Project
    proj_payload = {
        "name": "Báo cáo bài tập lớn ASP.NET Core",
        "type": "academic",
        "description": "Xây dựng website bán hàng trực tuyến sử dụng ASP.NET Core MVC",
        "topic_details": {
            "topic_name": "Xây dựng website bán hàng ASP.NET Core",
            "subject": "Lập trình Web nâng cao",
            "student_name": "Nguyen Van A",
            "student_id": "20210001",
            "instructor": "TS. Tran Van B"
        }
    }
    create_res = await client.post("/api/v1/projects", json=proj_payload, headers=headers)
    assert create_res.status_code == 201
    proj_data = create_res.json()
    assert proj_data["name"] == proj_payload["name"]
    project_id = proj_data["id"]

    # 4. List Projects
    list_res = await client.get("/api/v1/projects", headers=headers)
    assert list_res.status_code == 200
    projects = list_res.json()
    assert len(projects) == 1
    assert projects[0]["id"] == project_id

    # 5. Get Project Detail
    detail_res = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == project_id
    assert detail_res.json()["topic_details_json"]["student_id"] == "20210001"
