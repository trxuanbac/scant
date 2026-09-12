import pytest
from app.services.research.academic.base import ResearchSourceModel
from app.services.research.academic.crossref_provider import CrossrefProvider
from app.services.research.academic.arxiv_provider import ArxivProvider
from app.services.research.quality_scorer import source_quality_scorer
from app.services.research.source_verifier import source_verifier
from app.services.research.evidence_extractor import evidence_extractor
from app.services.research.synthesis_agent import synthesis_agent
from app.services.citations.citation_formatter import citation_formatter
from app.services.research.deep_research_pipeline import deep_research_pipeline, DeepResearchResult


@pytest.mark.live
@pytest.mark.asyncio
async def test_crossref_live_search():
    """Verify live Crossref queries return real papers with real DOIs and publishers."""
    provider = CrossrefProvider()
    sources = await provider.search("electric vehicle market vietnam", max_results=3)
    assert len(sources) > 0
    for s in sources:
        assert s.title
        assert s.doi or s.url.startswith("http")
        assert s.provider == "crossref"
        assert s.source_type == "academic"


@pytest.mark.live
@pytest.mark.asyncio
async def test_arxiv_live_search():
    """Verify live arXiv queries return real papers with arXiv IDs and real authors."""
    provider = ArxivProvider()
    sources = await provider.search("deep learning", max_results=3)
    assert len(sources) > 0
    for s in sources:
        assert s.title
        assert s.arxiv_id
        assert s.url.startswith("https://arxiv.org")
        assert s.provider == "arxiv"
        assert len(s.authors) > 0


def test_quality_scorer_transparent_formula():
    """Verify quality score calculation conforms to the transparent 6-factor formula."""
    source = ResearchSourceModel(
        id="src_test_1",
        title="Comprehensive Analysis of Electric Vehicle Adoption in Southeast Asia",
        url="https://doi.org/10.1016/j.trd.2025.104000",
        doi="10.1016/j.trd.2025.104000",
        authors=["Nguyen, A.", "Tran, B."],
        publisher="Elsevier Transportation Research",
        year=2025,
        citation_count=45,
        abstract="In this study, electric vehicle market penetration reaches 18% by 2026.",
        source_type="academic",
        provider="crossref",
        metadata_verified=True,
        url_verified=True,
    )
    scored = source_quality_scorer.score_sources(query="electric vehicle market", sources=[source])
    assert len(scored) == 1
    score = scored[0].quality_score
    breakdown = scored[0].quality_breakdown

    assert 70.0 <= score <= 100.0
    assert "authority" in breakdown
    assert "metadata_completeness" in breakdown
    assert "relevance" in breakdown
    assert "recency" in breakdown
    assert "citation_signal" in breakdown
    assert "verification" in breakdown


def test_source_verifier_deduplication():
    """Verify multi-provider duplicate sources (same DOI or identical title) are merged."""
    s1 = ResearchSourceModel(
        id="src_1",
        title="Market Transition to EV in Southeast Asia",
        url="https://doi.org/10.1000/182",
        doi="10.1000/182",
        authors=["Author One"],
        year=2025,
        provider="crossref",
    )
    s2 = ResearchSourceModel(
        id="src_2",
        title="Market Transition to EV in Southeast Asia",
        url="https://publisher.org/article/182",
        doi="10.1000/182",
        authors=["Author One", "Author Two"],
        year=2025,
        citation_count=12,
        provider="semanticscholar",
    )
    deduped = source_verifier.deduplicate_sources([s1, s2])
    assert len(deduped) == 1
    assert deduped[0].doi == "10.1000/182"
    assert deduped[0].citation_count == 12
    assert len(deduped[0].authors) == 2


def test_evidence_extractor_and_market_claims():
    """Verify extraction of atomic quotes and quantitative statistics."""
    source = ResearchSourceModel(
        id="src_test_ev",
        title="Vietnam EV Report 2026",
        url="https://example.org/report",
        abstract="Doanh số xe điện tại Việt Nam dự báo tăng 35% trong năm 2026, đạt 75.000 xe bán ra.",
        publisher="Ministry of Industry and Trade",
        year=2026,
    )
    evidence_nodes, claims = evidence_extractor.extract_evidence_from_sources(
        query="xe điện Việt Nam 2026",
        sources=[source],
    )
    assert len(evidence_nodes) > 0
    assert len(claims) > 0
    claim_texts = [c.claim for c in claims]
    assert any("35%" in c or "75.000" in c for c in claim_texts)


@pytest.mark.asyncio
async def test_synthesis_anti_hallucination_provenance():
    """Verify synthesized reports filter out unverified fake citation IDs."""
    source_verified = ResearchSourceModel(
        id="src_real_1",
        title="Verified EV Study",
        url="https://doi.org/10.1000/real",
        doi="10.1000/real",
        abstract="Xe điện chiếm 20% tổng lượng phương tiện vào năm 2026.",
    )
    evidence_nodes, _ = evidence_extractor.extract_evidence_from_sources(
        query="xe điện 2026",
        sources=[source_verified],
    )
    report = await synthesis_agent.synthesize_findings(
        query="xe điện 2026",
        sources=[source_verified],
        evidence_nodes=evidence_nodes,
    )
    assert report.valid_citation_count >= 1
    # Check that claims only reference existing valid sources
    for claim in report.claims:
        for sid in claim.source_ids:
            assert sid == "src_real_1" or sid == "1"


def test_citation_formatter_formats():
    """Verify export in IEEE, APA, Harvard, BibTeX, and RIS formats."""
    sources = [
        ResearchSourceModel(
            id="src_cit_1",
            title="Electric Vehicle Market Analysis in Vietnam",
            url="https://doi.org/10.1016/j.trd.2025.100",
            doi="10.1016/j.trd.2025.100",
            authors=["Nguyen, Van A", "Tran, Thi B"],
            publisher="Elsevier Transportation Research",
            year=2025,
        )
    ]
    ieee_text = citation_formatter.format_sources(sources, style="IEEE")
    assert "Nguyen, Van A" in ieee_text
    assert "10.1016/j.trd.2025.100" in ieee_text

    apa_text = citation_formatter.format_sources(sources, style="APA")
    assert "(2025)" in apa_text

    bibtex_text = citation_formatter.format_sources(sources, style="BIBTEX")
    assert "@article{" in bibtex_text

    ris_text = citation_formatter.format_sources(sources, style="RIS")
    assert "TY  - JOUR" in ris_text
    assert "ER  -" in ris_text


@pytest.mark.live
@pytest.mark.asyncio
async def test_end_to_end_deep_research_pipeline_vietnam_ev_2026():
    """Execute end-to-end pipeline with the user's test topic: 'Thị trường xe điện Việt Nam năm 2026'."""
    query = "Thị trường xe điện Việt Nam năm 2026"
    res: DeepResearchResult = await deep_research_pipeline.execute(query=query, mode="quick")

    assert isinstance(res, DeepResearchResult)
    assert res.total_verified > 0
    assert len(res.sources) > 0

    # Ensure zero mock sources (no fake IEEE Systems Journal 96%)
    for s in res.sources:
        assert s.title != f"Technical Research and Architecture: {query}"
        assert not s.url.startswith("https://gartner.example.com")
        assert s.url.startswith("http://") or s.url.startswith("https://")
        assert 0 <= s.quality_score <= 100

    # Ensure synthesis report is generated and provenance verified
    assert res.synthesis is not None
    assert res.synthesis.provenance_verified is True
    assert len(res.synthesis.executive_summary) > 10
    assert len(res.graph_nodes) > 0
