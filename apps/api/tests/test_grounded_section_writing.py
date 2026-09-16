from types import SimpleNamespace

import pytest

from app.services.agent.report_research_contracts import ClaimEvidence, SourceCandidate
from app.services.editor.writing_engine import writing_engine
from app.services.agent.agentic_report_orchestrator import AgenticReportOrchestrator


def source(source_id: str, title: str) -> SourceCandidate:
    return SourceCandidate(
        id=source_id,
        canonical_url=f"https://example.org/{source_id}",
        title=title,
        excerpt=f"Bằng chứng từ {title}",
        retrieval_status="available",
        trust_score=0.9,
        relevance_score=0.9,
        freshness_score=0.8,
    )


def evidence(source_id: str) -> ClaimEvidence:
    return ClaimEvidence(
        claim_id=f"claim-{source_id}",
        section_id="section-1",
        planned_claim="Thị trường tăng trưởng theo số liệu chính thức.",
        source_ids=[source_id],
        supporting_excerpts=["Thị trường tăng trưởng 12% trong năm 2025."],
        confidence=0.9,
        verification_status="verified",
    )


@pytest.mark.asyncio
async def test_grounded_draft_only_exposes_section_sources(monkeypatch):
    captured = {}

    async def fake_execute(request):
        captured["prompt"] = request.prompt
        return SimpleNamespace(
            text="Thị trường tăng 12% trong năm 2025 [SRC:s1].",
            usage=SimpleNamespace(total_tokens=25),
        )

    monkeypatch.setattr("app.services.editor.writing_engine.ai_gateway.execute", fake_execute)

    result = await writing_engine.draft_grounded_section(
        section_title="Thị trường",
        section_level=2,
        topic_name="Xe điện",
        evidence=[evidence("s1")],
        sources_by_id={"s1": source("s1", "Nguồn chính thức"), "s2": source("s2", "Nguồn không liên quan")},
        citation_labels={"s1": "[1]"},
        instruction="",
        tone="professional",
        target_words=200,
    )

    assert "Nguồn chính thức" in captured["prompt"]
    assert "Nguồn không liên quan" not in captured["prompt"]
    assert result["citations_found"] == ["s1"]
    assert result["invalid_citations"] == []
    assert result["stable_text"].endswith("[SRC:s1].")
    assert result["plain_text"].endswith("[1].")


@pytest.mark.asyncio
async def test_grounded_draft_rejects_unknown_source_marker(monkeypatch):
    async def fake_execute(_request):
        return SimpleNamespace(
            text="Số liệu được công bố năm 2025 [SRC:missing].",
            usage=SimpleNamespace(total_tokens=10),
        )

    monkeypatch.setattr("app.services.editor.writing_engine.ai_gateway.execute", fake_execute)

    result = await writing_engine.draft_grounded_section(
        section_title="Thị trường",
        section_level=2,
        topic_name="Xe điện",
        evidence=[evidence("s1")],
        sources_by_id={"s1": source("s1", "Nguồn chính thức")},
        citation_labels={"s1": "[1]"},
    )

    assert result["citations_found"] == []
    assert result["invalid_citations"] == ["missing"]
    assert "[SRC:missing]" not in result["plain_text"]


@pytest.mark.asyncio
async def test_grounded_draft_flags_uncited_specific_claim(monkeypatch):
    async def fake_execute(_request):
        return SimpleNamespace(
            text="Quy mô thị trường đạt 42% trong năm 2025.",
            usage=SimpleNamespace(total_tokens=10),
        )

    monkeypatch.setattr("app.services.editor.writing_engine.ai_gateway.execute", fake_execute)

    result = await writing_engine.draft_grounded_section(
        section_title="Thị trường",
        section_level=2,
        topic_name="Xe điện",
        evidence=[evidence("s1")],
        sources_by_id={"s1": source("s1", "Nguồn chính thức")},
        citation_labels={"s1": "[1]"},
    )

    assert result["unsupported_claims"] == ["Quy mô thị trường đạt 42% trong năm 2025."]


def test_orchestrator_builds_claim_source_rows_from_used_citations():
    rows = AgenticReportOrchestrator._claim_source_payloads(
        section_id="section-1",
        draft_result={"citations_found": ["s1"], "invalid_citations": [], "unsupported_claims": []},
        evidence_items=[evidence("s1"), evidence("s2")],
    )

    assert rows == [
        {
            "report_section_id": "section-1",
            "source_id": "s1",
            "citation_id": None,
            "claim_text": "Thị trường tăng trưởng theo số liệu chính thức.",
            "evidence_text": "Thị trường tăng trưởng 12% trong năm 2025.",
            "confidence_score": 0.9,
            "verification_status": "verified",
        }
    ]
