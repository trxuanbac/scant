import pytest
from httpx import AsyncClient
from app.services.usage.quota_engine import quota_engine, prompt_cache


def test_prompt_cache():
    p = "Tạo đề cương báo cáo tài chính"
    prompt_cache.set(prompt=p, system_prompt=None, task_type="OUTLINE", value={"status": "cached_ok"})
    cached = prompt_cache.get(prompt=p, system_prompt=None, task_type="OUTLINE")
    assert cached is not None
    assert cached["status"] == "cached_ok"


@pytest.mark.asyncio
async def test_quota_engine_and_budget_guard(db_session):
    user_id = "test-user-quota-01"

    # 1. Estimate workload
    est = quota_engine.estimate_workload("deep_research", num_sections=6, num_sources=5)
    assert est["expected_total_tokens"] > 10000
    assert est["estimated_cost_usd"] > 0.0

    # 2. Check budget guard with fresh quota
    allowed, msg, _ = await quota_engine.check_budget_guard(db_session, user_id, "deep_research")
    assert allowed is True

    # 3. Record high usage event
    await quota_engine.record_usage_event(
        db=db_session,
        user_id=user_id,
        project_id=None,
        task_type="AGENT_REASONING",
        provider="gemini",
        model="gemini-2.5-flash",
        input_tokens=950_000,
        output_tokens=100_000,
        cached_tokens=0,
        estimated_cost_usd=25.0,
        latency_ms=1200,
    )

    # 4. Budget guard should now block because cost exceeded $20 limit
    blocked, block_msg, _ = await quota_engine.check_budget_guard(db_session, user_id, "deep_research")
    assert blocked is False
    assert "Vượt quá hạn mức" in block_msg


@pytest.mark.asyncio
async def test_usage_api_endpoints(client: AsyncClient):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "saas_user@enterprise.com",
        "password": "Password123!",
        "name": "SaaS Executive"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Get Usage Summary
    summary_res = await client.get("/api/v1/usage/summary", headers=headers)
    assert summary_res.status_code == 200
    data = summary_res.json()
    assert "monthly_token_limit" in data
    assert "cost_usd_this_month" in data
    assert "remaining_budget_usd" in data

    # 2. Get Usage Events
    events_res = await client.get("/api/v1/usage/events", headers=headers)
    assert events_res.status_code == 200
    assert isinstance(events_res.json(), list)

    # 3. Workload Estimator API
    est_res = await client.get("/api/v1/usage/estimate-workload?job_type=auto_create&num_sections=4", headers=headers)
    assert est_res.status_code == 200
    assert "expected_total_tokens" in est_res.json()
