from types import SimpleNamespace

from app.services.quality.report_integrity_service import report_integrity_service


def section(title: str, text: str = "", summary=None, content=None):
    return SimpleNamespace(
        id=title.lower().replace(" ", "-"),
        title=title,
        plain_text=text,
        structured_summary_json=summary or {},
        content_json=content or {"type": "doc", "content": []},
    )


def source(source_id: str):
    return SimpleNamespace(id=source_id, url=f"https://example.org/{source_id}", canonical_url=f"https://example.org/{source_id}")


def profile():
    return {
        "required_sections": ["KẾT LUẬN", "TÀI LIỆU THAM KHẢO"],
        "citation_style": "numbered",
    }


def grounded_sections():
    return [
        section(
            "Phân tích",
            "Thông tin có căn cứ [1].",
            {"web_grounding": {"source_ids": ["s1"], "unsupported_claims": [], "invalid_citations": []}},
        ),
        section("KẾT LUẬN", "Kết luận báo cáo."),
        section(
            "TÀI LIỆU THAM KHẢO",
            "[1] Nguồn thật",
            {"bibliography": {"source_ids": ["s1"], "generated_from_citations": True}},
        ),
    ]


def test_integrity_blocks_fake_or_dangling_citations():
    result = report_integrity_service.validate(
        sections=[
            section("Phân tích", "Claim [SRC:missing]"),
            section("KẾT LUẬN"),
            section("TÀI LIỆU THAM KHẢO"),
        ],
        sources=[],
        images=[],
        template_profile=profile(),
    )

    assert result.ready is False
    assert "dangling_citation" in {item.code for item in result.blocking_errors}


def test_integrity_warns_but_does_not_block_when_optional_image_is_missing():
    result = report_integrity_service.validate(
        sections=grounded_sections(),
        sources=[source("s1")],
        images=[],
        template_profile=profile(),
    )

    assert result.ready is True
    assert "no_relevant_image" in {item.code for item in result.warnings}


def test_integrity_blocks_uncited_reference_and_unsupported_claim():
    sections = grounded_sections()
    sections[0].structured_summary_json["web_grounding"]["unsupported_claims"] = ["Doanh thu tăng 50%."]
    sections[2].structured_summary_json["bibliography"]["source_ids"].append("s2")

    result = report_integrity_service.validate(
        sections=sections,
        sources=[source("s1"), source("s2")],
        images=[],
        template_profile=profile(),
    )

    codes = {item.code for item in result.blocking_errors}
    assert "unsupported_claim" in codes
    assert "uncited_reference" in codes


def test_integrity_blocks_image_without_source_page():
    image_node = {
        "type": "image",
        "attrs": {"assetId": "asset-1", "sourceType": "web", "sourceUrl": None},
    }
    sections = grounded_sections()
    sections[0].content_json = {"type": "doc", "content": [image_node]}

    result = report_integrity_service.validate(
        sections=sections,
        sources=[source("s1")],
        images=[SimpleNamespace(id="asset-1", source_type="web", source_page_url=None, original_url=None)],
        template_profile=profile(),
    )

    assert "image_missing_provenance" in {item.code for item in result.blocking_errors}


def test_resume_stage_returns_first_incomplete_checkpoint():
    stage = report_integrity_service.resume_stage({
        "pipeline": {
            "template_profile": {"status": "completed"},
            "research": {"status": "completed"},
            "draft_sections": {"status": "failed"},
        }
    })

    assert stage == "draft_sections"
