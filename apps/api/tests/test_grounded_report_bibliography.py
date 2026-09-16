from datetime import date
from types import SimpleNamespace

from app.services.citations.bibliography_service import bibliography_service
from app.services.agent.agentic_report_orchestrator import AgenticReportOrchestrator


def source(source_id: str, title: str, **overrides):
    values = {
        "id": source_id,
        "title": title,
        "authors": "Nguyễn Văn A",
        "organization": None,
        "publisher": "Nhà xuất bản Khoa học",
        "published_date": "2025",
        "publication_year": None,
        "canonical_url": f"https://example.org/{source_id}",
        "url": f"https://example.org/{source_id}",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_bibliography_contains_only_cited_sources():
    result = bibliography_service.build(
        ["s2"],
        {"s1": source("s1", "Nguồn không dùng"), "s2": source("s2", "Nguồn đã dùng")},
        "apa7",
        accessed_at=date(2026, 9, 16),
    )

    assert "Nguồn đã dùng" in result.plain_text
    assert "Nguồn không dùng" not in result.plain_text
    assert result.source_ids == ["s2"]


def test_missing_author_and_date_are_not_invented():
    item = source(
        "s1",
        "Chính sách quốc gia",
        authors=None,
        organization=None,
        publisher=None,
        published_date=None,
        publication_year=None,
    )

    entry = bibliography_service.render_entry(item, 1, "apa7", date(2026, 9, 16))

    assert "Official Author" not in entry
    assert "Anonymous" not in entry
    assert "2024" not in entry
    assert "n.d." in entry
    assert "Chính sách quốc gia" in entry


def test_numbered_styles_have_stable_order_and_deduplicate_ids():
    result = bibliography_service.build(
        ["s2", "s1", "s2"],
        {"s1": source("s1", "Nguồn một"), "s2": source("s2", "Nguồn hai")},
        "ieee",
        accessed_at=date(2026, 9, 16),
    )

    assert result.source_ids == ["s2", "s1"]
    assert result.inline_labels == {"s2": "[1]", "s1": "[2]"}
    assert result.entries[0].startswith("[1]")
    assert result.entries[1].startswith("[2]")


def test_apa_inline_label_uses_real_author_and_year():
    item = source("s1", "Nghiên cứu", authors="Trần Thị B", published_date="2025-04-02")

    assert bibliography_service.inline_label(item, 1, "apa7") == "(Trần Thị B, 2025)"


def test_orchestrator_collects_only_citations_in_source_order():
    cited = AgenticReportOrchestrator._collect_cited_source_ids(
        [
            (SimpleNamespace(id="section-1"), {"citations_found": ["s2", "s1"]}),
            (SimpleNamespace(id="section-2"), {"citations_found": ["s2"]}),
        ],
        source_order=["s1", "s2", "s3"],
    )

    assert cited == ["s1", "s2"]


def test_orchestrator_recognizes_reference_section_titles():
    assert AgenticReportOrchestrator._is_reference_section("TÀI LIỆU THAM KHẢO") is True
    assert AgenticReportOrchestrator._is_reference_section("References") is True
    assert AgenticReportOrchestrator._is_reference_section("Kết luận") is False
