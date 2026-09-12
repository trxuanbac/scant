import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.citations.doi_arxiv_resolver import doi_arxiv_resolver
from app.services.quality.plagiarism_stylometry_engine import plagiarism_stylometry_engine
from app.services.billing.billing_provider import billing_provider
from app.services.automation.bulk_report_service import bulk_report_service
from app.services.visuals.diagram_agent import visual_diagram_agent, DiagramType


@pytest.mark.asyncio
async def test_stylometry_and_humanize_engine():
    sample_text = (
        "Hơn nữa, trong bối cảnh hiện nay, việc chuyển đổi số đóng vai trò then chốt. "
        "Ngoài ra, các doanh nghiệp cần đầu tư vào trí tuệ nhân tạo một cách toàn diện. "
        "Tóm lại, điều quan trọng cần lưu ý là công nghệ sẽ quyết định lợi thế cạnh tranh."
    )
    res = await plagiarism_stylometry_engine.analyze(sample_text)
    assert "human_probability" in res
    assert "burstiness_score" in res
    assert "robotic_phrases_count" in res
    assert res["robotic_phrases_count"] >= 3
    assert len(res["recommendations"]) > 0


@pytest.mark.live
@pytest.mark.asyncio
async def test_vietqr_billing_generation():
    checkout = await billing_provider.create_checkout_session(
        user_id="usr_test_12345",
        user_email="test@example.com",
        target_plan="pro",
        success_url="http://localhost:3050/settings",
        cancel_url="http://localhost:3050/settings",
    )
    assert checkout["target_plan"] == "pro"
    assert checkout["amount_vnd"] == 99000
    assert "vietqr.io/image" in checkout["qr_code_url"]
    assert "MBBank" in checkout["bank_name"]
    assert "UPGRADE" in checkout["transfer_content"]


@pytest.mark.asyncio
async def test_bulk_csv_parser():
    csv_content = b"""title,description,type,audience
De tai 1,Nghien cuu IoT,technical,Ky su phan mem
De tai 2,Phan tich thi truong EV,market_research,Ban Giam doc
"""
    rows = await bulk_report_service.parse_batch_file(csv_content, "topics.csv")
    assert len(rows) == 2
    assert rows[0]["title"] == "De tai 1"
    assert rows[1]["type"] == "market_research"


@pytest.mark.live
@pytest.mark.asyncio
async def test_mermaid_diagram_agent():
    spec = await visual_diagram_agent.plan_and_generate_diagram(
        context_text="Hệ thống gồm Client gửi request đến AI Gateway, Gateway chuyển tiếp đến LLM Provider rồi trả kết quả.",
        diagram_type=DiagramType.FLOWCHART,
        diagram_title="Luồng Xử Lý AI",
    )
    assert spec.title == "Luồng Xử Lý AI"
    assert "flowchart" in spec.mermaid_code.lower() or "graph" in spec.mermaid_code.lower()
    assert spec.nodes_count >= 3
