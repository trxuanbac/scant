import pytest
import openpyxl
import os
import tempfile
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.data.google_sheets_service import (
    google_sheets_service,
    col_letter_to_index,
    index_to_col_letter,
    hex_to_google_rgb,
    google_rgb_to_hex,
)
from app.services.data.workbook_chat_service import workbook_chat_service
from app.services.data.adapters import GoogleSheetsAdapter


def test_coordinate_and_index_conversions():
    # 0-based column conversions
    assert col_letter_to_index("A") == 0
    assert col_letter_to_index("B") == 1
    assert col_letter_to_index("O") == 14
    assert col_letter_to_index("Z") == 25
    assert col_letter_to_index("AA") == 26

    assert index_to_col_letter(0) == "A"
    assert index_to_col_letter(1) == "B"
    assert index_to_col_letter(14) == "O"
    assert index_to_col_letter(25) == "Z"
    assert index_to_col_letter(26) == "AA"

    # Single cell A1 parse
    r, c = google_sheets_service.parse_a1_coordinate("O36")
    assert r == 35
    assert c == 14

    # GridRange construction for O36
    grid = google_sheets_service.parse_a1_range_to_grid(sheet_id=0, range_str="O36")
    assert grid == {
        "sheetId": 0,
        "startRowIndex": 35,
        "endRowIndex": 36,
        "startColumnIndex": 14,
        "endColumnIndex": 15,
    }

    # GridRange construction for range O9:O36
    grid_range = google_sheets_service.parse_a1_range_to_grid(sheet_id=123, range_str="O9:O36")
    assert grid_range == {
        "sheetId": 123,
        "startRowIndex": 8,
        "endRowIndex": 36,
        "startColumnIndex": 14,
        "endColumnIndex": 15,
    }

    # GridRange construction for full row 36
    grid_row = google_sheets_service.parse_a1_range_to_grid(sheet_id=0, range_str="36", max_cols=30)
    assert grid_row == {
        "sheetId": 0,
        "startRowIndex": 35,
        "endRowIndex": 36,
        "startColumnIndex": 0,
        "endColumnIndex": 30,
    }


def test_color_conversions():
    rgb_yellow = hex_to_google_rgb("#FEF08A")
    assert pytest.approx(rgb_yellow["red"], 0.01) == 0.996
    assert pytest.approx(rgb_yellow["green"], 0.01) == 0.941
    assert pytest.approx(rgb_yellow["blue"], 0.01) == 0.541

    hex_back = google_rgb_to_hex(rgb_yellow)
    assert hex_back == "#FEF08A"

    rgb_green = hex_to_google_rgb("#BBF7D0")
    assert pytest.approx(rgb_green["red"], 0.01) == 0.733
    assert pytest.approx(rgb_green["green"], 0.01) == 0.968
    assert pytest.approx(rgb_green["blue"], 0.01) == 0.816


def test_extract_spreadsheet_id():
    url1 = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=0"
    assert google_sheets_service.extract_spreadsheet_id(url1) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    url2 = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTABCDEF1234567890/pubhtml"
    assert google_sheets_service.extract_spreadsheet_id(url2) == "2PACX-1vTABCDEF1234567890"

    raw_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    assert google_sheets_service.extract_spreadsheet_id(raw_id) == raw_id


