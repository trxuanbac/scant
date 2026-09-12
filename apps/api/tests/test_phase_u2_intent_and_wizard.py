import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ai_analyze_intent_flow(client: AsyncClient, deterministic_ai_provider):
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
