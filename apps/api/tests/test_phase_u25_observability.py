import pytest
from httpx import AsyncClient
from app.services.observability.structured_logger import structured_logger
from app.services.observability.metrics_collector import metrics_collector


def test_structured_logging():
    # 1. HTTP Log
    http_event = structured_logger.log_http_request(
        request_id="req-test-12345",
        method="POST",
        route="/api/v1/reports/auto-create",
        status_code=200,
        duration_ms=45,
        user_id="usr-99",
    )
    assert http_event["request_id"] == "req-test-12345"
    assert http_event["duration_ms"] == 45

    # 2. AI Trace Log
    ai_event = structured_logger.log_ai_trace(
        trace_id="tr-trace-987",
        task_type="SECTION_WRITING",
        provider="gemini",
        model="gemini-2.5-flash",
        latency_ms=210,
        tokens=1500,
        cost_usd=0.00035,
    )
    assert ai_event["trace_id"] == "tr-trace-987"
    assert ai_event["estimated_cost_usd"] == 0.00035


def test_metrics_telemetry():
    metrics_collector.reset()
    metrics_collector.record_http_request(30)
    metrics_collector.record_http_request(85)
    metrics_collector.record_http_request(120, status_code=500)
    metrics_collector.record_ai_request(240, success=True)
    metrics_collector.record_export(380)

    summary = metrics_collector.get_summary()
    assert "api_latency_p50_ms" in summary
    assert "ai_latency_p50_ms" in summary
    assert "ai_failure_rate_pct" in summary
    assert summary["http_total_requests"] == 3
    assert summary["http_error_count"] == 1
    assert summary["http_error_rate_pct"] == 33.33


@pytest.mark.asyncio
async def test_metrics_api(client: AsyncClient):
    metrics_collector.reset()
    await client.get("/api/v1/health")
    res = await client.get("/api/v1/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "api_latency_p50_ms" in data
    assert "database_latency_ms" in data
    assert data["http_total_requests"] >= 1
