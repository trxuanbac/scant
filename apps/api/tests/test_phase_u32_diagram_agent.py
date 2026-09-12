import pytest
from app.services.visuals.diagram_agent import visual_diagram_agent, DiagramType


@pytest.mark.live
@pytest.mark.asyncio
async def test_diagram_generation_flowchart():
    spec = await visual_diagram_agent.plan_and_generate_diagram(
        context_text="Hệ thống gồm API Gateway, Microservices, Worker Queue và PostgreSQL Database.",
        diagram_type=DiagramType.FLOWCHART,
        detail_level="standard",
        diagram_title="Luồng Xử Lý Hệ Thống"
    )
    assert spec.diagram_type == DiagramType.FLOWCHART
    assert len(spec.mermaid_code) > 10
    assert visual_diagram_agent.validate_mermaid_syntax(spec.mermaid_code) is True
    assert spec.nodes_count >= 3


@pytest.mark.live
@pytest.mark.asyncio
async def test_diagram_generation_erd():
    spec = await visual_diagram_agent.plan_and_generate_diagram(
        context_text="Mô hình dữ liệu gồm Users, Projects, Reports, Sections và Citations.",
        diagram_type=DiagramType.ERD,
        detail_level="deep_technical",
        diagram_title="Lược Đồ Cơ Sở Dữ Liệu ERD"
    )
    assert spec.diagram_type == DiagramType.ERD
    assert visual_diagram_agent.validate_mermaid_syntax(spec.mermaid_code) is True


@pytest.mark.live
@pytest.mark.asyncio
async def test_diagram_generation_sequence():
    spec = await visual_diagram_agent.plan_and_generate_diagram(
        context_text="Người dùng gửi yêu cầu xuất file, API gửi task vào Queue, Worker xử lý và trả kết quả.",
        diagram_type=DiagramType.SEQUENCE,
        diagram_title="Trình Tự Xuất File Báo Cáo"
    )
    assert spec.diagram_type == DiagramType.SEQUENCE
    assert visual_diagram_agent.validate_mermaid_syntax(spec.mermaid_code) is True
