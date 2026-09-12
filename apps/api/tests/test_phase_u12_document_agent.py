import pytest
from httpx import AsyncClient
from app.services.agent.agent_tool_registry import agent_tool_registry


def test_agent_tool_registry():
    tools = agent_tool_registry.list_tools()
    assert len(tools) >= 10
    tool_names = [t.name for t in tools]
    assert "read_document" in tool_names
    assert "insert_table" in tool_names
    assert "insert_chart" in tool_names
    assert "run_fact_check" in tool_names

    schemas = agent_tool_registry.get_tool_schemas_for_ai()
    assert len(schemas) == len(tools)


@pytest.mark.live
@pytest.mark.asyncio
async def test_agent_execute_turn_api(client: AsyncClient):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "agentuser@corp.com",
        "password": "Password123!",
        "name": "Agent User"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Get Tools
    tools_res = await client.get("/api/v1/ai/agent/tools", headers=headers)
    assert tools_res.status_code == 200
    assert len(tools_res.json()) >= 10

    # 2. Create Project & Report
    proj_res = await client.post("/api/v1/projects", json={
        "name": "Dự án Khảo sát Chiến lược",
        "type": "business_report"
    }, headers=headers)
    project_id = proj_res.json()["id"]

    rep_res = await client.post("/api/v1/reports", json={
        "project_id": project_id,
        "title": "Báo cáo Chiến lược",
        "report_type": "business_report",
        "outline": [{"title": "1. Tổng quan", "level": 1, "position": 1, "children": []}]
    }, headers=headers)
    report_id = rep_res.json()["id"]

    # 3. Execute Turn
    turn_res = await client.post("/api/v1/ai/agent/execute-turn", json={
        "project_id": project_id,
        "report_id": report_id,
        "message": "Hãy thêm một chương mới về Đánh giá Rủi ro và chèn nội dung phân tích"
    }, headers=headers)

    assert turn_res.status_code == 200
    data = turn_res.json()
    assert "human_readable_activity" in data
    assert "message_to_user" in data
