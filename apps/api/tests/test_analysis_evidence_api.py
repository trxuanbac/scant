import hashlib
import io
import json

import openpyxl
import pytest

from test_admin_core import auth, ctx


def two_sheet_workbook() -> bytes:
    workbook = openpyxl.Workbook()
    revenue = workbook.active
    revenue.title = "Doanh thu"
    revenue.append(["Tháng", "Giá trị"])
    revenue.append(["T1", 10])
    revenue.append(["T2", 20])
    cost = workbook.create_sheet("Chi phí")
    cost.append(["Tháng", "Giá trị"])
    cost.append(["T1", 4])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_scope", "expected_scope"),
    [
        ({"type": "workbook"}, {"mode": "workbook", "sheets": ["Doanh thu", "Chi phí"], "range": None}),
        ({"type": "sheets", "sheets": ["Chi phí", "Doanh thu"]}, {"mode": "sheets", "sheets": ["Chi phí", "Doanh thu"], "range": None}),
        ({"type": "sheet", "sheet": "Doanh thu"}, {"mode": "sheet", "sheets": ["Doanh thu"], "range": None}),
        ({"type": "range", "sheet": "Doanh thu", "range": "B2:B3"}, {"mode": "range", "sheets": ["Doanh thu"], "range": "B2:B3"}),
    ],
)
async def test_chat_round_trips_validated_scope_and_binds_exact_source_to_evidence(ctx, raw_scope, expected_scope):
    client, _ = ctx
    content = two_sheet_workbook()
    response = await client.post(
        "/api/v1/data/workbook-chat",
        headers=auth("user"),
        files={"file": ("finance.xlsx", content)},
        data={"message": "xin chào", "sheet_name": "Doanh thu", "scope": json.dumps(raw_scope)},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    source = body["analysis_context"]["source_version"]
    assert source["version"] == hashlib.sha256(content).hexdigest()
    assert body["analysis_context"]["scope"] == expected_scope
    assert body["evidence"]["source_version"] == source
    assert body["evidence"]["scope"] == expected_scope


@pytest.mark.asyncio
async def test_chat_derives_range_scope_for_legacy_clients(ctx):
    client, _ = ctx
    response = await client.post(
        "/api/v1/data/workbook-chat",
        headers=auth("user"),
        files={"file": ("finance.xlsx", two_sheet_workbook())},
        data={"message": "tính tổng", "sheet_name": "Chi phí", "selected_range": "B2:B2"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["analysis_context"]["scope"] == {
        "mode": "range",
        "sheets": ["Chi phí"],
        "range": "B2:B2",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope",
    ["{broken", json.dumps({"type": "sheet", "sheet": "Không có"}), json.dumps({"type": "range", "sheet": "Doanh thu", "range": "B3:A2"})],
)
async def test_chat_rejects_unresolvable_scope_before_analysis(ctx, scope):
    client, _ = ctx
    response = await client.post(
        "/api/v1/data/workbook-chat",
        headers=auth("user"),
        files={"file": ("finance.xlsx", two_sheet_workbook())},
        data={"message": "tính tổng", "scope": scope},
    )

    assert response.status_code == 422
    assert response.json()["detail"]


@pytest.mark.asyncio
async def test_sheet_analysis_and_preview_expose_the_same_versioned_context(ctx):
    client, _ = ctx
    content = two_sheet_workbook()
    expected_version = hashlib.sha256(content).hexdigest()

    analysis = await client.post(
        "/api/v1/data/analyze-sheet",
        headers=auth("user"),
        files={"file": ("finance.xlsx", content)},
        data={"sheet_name": "Chi phí"},
    )
    preview = await client.post(
        "/api/v1/data/preview-upload",
        headers=auth("user"),
        files={"file": ("finance.xlsx", content)},
        data={"sheet_range": "Doanh thu!A1:B3"},
    )

    assert analysis.status_code == 200, analysis.text
    assert preview.status_code == 200, preview.text
    assert analysis.json()["analysis_context"]["source_version"]["version"] == expected_version
    assert analysis.json()["analysis_context"]["scope"] == {
        "mode": "sheet",
        "sheets": ["Chi phí"],
        "range": None,
    }
    assert preview.json()["analysis_context"]["source_version"]["version"] == expected_version
    assert preview.json()["analysis_context"]["scope"] == {
        "mode": "range",
        "sheets": ["Doanh thu"],
        "range": "A1:B3",
    }
