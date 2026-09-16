from app.services.agent.template_profile_service import template_profile_service
from app.services.agent.agentic_report_orchestrator import AgenticReportOrchestrator


def test_template_profile_prefers_detected_template_citation_style():
    profile = template_profile_service.build(
        {
            "headings": [{"text": "TÀI LIỆU THAM KHẢO", "level": 1}],
            "full_text": "TÀI LIỆU THAM KHẢO\n[1] A. Author, Title, 2025.",
            "presentation_rules": "Giữ nguyên đánh số tài liệu tham khảo.",
        },
        report_type="research",
        explicit_requirements="Dùng APA 7",
    )

    assert profile.citation_style == "ieee"
    assert profile.has_uploaded_template is True
    assert "TÀI LIỆU THAM KHẢO" in profile.required_sections
    assert profile.presentation_rules == "Giữ nguyên đánh số tài liệu tham khảo."


def test_template_profile_uses_explicit_requirement_without_detected_style():
    profile = template_profile_service.build(
        {"headings": [{"text": "Kết luận", "level": 1}], "full_text": ""},
        report_type="business_report",
        explicit_requirements="Trình bày trích dẫn và tài liệu tham khảo theo APA 7.",
    )

    assert profile.citation_style == "apa7"
    assert "KẾT LUẬN" in profile.required_sections
    assert "TÀI LIỆU THAM KHẢO" in profile.required_sections


def test_template_profile_uses_report_type_fallback_without_template():
    assert template_profile_service.build({}, "technical", "").citation_style == "ieee"
    assert template_profile_service.build({}, "research", "").citation_style == "apa7"
    assert template_profile_service.build({}, "business_report", "").citation_style == "numbered"


def test_template_profile_contract_serializes_with_schema_version():
    profile = template_profile_service.build({}, "proposal", "")

    payload = profile.model_dump(mode="json")

    assert payload["schema_version"] == "1.0"
    assert payload["citation_style"] == "numbered"
    assert payload["required_sections"][-2:] == ["KẾT LUẬN", "TÀI LIỆU THAM KHẢO"]


def test_orchestrator_builds_serializable_template_profile_checkpoint():
    payload = AgenticReportOrchestrator._build_template_profile_checkpoint(
        {"headings": [{"text": "References"}], "full_text": "APA 7"},
        report_type="research",
        instructions="",
    )

    assert payload["schema_version"] == "1.0"
    assert payload["citation_style"] == "apa7"
