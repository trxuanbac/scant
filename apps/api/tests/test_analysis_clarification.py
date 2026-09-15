from app.services.data.analysis_clarification import build_clarification
from app.services.data.sheet_resolvers import column_resolver


def columns(*names: str) -> list[dict]:
    return [
        {"name": name, "letter": chr(65 + index), "index": index + 1, "header_row": 1}
        for index, name in enumerate(names)
    ]


def test_clarification_contract_deduplicates_candidates_and_exposes_no_values():
    response = build_clarification(
        "column",
        "Bạn muốn dùng cột doanh thu nào?",
        [
            {"value": "Doanh thu thuần", "confidence": 0.75, "reason": "Khớp từ khóa", "sample": 999},
            {"value": "Doanh thu thuần", "confidence": 0.70},
            {"value": "Doanh thu gộp", "confidence": 0.74, "reason": "Khớp từ khóa"},
        ],
        {"sheet": "Kinh doanh", "raw_rows": [{"secret": 1}]},
    )

    assert response["status"] == "needs_clarification"
    assert response["clarification"] == {
        "kind": "column",
        "question": "Bạn muốn dùng cột doanh thu nào?",
        "candidates": [
            {"value": "Doanh thu thuần", "label": "Doanh thu thuần", "confidence": 0.75, "reason": "Khớp từ khóa"},
            {"value": "Doanh thu gộp", "label": "Doanh thu gộp", "confidence": 0.74, "reason": "Khớp từ khóa"},
        ],
        "context": {"sheet": "Kinh doanh"},
    }
    assert response["result"] == {}
    assert response["actions"] == []
    assert response["pending_actions"] == []
    assert response["evidence"] is None
    assert "999" not in str(response)
    assert "secret" not in str(response)


def test_clarification_accepts_all_supported_kinds_and_rejects_invalid_kind():
    for kind in ("sheet", "column", "date", "unit"):
        response = build_clarification(kind, "Hãy chọn", ["A", "B"], {})
        assert response["clarification"]["kind"] == kind
        assert [item["value"] for item in response["clarification"]["candidates"]] == ["A", "B"]

    try:
        build_clarification("invented", "Hãy chọn", ["A"], {})
    except ValueError as exc:
        assert "kind" in str(exc).lower()
    else:
        raise AssertionError("Unsupported clarification kind must fail")


def test_column_resolver_exact_and_accent_insensitive_match_take_precedence():
    schema = columns("Doanh thu", "Doanh thu thuần", "Ngày tạo")

    exact = column_resolver.resolve_column("Doanh thu", schema)
    accent = column_resolver.resolve_column("Ngay tao", schema)

    assert exact["found"] is True
    assert exact["name"] == "Doanh thu"
    assert exact["ambiguous"] is False
    assert exact["confidence"] == 1.0
    assert accent["found"] is True
    assert accent["name"] == "Ngày tạo"
    assert accent["ambiguous"] is False
    assert accent["confidence"] == 0.95


def test_column_resolver_requires_clarification_for_near_tied_candidates():
    schema = columns("Doanh thu thuần", "Doanh thu gộp", "Chi phí")

    ranked = column_resolver.rank_candidates("doanh thu", schema)
    resolved = column_resolver.resolve_column("doanh thu", schema)

    assert [item["name"] for item in ranked[:2]] == ["Doanh thu thuần", "Doanh thu gộp"]
    assert all(item["confidence"] >= 0.4 for item in ranked[:2])
    assert resolved["found"] is False
    assert resolved["ambiguous"] is True
    assert resolved["candidates"] == ["Doanh thu thuần", "Doanh thu gộp"]


def test_column_resolver_returns_ordered_semantic_candidates_and_low_confidence_not_found():
    schema = columns("Lương cơ bản", "Tổng lương", "Mã nhân viên")

    semantic = column_resolver.resolve_column("lương", schema)
    missing = column_resolver.resolve_column("thời tiết", schema)

    assert semantic["found"] is False
    assert semantic["ambiguous"] is True
    assert semantic["candidates"] == ["Lương cơ bản", "Tổng lương"]
    assert missing["found"] is False
    assert missing["ambiguous"] is False
    assert missing["confidence"] == 0.0
    assert missing["candidates"] == ["Lương cơ bản", "Tổng lương", "Mã nhân viên"]
