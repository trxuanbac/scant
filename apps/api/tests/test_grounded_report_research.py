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


def test_normalize_results_drops_high_trust_but_irrelevant_academic_hits():
    candidates = grounded_research_service.normalize_results(
        [
            {
                "title": "Vietnam electric vehicle market outlook",
                "url": "https://agency.gov.vn/ev-outlook",
                "snippet": "Electric vehicle demand and charging infrastructure in Vietnam.",
            },
            {
                "title": "Finite-rank optimizers for Lieb-Thirring inequalities",
                "url": "https://arxiv.org/abs/2510.24148",
                "snippet": "We establish an operator inequality in mathematical physics.",
            },
        ],
        "Vietnam electric vehicle market",
    )

    assert [item.canonical_url for item in candidates] == ["https://agency.gov.vn/ev-outlook"]


def test_evidence_packets_require_a_distinctive_topic_anchor():
    sections = [SimpleNamespace(id="strategy", title="Phân khúc thị trường và chiến lược")]
    candidates = grounded_research_service.normalize_results(
        [
            {
                "title": "Tác động chính sách tới thị trường xe điện Việt Nam",
                "url": "https://agency.gov.vn/ev-policy",
                "snippet": "Chính sách hỗ trợ xe điện và hạ tầng sạc tại Việt Nam.",
            },
            {
                "title": "Mô hình lựa chọn phân khúc thị trường hạt điều",
                "url": "https://example.org/cashew-segments",
                "snippet": "Chiến lược xuất khẩu hạt điều theo từng phân khúc thị trường.",
            },
        ],
        "thị trường xe điện Việt Nam chiến lược phân khúc",
    )

    packets = grounded_research_service.build_evidence_packets(
        sections,
        candidates,
        topic="Phân tích thị trường xe điện Việt Nam và chiến lược thâm nhập",
    )

    assert len(packets["strategy"]) == 1
    assert packets["strategy"][0].source_ids == [
        next(item.id for item in candidates if "ev-policy" in item.canonical_url)
    ]


def test_evidence_packets_do_not_treat_connecting_words_as_topic_anchors():
    sections = [SimpleNamespace(id="strategy", title="Phân khúc thị trường và chiến lược")]
    candidates = grounded_research_service.normalize_results(
        [
            {
                "title": "Chiến lược thị trường hạt điều tại Việt Nam",
                "url": "https://example.org/cashew-strategy",
                "snippet": "Phân tích cơ hội và đề xuất thâm nhập các phân khúc xuất khẩu.",
            },
            {
                "title": "Chiến lược thị trường xe điện tại Việt Nam",
                "url": "https://agency.gov.vn/ev-strategy",
                "snippet": "Phân tích cơ hội và đề xuất thâm nhập phân khúc xe điện phổ thông.",
            },
        ],
        "thị trường xe điện Việt Nam và chiến lược thâm nhập",
    )

    packets = grounded_research_service.build_evidence_packets(
        sections,
        candidates,
        topic="Phân tích thị trường xe điện Việt Nam và đề xuất chiến lược thâm nhập",
    )

    assert [item.source_ids for item in packets["strategy"]] == [[
        next(item.id for item in candidates if "ev-strategy" in item.canonical_url)
    ]]


def test_evidence_packets_reject_single_ambiguous_ev_word():
    sections = [SimpleNamespace(id="market", title="Thị trường xe điện")]
    candidates = grounded_research_service.from_persisted_sources(
        [
            SimpleNamespace(
                id="collision",
                canonical_url="https://arxiv.org/abs/1711.08499",
                url="https://arxiv.org/abs/1711.08499",
                title="Hydrodynamic predictions for Xe+Xe collisions",
                authors=None,
                organization=None,
                publisher=None,
                published_date="2017",
                publication_year=None,
                source_type="paper",
                language="en",
                summary="Heavy ion collisions at the Large Hadron Collider.",
                content_extracted=None,
                access_status="open",
                reliability_score=0.96,
                metadata_json={"research_scores": {"relevance": 1.0}},
            ),
            SimpleNamespace(
                id="electric-field",
                canonical_url="https://example.org/electric-field",
                url="https://example.org/electric-field",
                title="Phân tích dao động dưới tác dụng của điện trường",
                authors=None,
                organization=None,
                publisher=None,
                published_date="2025",
                publication_year=None,
                source_type="paper",
                language="vi",
                summary="Nghiên cứu vật lý về điện trường và dao động phi tuyến.",
                content_extracted=None,
                access_status="open",
                reliability_score=0.92,
                metadata_json={"research_scores": {"relevance": 1.0}},
            ),
        ]
    )

    packets = grounded_research_service.build_evidence_packets(
        sections,
        candidates,
        topic="Phân tích thị trường xe điện Việt Nam",
    )

    assert packets["market"] == []


def test_vietnamese_ev_query_keeps_relevant_english_source():
    candidates = grounded_research_service.normalize_results(
        [
            {
                "title": "Vietnam electric vehicle market outlook",
                "url": "https://example.org/vietnam-ev-outlook",
                "snippet": "Electric vehicle adoption and charging infrastructure in Vietnam.",
            }
        ],
        "phân tích thị trường xe điện Việt Nam",
    )

    packets = grounded_research_service.build_evidence_packets(
        [SimpleNamespace(id="market", title="Thị trường xe điện")],
        candidates,
        topic="Phân tích thị trường xe điện Việt Nam",
    )

    assert len(candidates) == 1
    assert len(packets["market"]) == 1


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
            metadata_json={"research_scores": {"relevance": 0.82}},
        )
    ])

    assert candidates[0].id == "db-source-1"
    assert candidates[0].author_or_organization is None
    assert candidates[0].publisher is None
    assert candidates[0].published_at is None
    assert candidates[0].relevance_score == 0.82
