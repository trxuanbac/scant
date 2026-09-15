import hashlib

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.analysis_session import AnalysisFinding, AnalysisMessage, AnalysisSession
from app.models.entities import User
from app.models.workbook_action import WorkbookAction
from app.services.data.analysis_contracts import AnalysisScope, SourceVersion
from app.services.data.analysis_session_service import get_or_create_session, record_exchange


def auth(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=user_id)}"}


def source(version_char: str = "a", source_kind: str = "stored_file") -> SourceVersion:
    return SourceVersion(
        source_id="dataset-1",
        source_kind=source_kind,
        version=version_char * 64,
        display_name="doanh-thu.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=2048,
    )


@pytest_asyncio.fixture
async def session_ctx(client, test_session_factory):
    async with test_session_factory() as db:
        db.add_all(
            [
                User(id="owner-a", name="Owner A", email="a@example.test", plan="free"),
                User(id="owner-b", name="Owner B", email="b@example.test", plan="free"),
            ]
        )
        await db.commit()
    return client, test_session_factory


@pytest.mark.asyncio
async def test_service_reuses_hashed_key_and_splits_changed_source(session_ctx):
    _, factory = session_ctx
    async with factory() as db:
        owner = await db.get(User, "owner-a")
        first = await get_or_create_session(
            db,
            owner,
            source(),
            ["Tổng quan", "Chi tiết"],
            AnalysisScope("workbook", ("Tổng quan", "Chi tiết")),
            "browser-secret-key",
        )
        reused = await get_or_create_session(
            db,
            owner,
            source(),
            ["Tổng quan", "Chi tiết"],
            AnalysisScope("sheet", ("Chi tiết",)),
            "browser-secret-key",
        )
        changed = await get_or_create_session(
            db,
            owner,
            source("b"),
            ["Tổng quan", "Chi tiết"],
            AnalysisScope("workbook", ("Tổng quan", "Chi tiết")),
            "browser-secret-key",
        )
        changed_kind = await get_or_create_session(
            db,
            owner,
            source(source_kind="upload"),
            ["Tổng quan", "Chi tiết"],
            AnalysisScope("workbook", ("Tổng quan", "Chi tiết")),
            "browser-secret-key",
        )
        await db.commit()

        assert reused.id == first.id
        assert reused.scope_json == {"mode": "sheet", "sheets": ["Chi tiết"], "range": None}
        assert changed.id != first.id
        assert changed_kind.id != first.id
        assert first.client_key_hash == hashlib.sha256(b"browser-secret-key").hexdigest()
        assert first.client_key_hash != "browser-secret-key"
        assert first.available_sheets_json == ["Tổng quan", "Chi tiết"]


@pytest.mark.asyncio
async def test_record_exchange_orders_messages_and_extracts_only_supported_findings(session_ctx):
    _, factory = session_ctx
    async with factory() as db:
        owner = await db.get(User, "owner-a")
        session = await get_or_create_session(
            db, owner, source(), ["Data"], AnalysisScope("workbook", ("Data",)), "conversation"
        )
        _, assistant, finding = await record_exchange(
            db,
            session,
            "Doanh thu trung bình là bao nhiêu?",
            {
                "answer": "Doanh thu trung bình là 125.",
                "result": {"average": 125},
                "evidence": {"sheet": "Data", "cells": ["B2:B8"]},
                "analysis_history_item": {"operation": "average", "summary": "Trung bình 125"},
            },
        )
        _, _, no_finding = await record_exchange(
            db,
            session,
            "Bạn làm được gì?",
            {"answer": "Tôi có thể hỗ trợ phân tích.", "evidence": {}},
        )
        await db.commit()

        messages = list(
            (await db.scalars(select(AnalysisMessage).order_by(AnalysisMessage.sequence))).all()
        )
        assert [message.sequence for message in messages] == [1, 2, 3, 4]
        assert [message.role for message in messages] == ["user", "assistant", "user", "assistant"]
        assert finding is not None
        assert finding.message_id == assistant.id
        assert finding.evidence_json == {"sheet": "Data", "cells": ["B2:B8"]}
        assert no_finding is None


