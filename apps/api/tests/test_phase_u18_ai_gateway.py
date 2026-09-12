import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from app.core.config import Settings
from app.services.ai.gemini_provider import GeminiProvider
from app.services.ai.types import AIRequest, AITaskType, AIProviderType, AIResponse
from app.services.ai.model_router import model_router
from app.services.ai.gateway import ai_gateway
from app.services.editor.outline_service import outline_service
from app.services.observability.metrics_collector import metrics_collector
from app.schemas.ai import AnalyzeIntentRequest


@pytest_asyncio.fixture(autouse=True)
async def isolated_gateway_database(test_session_factory):
    yield


def test_model_router_resolutions():
    # Classification / Intent -> Fast cheap model
    route_class = model_router.resolve_route(
        AIRequest(task_type=AITaskType.CLASSIFICATION, prompt="Phân loại yêu cầu")
    )
    assert route_class.primary_model == "gemini-2.5-flash"
    assert route_class.fallback_model == "gpt-4o-mini"

    # Agent Reasoning -> Strong model
    route_agent = model_router.resolve_route(
        AIRequest(task_type=AITaskType.AGENT_REASONING, prompt="Lập kế hoạch phân tích đa bước")
    )
    assert route_agent.primary_provider == AIProviderType.GEMINI

    # Cost Calculation
    cost = model_router.calculate_cost("gemini-2.5-flash", prompt_tokens=1000, completion_tokens=500)
    assert cost > 0.0


@pytest.mark.asyncio
async def test_ai_gateway_execute_success(deterministic_ai_provider):
    metrics_collector.reset()
    req = AIRequest(
        task_type=AITaskType.SECTION_WRITING,
        prompt="Viết phần tổng quan dự án",
        temperature=0.3,
    )
    res = await ai_gateway.execute(req)
    assert isinstance(res, AIResponse)
    assert res.task_type == AITaskType.SECTION_WRITING
    assert res.usage.prompt_tokens > 0
    assert res.usage.completion_tokens > 0
    assert res.latency_ms >= 0
    assert res.failover_applied is False
    assert metrics_collector.get_summary()["ai_total_requests"] == 1


@pytest.mark.asyncio
async def test_ai_gateway_passes_max_tokens_to_provider():
    metrics_collector.reset()
    req = AIRequest(
        task_type=AITaskType.AGENT_REASONING,
        prompt="Trả lời ngắn",
        temperature=0.2,
        max_tokens=123,
    )

    with patch("app.services.ai.gemini_provider.GeminiProvider.generate", new_callable=AsyncMock) as generate:
        generate.return_value = {
            "text": "ok",
            "usage": {"prompt_tokens": 5, "completion_tokens": 1},
        }

        res = await ai_gateway.execute(req)

    assert res.text == "ok"
    assert generate.await_args.kwargs["max_tokens"] == 123


@pytest.mark.asyncio
async def test_ai_gateway_failover_mechanism(deterministic_ai_provider):
    req = AIRequest(
        task_type=AITaskType.FACT_CHECK,
        prompt="Kiểm tra thông tin doanh thu 500 tỷ",
        temperature=0.2,
    )

    # Mock primary provider failure so gateway automatically fails over to secondary
    with patch("app.services.ai.gemini_provider.GeminiProvider.generate", side_effect=Exception("Gemini 429 Rate Limit")):
        res = await ai_gateway.execute(req)
        assert res.failover_applied is True
        assert res.provider == "openai"
        assert res.model == "gpt-4o-mini"
        assert len(res.text) > 0


@pytest.mark.asyncio
async def test_outline_service_via_gateway(deterministic_ai_provider):
    res = await outline_service.analyze_intent(
        AnalyzeIntentRequest(user_prompt="Báo cáo kiểm toán bảo mật hệ thống ngân hàng số")
    )
    assert res.suggested_title is not None
    assert len(res.key_themes) > 0


def test_ai_offline_fallback_is_disabled_in_production():
    assert Settings(ENVIRONMENT="development", AI_RUNTIME_MODE="auto", _env_file=None).allow_ai_offline_fallback is True
    assert Settings(ENVIRONMENT="test", AI_RUNTIME_MODE="auto", _env_file=None).allow_ai_offline_fallback is True
    assert Settings(ENVIRONMENT="production", AI_RUNTIME_MODE="auto", _env_file=None).allow_ai_offline_fallback is False


@pytest.mark.asyncio
async def test_gemini_provider_without_key_fails_in_production(monkeypatch):
    production_settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        JWT_SECRET="real-production-secret-value-with-more-than-32-characters",
        CORS_ORIGINS=["https://app.example.com"],
        GEMINI_API_KEY="",
        AI_RUNTIME_MODE="auto",
        _env_file=None,
    )
    monkeypatch.setattr("app.services.ai.gemini_provider.settings", production_settings)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is required"):
        await GeminiProvider().generate("Viết phần mở đầu")
