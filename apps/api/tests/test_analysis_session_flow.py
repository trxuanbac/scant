import hashlib
import io
import json
from unittest.mock import AsyncMock

import openpyxl
import pytest
from sqlalchemy import func, select

from app.models.analysis_session import AnalysisFinding, AnalysisMessage, AnalysisSession
from app.models.workbook_action import WorkbookAction
from app.services.data.workbook_chat_service import workbook_chat_service
from test_admin_core import auth, ctx


def workbook_bytes(value: int = 10) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet.append(["Tên", "Giá trị"])
    sheet.append(["A", value])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_authenticated_chat_persists_bound_exchange_and_changed_bytes_split_session(ctx, monkeypatch):
    client, factory = ctx
    response_payload = {
        "answer": "Tổng là 10.",
        "result": {"sum": 10},
        "evidence": {"sheet": "Data", "cells": ["B2"]},
        "actions": [],
        "pending_actions": [],
    }
    chat = AsyncMock(return_value=response_payload)
    monkeypatch.setattr(workbook_chat_service, "chat", chat)
    content = workbook_bytes()
    request = {
        "files": {"file": ("data.xlsx", content)},
        "data": {"message": "Tính tổng", "conversation_id": "browser-conversation"},
        "headers": auth("user"),
    }
    first = await client.post("/api/v1/data/workbook-chat", **request)
    second = await client.post("/api/v1/data/workbook-chat", **request)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["analysis_session_id"] == second.json()["analysis_session_id"]

    expected_hash = hashlib.sha256(content).hexdigest()
    async with factory() as db:
        sessions = list((await db.scalars(select(AnalysisSession))).all())
        messages = list(
            (await db.scalars(select(AnalysisMessage).order_by(AnalysisMessage.sequence))).all()
        )
        findings = list((await db.scalars(select(AnalysisFinding))).all())
    assert len(sessions) == 1
    assert [message.sequence for message in messages] == [1, 2, 3, 4]
    assert len(findings) == 2
    assert findings[0].evidence_json["source_version"]["version"] == expected_hash
    assert findings[0].evidence_json["scope"] == {
        "mode": "workbook",
        "sheets": ["Data"],
        "range": None,
    }

    changed = await client.post(
        "/api/v1/data/workbook-chat",
        files={"file": ("data.xlsx", workbook_bytes(11))},
        data={"message": "Tính tổng", "conversation_id": "browser-conversation"},
        headers=auth("user"),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["analysis_session_id"] != first.json()["analysis_session_id"]


@pytest.mark.asyncio
async def test_failed_and_guest_chat_do_not_create_durable_rows(ctx, monkeypatch):
    client, factory = ctx
    monkeypatch.setattr(workbook_chat_service, "chat", AsyncMock(side_effect=RuntimeError("provider failed")))
    failed = await client.post(
        "/api/v1/data/workbook-chat",
        files={"file": ("data.xlsx", workbook_bytes())},
        data={"message": "Tính tổng", "conversation_id": "failed"},
        headers=auth("user"),
    )
    assert failed.status_code == 400

    monkeypatch.setattr(
        workbook_chat_service,
        "chat",
        AsyncMock(return_value={"answer": "Xin chào", "evidence": {}, "actions": [], "pending_actions": []}),
    )
    guest = await client.post(
        "/api/v1/data/workbook-chat",
        files={"file": ("data.xlsx", workbook_bytes())},
        data={"message": "Xin chào", "conversation_id": "guest"},
    )
    assert guest.status_code == 200, guest.text
    assert "analysis_session_id" not in guest.json()
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(AnalysisSession)) == 0
        assert await db.scalar(select(func.count()).select_from(AnalysisMessage)) == 0


@pytest.mark.asyncio
async def test_analysis_action_is_persisted_with_exact_evidence(ctx, monkeypatch):
    client, factory = ctx
    monkeypatch.setattr(
        workbook_chat_service,
        "analyze_action",
        AsyncMock(
            return_value={
                "answer": "Phát hiện một ngoại lệ.",
                "result": {"outlier_count": 1},
                "evidence": {"sheet": "Data", "cells": ["B2"]},
                "analysis_history_item": {"operation": "outlier", "summary": "1 ngoại lệ"},
            }
        ),
    )
    content = workbook_bytes()
    response = await client.post(
        "/api/v1/data/workbook-analysis-action",
        files={"file": ("data.xlsx", content)},
        data={"prompt": "Tìm ngoại lệ", "conversation_id": "analysis-action"},
        headers=auth("user"),
    )
    assert response.status_code == 200, response.text
    async with factory() as db:
        finding = (await db.scalars(select(AnalysisFinding))).one()
    assert finding.evidence_json["source_version"]["version"] == hashlib.sha256(content).hexdigest()
    assert finding.evidence_json["scope"]["sheets"] == ["Data"]


@pytest.mark.asyncio
async def test_workbook_action_attaches_only_owned_matching_session(ctx, monkeypatch):
    client, factory = ctx
    monkeypatch.setattr(
        workbook_chat_service,
        "chat",
        AsyncMock(return_value={"answer": "10", "result": {"sum": 10}, "evidence": {"sheet": "Data"}}),
    )
    content = workbook_bytes()
    chat = await client.post(
        "/api/v1/data/workbook-chat",
        files={"file": ("data.xlsx", content)},
        data={"message": "Tính tổng", "conversation_id": "attach"},
        headers=auth("user"),
    )
    assert chat.status_code == 200, chat.text
    session_id = chat.json()["analysis_session_id"]
    action = json.dumps(
        {"type": "HIGHLIGHT_CELLS", "sheet": "Data", "cells": ["B2"], "color": "#FFFF00"}
    )
    attached = await client.post(
        "/api/v1/data/workbook-actions/preview",
        files={"file": ("data.xlsx", content)},
        data={"source_key": "browser-source", "action": action, "analysis_session_id": session_id},
        headers=auth("user"),
    )
    assert attached.status_code == 200, attached.text
    assert attached.json()["analysis_session_id"] == session_id
    async with factory() as db:
        stored = await db.get(WorkbookAction, attached.json()["id"])
        assert stored.analysis_session_id == session_id

    foreign = await client.post(
        "/api/v1/data/workbook-actions/preview",
        files={"file": ("data.xlsx", content)},
        data={"source_key": "browser-source", "action": action, "analysis_session_id": session_id},
        headers=auth("admin"),
    )
    assert foreign.status_code == 404
    stale = await client.post(
        "/api/v1/data/workbook-actions/preview",
        files={"file": ("data.xlsx", workbook_bytes(99))},
        data={"source_key": "browser-source", "action": action, "analysis_session_id": session_id},
        headers=auth("user"),
    )
    assert stale.status_code == 409
