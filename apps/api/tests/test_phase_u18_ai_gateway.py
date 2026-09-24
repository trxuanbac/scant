import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from app.core.config import Settings
from app.services.ai.gemini_provider import GeminiProvider
from app.services.ai.types import AIRequest, AITaskType, AIProviderType, AIResponse
from app.services.ai.model_router import model_router
from app.services.ai.gateway import ai_gateway
from app.services.editor.outline_service import outline_service
from app.services.editor.writing_engine import WritingEngine
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


def test_offline_fallback_classifies_market_research_from_user_topic():
    prompt = '''
Ý TƯỞNG CỦA NGƯỜI DÙNG:
"Phân tích thị trường xe điện Việt Nam năm 2026 và đề xuất chiến lược thâm nhập thị trường"

Hãy phân tích và trả về JSON cấu trúc theo đúng format yêu cầu.
'''

    payload = GeminiProvider()._mock_academic_fallback(prompt, "json")
    data = json.loads(payload["text"])

    assert data["suggested_type"] == "market_research"
    assert "xe điện Việt Nam" in data["suggested_title"]


def test_offline_fallback_respects_explicit_technical_type_for_crm_topic():
    prompt = '''
Ý TƯỞNG CỦA NGƯỜI DÙNG:
"Xây dựng hệ thống CRM quản lý khách hàng và phân quyền nội bộ"

DANH MỤC BAN ĐẦU (NẾU CÓ): technical

Hãy phân tích và trả về JSON cấu trúc theo đúng format yêu cầu.
'''

    payload = GeminiProvider()._mock_academic_fallback(prompt, "json")
    data = json.loads(payload["text"])

    assert data["suggested_type"] == "technical"


def test_offline_fallback_preserves_multiline_market_idea():
    prompt = '''
Ý TƯỞNG CỦA NGƯỜI DÙNG:
"Phân tích thị trường xe điện Việt Nam năm 2026
và đề xuất chiến lược thâm nhập cho phân khúc phổ thông"

DANH MỤC BAN ĐẦU (NẾU CÓ): market_research

Hãy phân tích và trả về JSON cấu trúc theo đúng format yêu cầu.
'''

    payload = GeminiProvider()._mock_academic_fallback(prompt, "json")
    data = json.loads(payload["text"])

    assert data["suggested_title"] == (
        "Phân tích thị trường xe điện Việt Nam năm 2026 "
        "và đề xuất chiến lược thâm nhập cho phân khúc phổ thông"
    )


def test_offline_fallback_builds_market_outline_without_software_chapters():
    prompt = '''
LOẠI TÀI LIỆU: MARKET_RESEARCH
TIÊU ĐỀ: Phân tích thị trường xe điện Việt Nam năm 2026
MÔ TẢ CHI TIẾT: Đánh giá thị trường và đề xuất chiến lược thâm nhập.
Hãy tạo cấu trúc đề cương hoàn chỉnh.
'''

    payload = GeminiProvider()._mock_academic_fallback(prompt, "json")
    data = json.loads(payload["text"])
    titles = " ".join(item["title"] for item in data["outline"])

    assert "THỊ TRƯỜNG" in titles
    assert "CHIẾN LƯỢC" in titles
    assert "KIẾN TRÚC PHẦN MỀM" not in titles


def test_offline_fallback_keeps_explicit_technical_outline_for_crm():
    prompt = '''
LOẠI TÀI LIỆU: TECHNICAL
TIÊU ĐỀ: Hệ thống CRM quản lý khách hàng
MÔ TẢ CHI TIẾT: Thiết kế phần mềm quản trị nội bộ.
Hãy tạo cấu trúc đề cương hoàn chỉnh.
'''

    payload = GeminiProvider()._mock_academic_fallback(prompt, "json")
    data = json.loads(payload["text"])
    titles = " ".join(item["title"] for item in data["outline"])

    assert "QUY MÔ VÀ XU HƯỚNG THỊ TRƯỜNG" not in titles
    assert "PHÂN TÍCH VÀ THIẾT KẾ HỆ THỐNG" in titles


def test_offline_grounded_section_uses_topic_evidence_and_stable_citation():
    prompt = '''
ĐỀ TÀI: Phân tích thị trường xe điện Việt Nam
MỤC ĐANG VIẾT: 2.1 Quy mô và xu hướng thị trường (Heading 2)
ĐỘ DÀI MỤC TIÊU: 220 từ

NGUỒN ĐƯỢC PHÉP DÙNG CHO RIÊNG MỤC NÀY:
[SRC:source-1] Báo cáo thị trường xe điện Việt Nam (Cơ quan A · 2025)
URL: https://example.org/report
Bằng chứng: Nhu cầu xe điện tăng cùng với quá trình mở rộng hạ tầng sạc tại các đô thị.
'''

    text = GeminiProvider()._mock_academic_fallback(prompt, None)["text"]

    assert "Phân tích thị trường xe điện Việt Nam" in text
    assert "[SRC:source-1]" in text
    assert "hạ tầng sạc" in text
    assert "ARM" not in text


def test_offline_grounded_section_does_not_create_unsupported_year_or_excerpt_claims():
    prompt = '''
ĐỀ TÀI: Phân tích thị trường xe điện Việt Nam năm 2026
MỤC ĐANG VIẾT: 2.1 Quy mô và xu hướng thị trường (Heading 2)
ĐỘ DÀI MỤC TIÊU: 220 từ

NGUỒN ĐƯỢC PHÉP DÙNG CHO RIÊNG MỤC NÀY:
[SRC:source-1] Báo cáo thị trường xe điện Việt Nam 2025
URL: https://example.org/report
Bằng chứng: Năm 2025, thị trường tăng 20%. Hạ tầng sạc được mở rộng tại các đô thị.
'''

    text = GeminiProvider()._mock_academic_fallback(prompt, None)["text"]

    assert WritingEngine._unsupported_specific_claims(text, {"source-1"}) == []
    assert text.count("[SRC:source-1]") >= 2


def test_offline_grounded_section_reaches_requested_length():
    prompt = '''
ĐỀ TÀI: Phân tích thị trường xe điện Việt Nam
MỤC ĐANG VIẾT: 2.1 Quy mô và xu hướng thị trường (Heading 2)
ĐỘ DÀI MỤC TIÊU: 900 từ

NGUỒN ĐƯỢC PHÉP DÙNG CHO RIÊNG MỤC NÀY:
[SRC:source-1] Báo cáo thị trường xe điện Việt Nam
URL: https://example.org/report
Bằng chứng: Nhu cầu xe điện tăng cùng với quá trình mở rộng hạ tầng sạc tại các đô thị.
'''

    text = GeminiProvider()._mock_academic_fallback(prompt, None)["text"]

    assert len(text.split()) >= 900


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
