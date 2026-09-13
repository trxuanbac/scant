import copy
import json

import pytest

from app.services.data.analysis_contracts import (
    AnalysisScope,
    AnalysisScopeError,
    SourceVersion,
    bind_analysis_evidence,
    normalize_analysis_scope,
)


SHEETS = ["Doanh thu", "Chi phí"]


def test_source_version_serializes_the_exact_public_identity():
    source = SourceVersion(
        source_id="stored-file-1",
        source_kind="stored_file",
        version="a" * 64,
        display_name="Bao cao.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=128,
    )

    assert source.as_dict() == {
        "source_id": "stored-file-1",
        "source_kind": "stored_file",
        "version": "a" * 64,
        "display_name": "Bao cao.xlsx",
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "size_bytes": 128,
    }


@pytest.mark.parametrize(
    ("raw_scope", "expected"),
    [
        ({"type": "workbook"}, {"mode": "workbook", "sheets": SHEETS, "range": None}),
        (
            json.dumps({"type": "sheets", "sheets": ["Chi phí", "Doanh thu"]}),
            {"mode": "sheets", "sheets": ["Chi phí", "Doanh thu"], "range": None},
        ),
        ({"type": "sheet", "sheet": "doanh thu"}, {"mode": "sheet", "sheets": ["Doanh thu"], "range": None}),
        (
            {"type": "range", "sheet": "Chi phí", "range": "b2:c10"},
            {"mode": "range", "sheets": ["Chi phí"], "range": "B2:C10"},
        ),
    ],
)
def test_scope_normalizes_each_supported_mode(raw_scope, expected):
    assert normalize_analysis_scope(raw_scope, available_sheets=SHEETS).as_dict() == expected


@pytest.mark.parametrize(
    ("sheet_name", "selected_range", "expected"),
    [
        ("Doanh thu", "B2:C4", {"mode": "range", "sheets": ["Doanh thu"], "range": "B2:C4"}),
        ("Chi phí", None, {"mode": "sheet", "sheets": ["Chi phí"], "range": None}),
        (None, None, {"mode": "workbook", "sheets": SHEETS, "range": None}),
    ],
)
def test_omitted_scope_is_derived_without_silently_losing_the_selected_range(sheet_name, selected_range, expected):
    scope = normalize_analysis_scope(
        None,
        available_sheets=SHEETS,
        sheet_name=sheet_name,
        selected_range=selected_range,
    )
    assert scope.as_dict() == expected


@pytest.mark.parametrize(
    "raw_scope",
    [
        "{bad json",
        {"type": "unknown"},
        {"type": "workbook", "sheet": "Doanh thu"},
        {"type": "sheets", "sheets": ["Doanh thu", "Doanh thu"]},
        {"type": "sheet", "sheet": "Không có"},
        {"type": "range", "sheet": "Doanh thu", "range": "A0:B2"},
        {"type": "range", "sheet": "Doanh thu", "range": "B4:A2"},
        {"type": "range", "sheet": "Doanh thu", "range": "XFE1:XFE2"},
    ],
)
def test_invalid_or_ambiguous_scope_is_rejected(raw_scope):
    with pytest.raises(AnalysisScopeError):
        normalize_analysis_scope(raw_scope, available_sheets=SHEETS)


def test_evidence_binding_copies_payload_and_binds_every_dictionary_evidence():
    source = SourceVersion("file-1", "stored_file", "b" * 64, "sales.xlsx", "application/xlsx", 42)
    scope = AnalysisScope("range", ("Doanh thu",), "B2:B4")
    payload = {
        "answer": "Tổng doanh thu là 60.",
        "evidence": {"sheet": "Doanh thu", "ranges": ["B2:B4"], "operation": "SUM", "rowCount": 3},
        "result": {"value": 60, "evidence": {"sheet": "Doanh thu", "ranges": ["B2:B4"]}},
        "insight": {"evidence": "Ba dòng cộng lại thành 60"},
    }
    original = copy.deepcopy(payload)

    bound = bind_analysis_evidence(payload, source_version=source, scope=scope)

    expected_source = source.as_dict()
    expected_scope = scope.as_dict()
    assert payload == original
    assert bound["analysis_context"] == {"source_version": expected_source, "scope": expected_scope}
    assert bound["evidence"]["source_version"] == expected_source
    assert bound["evidence"]["scope"] == expected_scope
    assert bound["result"]["evidence"]["source_version"] == expected_source
    assert bound["insight"]["evidence"] == "Ba dòng cộng lại thành 60"
    assert bound["answer"] == "Tổng doanh thu là 60."