@pytest.mark.asyncio
async def test_google_sheets_highlight_and_verification_mock():
    # Mock httpx responses for Google Sheets API v4
    mock_metadata_resp = MagicMock()
    mock_metadata_resp.status_code = 200
    mock_metadata_resp.json.return_value = {
        "sheets": [
            {
                "properties": {
                    "sheetId": 0,
                    "title": "REPORT_XE_QUA_TRAM",
                    "gridProperties": {"rowCount": 100, "columnCount": 26},
                }
            }
        ]
    }

    mock_batch_resp = MagicMock()
    mock_batch_resp.status_code = 200
    mock_batch_resp.json.return_value = {"spreadsheetId": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"}

    mock_verify_resp = MagicMock()
    mock_verify_resp.status_code = 200
    mock_verify_resp.json.return_value = {
        "sheets": [
            {
                "data": [
                    {
                        "rowData": [
                            {
                                "values": [
                                    {
                                        "userEnteredFormat": {
                                            "backgroundColor": {
                                                "red": 0.9961,
                                                "green": 0.9412,
                                                "blue": 0.5412,
                                            }
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers=None):
            if "fields=sheets.properties" in url:
                return mock_metadata_resp
            return mock_verify_resp

        async def post(self, url, headers=None, json=None):
            return mock_batch_resp

    with patch("httpx.AsyncClient", return_value=MockAsyncClient()):
        res = await google_sheets_service.highlight_cells(
            spreadsheet_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            sheet_name="REPORT_XE_QUA_TRAM",
            cell_addresses=["O36"],
            color_hex="#FEF08A",
            access_token="mock_valid_token_123",
            session_id="test_session_1",
        )

        assert res["success"] is True
        assert res["synced_to_google_sheets"] is True
        assert res["verified_on_google_sheets"] is True
        assert res["highlighted_count"] == 1
        assert res["cells"][0]["cell"] == "O36"
        assert res["cells"][0]["row"] == 36
        assert res["cells"][0]["column"] == "O"
        assert res["cells"][0]["startRowIndex"] == 35
        assert res["cells"][0]["endRowIndex"] == 36
        assert res["cells"][0]["startColumnIndex"] == 14
        assert res["cells"][0]["endColumnIndex"] == 15


@pytest.mark.asyncio
async def test_workbook_analysis_action_with_google_sync():
    # Create temporary Excel file mimicking REPORT_XE_QUA_TRAM
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "REPORT_XE_QUA_TRAM"

    # Headers at row 1
    headers = ["STT", "Biển số xe", "Mã trạm", "Tên trạm", "Loại xe", "Giá tiền"]
    ws.append(headers)

    # 35 rows of data
    for i in range(1, 35):
        ws.append([i, f"29A-{i:05d}", f"T{i}", "Mỹ Lộc", "Xe con", 500 + i])

    # Row 36: Max price
    ws.append([35, "30E-99999", "T99", "Mỹ Lộc", "Xe tải lớn", 1136])
    ws.append([36, "30E-88888", "T98", "Mỹ Lộc", "Xe con", 600])

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        wb.save(tmp.name)
        tmp_path = tmp.name

    try:
        # Mock Google Sheets service call
        with patch.object(
            google_sheets_service,
            "get_valid_access_token",
            return_value=("mock_token_abc", None),
        ), patch.object(
            google_sheets_service,
            "highlight_cells",
            return_value={
                "success": True,
                "synced_to_google_sheets": True,
                "verified_on_google_sheets": True,
                "sheet_id": 0,
                "sheet_name": "REPORT_XE_QUA_TRAM",
            },
        ):
            res = await workbook_chat_service.analyze_action(
                file_path=tmp_path,
                prompt="giá trị cao nhất",
                sheet_name="REPORT_XE_QUA_TRAM",
                data_source_url="https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
            )

            assert res["mode"] == "analysis_action"
            assert "1.136" in res["answer"]
            assert res["actions"] == []
            assert len(res["pending_actions"]) >= 1
            action = res["pending_actions"][0]
            assert action["requires_confirmation"] is True
            assert action["type"] == "HIGHLIGHT_CELLS"
            # Must point to row 36 and column F (Giá tiền)
            assert action["cells"] == ["F36"]

            # Structured matched cells check
            matched_cells = res["result"].get("matched_cells", [])
            assert len(matched_cells) >= 1
            assert matched_cells[0]["sheetName"] == "REPORT_XE_QUA_TRAM"
            assert matched_cells[0]["row"] == 36
            assert matched_cells[0]["column"] == "F"
            assert matched_cells[0]["cell"] == "F36"

            # Google sync check
            gs = res.get("google_sync", {})
            assert gs.get("is_google_sheet") is True
            assert gs.get("synced_to_google_sheets") is False
            assert gs.get("verified_on_google_sheets") is False
            assert gs.get("google_sync_attempted") is False

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