@pytest.mark.asyncio
async def test_session_api_restores_filters_updates_and_hides_sensitive_fields(session_ctx):
    client, factory = session_ctx
    async with factory() as db:
        owner = await db.get(User, "owner-a")
        session = await get_or_create_session(
            db,
            owner,
            source(),
            ["Tổng quan", "Chi tiết"],
            AnalysisScope("workbook", ("Tổng quan", "Chi tiết")),
            "do-not-return-this-key",
        )
        _, _, finding = await record_exchange(
            db,
            session,
            "Tìm điểm bất thường",
            {
                "answer": "Có một điểm bất thường.",
                "result": {"outlier_count": 1},
                "evidence": {"sheet": "Chi tiết", "cells": ["C9"]},
                "actions": [{"id": "action-linked"}],
            },
        )
        db.add(
            WorkbookAction(
                id="action-linked",
                user_id=owner.id,
                analysis_session_id=session.id,
                source_key="c" * 64,
                source_hash=source().version,
                base_revision="d" * 64,
                payload_json={"type": "HIGHLIGHT_CELLS", "sheet": "Chi tiết", "cells": ["C9"]},
                preview_json=[{"cell": "C9", "value": "private-preview-value"}],
            )
        )
        session_id = session.id
        finding_id = finding.id
        await db.commit()

    response = await client.get(
        "/api/v1/data/analysis-sessions",
        params={"source_id": "dataset-1", "source_version": "a" * 64},
        headers=auth("owner-a"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body["items"]] == [session_id]
    assert "client_key_hash" not in response.text
    assert "do-not-return-this-key" not in response.text

    detail = await client.get(
        f"/api/v1/data/analysis-sessions/{session_id}", headers=auth("owner-a")
    )
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert [message["sequence"] for message in payload["messages"]] == [1, 2]
    assert payload["findings"][0]["action_ids"] == ["action-linked"]
    assert payload["workbook_action_ids"] == ["action-linked"]
    assert "private-preview-value" not in detail.text

    updated = await client.patch(
        f"/api/v1/data/analysis-sessions/{session_id}/scope",
        json={"scope": {"type": "range", "sheet": "chi tiết", "range": "$B$2:C9"}},
        headers=auth("owner-a"),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["scope"] == {
        "mode": "range",
        "sheets": ["Chi tiết"],
        "range": "B2:C9",
    }
    invalid = await client.patch(
        f"/api/v1/data/analysis-sessions/{session_id}/scope",
        json={"scope": {"type": "sheet", "sheet": "Không tồn tại"}},
        headers=auth("owner-a"),
    )
    assert invalid.status_code == 422

    for _ in range(2):
        accepted = await client.post(
            f"/api/v1/data/analysis-sessions/{session_id}/findings/{finding_id}/accept",
            headers=auth("owner-a"),
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"
        archived = await client.post(
            f"/api/v1/data/analysis-sessions/{session_id}/archive", headers=auth("owner-a")
        )
        assert archived.status_code == 200
        assert archived.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_session_api_never_reveals_foreign_resources(session_ctx):
    client, factory = session_ctx
    async with factory() as db:
        owner = await db.get(User, "owner-a")
        session = await get_or_create_session(
            db, owner, source(), ["Data"], AnalysisScope("workbook", ("Data",)), "private"
        )
        _, _, finding = await record_exchange(
            db,
            session,
            "Tính tổng",
            {"answer": "10", "result": {"sum": 10}, "evidence": {"sheet": "Data"}},
        )
        session_id, finding_id = session.id, finding.id
        await db.commit()

    listing = await client.get("/api/v1/data/analysis-sessions", headers=auth("owner-b"))
    assert listing.status_code == 200
    assert listing.json()["items"] == []
    calls = [
        ("GET", f"/api/v1/data/analysis-sessions/{session_id}", None),
        ("PATCH", f"/api/v1/data/analysis-sessions/{session_id}/scope", {"scope": {"type": "workbook"}}),
        ("POST", f"/api/v1/data/analysis-sessions/{session_id}/findings/{finding_id}/accept", None),
        ("POST", f"/api/v1/data/analysis-sessions/{session_id}/archive", None),
    ]
    for method, path, body in calls:
        response = await client.request(method, path, json=body, headers=auth("owner-b"))
        assert response.status_code == 404
