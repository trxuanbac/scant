import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_and_probes(client: AsyncClient):
    # 1. Health basic
    h_res = await client.get("/api/v1/health")
    assert h_res.status_code == 200
    assert h_res.json()["status"] == "healthy"

    # 2. Liveness probe
    live_res = await client.get("/api/v1/health/live")
    assert live_res.status_code == 200
    assert live_res.json()["status"] == "alive"

    # 3. Readiness probe
    ready_res = await client.get("/api/v1/health/ready")
    assert ready_res.status_code == 200
    assert ready_res.json()["status"] == "ready"
    assert ready_res.json()["database"] == "connected"
