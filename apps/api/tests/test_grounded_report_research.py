from types import SimpleNamespace

from app.services.agent.grounded_research_service import grounded_research_service


def test_normalize_results_never_invents_missing_metadata():
    items = grounded_research_service.normalize_results(
        [
            {
                "title": "Official statistic",
                "url": "https://agency.gov.vn/data?utm_source=newsletter",
                "snippet": "Kết quả thống kê thị trường năm 2025.",
            }
        ],
        "thống kê thị trường 2025",
    )

    assert len(items) == 1
    assert items[0].canonical_url == "https://agency.gov.vn/data"
    assert items[0].author_or_organization is None
    assert items[0].publisher is None
    assert items[0].published_at is None


def test_official_and_academic_sources_rank_above_blog():
    items = grounded_research_service.normalize_results(
        [
            {
                "title": "Blog thị trường",
                "url": "https://example.wordpress.com/market",
                "snippet": "Số liệu thị trường xe điện.",
            },
            {
                "title": "Báo cáo thị trường chính thức",
                "url": "https://agency.gov.vn/report",
                "snippet": "Số liệu thị trường xe điện.",
            },
        ],
        "số liệu thị trường xe điện",
    )

    assert items[0].canonical_url == "https://agency.gov.vn/report"
    assert items[0].trust_score > items[1].trust_score


def test_normalize_results_deduplicates_tracking_variants():
    items = grounded_research_service.normalize_results(
        [
            {"title": "Report", "url": "https://example.org/report?utm_campaign=a", "snippet": "EV market"},
            {"title": "Report copy", "url": "https://EXAMPLE.org/report#overview", "snippet": "EV market"},
        ],
        "EV market",
    )

    assert len(items) == 1
    assert items[0].canonical_url == "https://example.org/report"


def test_build_plan_skips_front_matter_and_references():
    sections = [
        SimpleNamespace(id="s1", title="LỜI MỞ ĐẦU"),
        SimpleNamespace(id="s2", title="Thị trường xe điện Việt Nam"),
        SimpleNamespace(id="s3", title="TÀI LIỆU THAM KHẢO"),
    ]

    plan = grounded_research_service.build_plan("Xe điện Việt Nam 2026", sections, "research")

    assert [item.section_id for item in plan.questions] == ["s2"]
    assert "Xe điện Việt Nam 2026" in plan.questions[0].query


def test_evidence_packets_exclude_unrelated_sources():
    sections = [SimpleNamespace(id="market", title="Thị trường xe điện")]
    candidates = grounded_research_service.normalize_results(
        [
            {
                "title": "Báo cáo thị trường xe điện",
                "url": "https://agency.gov.vn/ev",
                "snippet": "Quy mô thị trường xe điện Việt Nam tăng trong năm 2025.",
            },
            {
                "title": "Hướng dẫn trồng cà phê",
                "url": "https://example.org/coffee",
                "snippet": "Kỹ thuật tưới nước cho cây cà phê.",
            },
        ],
        "thị trường xe điện",
    )

    packets = grounded_research_service.build_evidence_packets(sections, candidates)

    assert len(packets["market"]) == 1
    assert packets["market"][0].source_ids == [candidates[0].id]
    assert packets["market"][0].verification_status == "verified"


def test_persisted_sources_keep_real_missing_metadata_empty():
    candidates = grounded_research_service.from_persisted_sources([
        SimpleNamespace(
            id="db-source-1",
            canonical_url="https://agency.gov.vn/report",
            url="https://agency.gov.vn/report",
            title="Báo cáo chính thức",
            authors=None,
            organization=None,
            publisher=None,
            published_date=None,
            publication_year=None,
            source_type="government_source",
            language="vi",
            summary="Thống kê thị trường chính thức.",
            content_extracted=None,
            access_status="open",
            reliability_score=0.98,
        )
    ])

    assert candidates[0].id == "db-source-1"
    assert candidates[0].author_or_organization is None
    assert candidates[0].publisher is None
    assert candidates[0].published_at is None
