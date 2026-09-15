"""Persistence and safe serialization for workbook analysis sessions."""

from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_session import AnalysisFinding, AnalysisMessage, AnalysisSession
from app.models.entities import User
from app.models.workbook_action import WorkbookAction
from app.services.data.analysis_contracts import (
    AnalysisScope,
    AnalysisScopeError,
    SourceVersion,
    normalize_analysis_scope,
)


def _scope_request(scope: AnalysisScope) -> dict[str, Any]:
    if scope.mode == "workbook":
        return {"type": "workbook"}
    if scope.mode == "sheets":
        return {"type": "sheets", "sheets": list(scope.sheets)}
    if scope.mode == "range":
        return {"type": "range", "sheet": scope.sheets[0], "range": scope.cell_range}
    return {"type": "sheet", "sheet": scope.sheets[0]}


def _clean_json(value: Any) -> Any:
    """Copy JSON-compatible response data while dropping known raw-source payloads."""
    if isinstance(value, dict):
        return {
            str(key): _clean_json(child)
            for key, child in value.items()
            if key not in {"preview", "preview_rows", "file_bytes", "source_bytes"}
        }
    if isinstance(value, (list, tuple)):
        return [_clean_json(child) for child in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _first_mapping(value: Any, key: str) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    candidate = value.get(key)
    if isinstance(candidate, dict) and candidate:
        return candidate
    for child in value.values():
        if isinstance(child, dict):
            found = _first_mapping(child, key)
            if found:
                return found
        elif isinstance(child, list):
            for item in child:
                found = _first_mapping(item, key)
                if found:
                    return found
    return None


def _meaningful_result(response: dict[str, Any]) -> Any | None:
    result = response.get("result")
    if isinstance(result, (dict, list)) and result:
        return result
    if isinstance(result, (int, float)) and not isinstance(result, bool):
        return result
    history = response.get("analysis_history_item")
    if isinstance(history, dict) and history:
        return history
    return None


def _action_ids(response: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("actions", "pending_actions"):
        values = response.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            action_id = value.get("id") if isinstance(value, dict) else value
            if isinstance(action_id, str) and action_id and action_id not in ids:
                ids.append(action_id)
    return ids


async def _lock_owner(db: AsyncSession, user_id: str) -> None:
    await db.execute(update(User).where(User.id == user_id).values(id=User.id))


async def get_or_create_session(
    db: AsyncSession,
    user: User,
    source_version: SourceVersion,
    available_sheets: list[str] | tuple[str, ...],
    scope: AnalysisScope,
    client_key: str,
) -> AnalysisSession:
    key = client_key.strip() if isinstance(client_key, str) else ""
    if not key or len(key) > 1000:
        raise ValueError("Conversation key is invalid")
    sheets = list(available_sheets)
    if not sheets or any(not isinstance(sheet, str) or not sheet for sheet in sheets):
        raise AnalysisScopeError("Workbook không có sheet để phân tích.")
    if len(set(sheets)) != len(sheets):
        raise AnalysisScopeError("Danh sách sheet không được trùng lặp.")
    normalized_scope = normalize_analysis_scope(_scope_request(scope), available_sheets=sheets)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()

    await _lock_owner(db, user.id)
    session = await db.scalar(
        select(AnalysisSession).where(
            AnalysisSession.user_id == user.id,
            AnalysisSession.source_id == source_version.source_id,
            AnalysisSession.source_kind == source_version.source_kind,
            AnalysisSession.source_version == source_version.version,
            AnalysisSession.client_key_hash == digest,
        )
    )
    now = datetime.now(timezone.utc)
    if session is not None:
        if session.available_sheets_json != sheets:
            raise AnalysisScopeError("Danh mục sheet không khớp với phiên bản nguồn.")
        session.scope_json = normalized_scope.as_dict()
        session.status = "active"
        session.updated_at = now
        await db.flush()
        return session

    session = AnalysisSession(
        user_id=user.id,
        source_id=source_version.source_id,
        source_kind=source_version.source_kind,
        source_version=source_version.version,
        source_display_name=source_version.display_name,
        source_mime_type=source_version.mime_type,
        source_size_bytes=source_version.size_bytes,
        available_sheets_json=sheets,
        scope_json=normalized_scope.as_dict(),
        client_key_hash=digest,
        title=f"Phân tích {source_version.display_name}"[:255],
        status="active",
        updated_at=now,
    )
    db.add(session)
    await db.flush()
    return session


async def record_exchange(
    db: AsyncSession,
    session: AnalysisSession,
    question: str,
    response: dict[str, Any],
) -> tuple[AnalysisMessage, AnalysisMessage, AnalysisFinding | None]:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question is required")
    if not isinstance(response, dict):
        raise ValueError("Structured response is required")
    await _lock_owner(db, session.user_id)
    locked = await db.scalar(
        select(AnalysisSession)
        .where(AnalysisSession.id == session.id, AnalysisSession.user_id == session.user_id)
        .with_for_update()
    )
    if locked is None:
        raise ValueError("Analysis session no longer exists")
    last_sequence = await db.scalar(
        select(func.max(AnalysisMessage.sequence)).where(AnalysisMessage.session_id == session.id)
    )
    cleaned = _clean_json(response)
    user_message = AnalysisMessage(
        session_id=session.id,
        sequence=(last_sequence or 0) + 1,
        role="user",
        content_text=question.strip(),
        response_json={},
    )
    answer = cleaned.get("answer")
    assistant_message = AnalysisMessage(
        session_id=session.id,
        sequence=(last_sequence or 0) + 2,
        role="assistant",
        content_text=answer if isinstance(answer, str) else "",
        response_json=cleaned,
    )
    db.add_all([user_message, assistant_message])
    await db.flush()

    finding = None
    evidence = _first_mapping(cleaned, "evidence")
    result = _meaningful_result(cleaned)
    if evidence is not None and result is not None:
        history = cleaned.get("analysis_history_item")
        title = cleaned.get("title")
        if not isinstance(title, str) or not title.strip():
            operation = history.get("operation") if isinstance(history, dict) else None
            title = str(operation).strip() if operation else "Phát hiện phân tích"
        summary = cleaned.get("answer")
        if not isinstance(summary, str) or not summary.strip():
            candidate = history.get("summary") if isinstance(history, dict) else None
            summary = str(candidate).strip() if candidate else title
        result_json = result if isinstance(result, dict) else {"value": result}
        finding = AnalysisFinding(
            session_id=session.id,
            message_id=assistant_message.id,
            status="proposed",
            title=title[:255],
            summary=summary,
            evidence_json=copy.deepcopy(evidence),
            result_json=copy.deepcopy(result_json),
            action_ids_json=_action_ids(cleaned),
        )
        db.add(finding)
    locked.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return user_message, assistant_message, finding


async def owned_session(db: AsyncSession, user_id: str, session_id: str) -> AnalysisSession:
    session = await db.scalar(
        select(AnalysisSession).where(
            AnalysisSession.id == session_id,
            AnalysisSession.user_id == user_id,
        )
    )
    if session is None:
        raise HTTPException(404, "Không tìm thấy phiên phân tích.")
    return session


def serialize_session(session: AnalysisSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "source": {
            "source_id": session.source_id,
            "source_kind": session.source_kind,
            "version": session.source_version,
            "display_name": session.source_display_name,
            "mime_type": session.source_mime_type,
            "size_bytes": session.source_size_bytes,
        },
        "available_sheets": list(session.available_sheets_json),
        "scope": copy.deepcopy(session.scope_json),
        "title": session.title,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


def serialize_message(message: AnalysisMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "sequence": message.sequence,
        "role": message.role,
        "content": message.content_text,
        "response": copy.deepcopy(message.response_json),
        "created_at": message.created_at.isoformat(),
    }


def serialize_finding(finding: AnalysisFinding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "message_id": finding.message_id,
        "status": finding.status,
        "title": finding.title,
        "summary": finding.summary,
        "evidence": copy.deepcopy(finding.evidence_json),
        "result": copy.deepcopy(finding.result_json),
        "action_ids": list(finding.action_ids_json),
        "created_at": finding.created_at.isoformat(),
    }


async def serialize_session_detail(db: AsyncSession, session: AnalysisSession) -> dict[str, Any]:
    messages = list(
        (
            await db.scalars(
                select(AnalysisMessage)
                .where(AnalysisMessage.session_id == session.id)
                .order_by(AnalysisMessage.sequence)
            )
        ).all()
    )
    findings = list(
        (
            await db.scalars(
                select(AnalysisFinding)
                .where(AnalysisFinding.session_id == session.id)
                .order_by(AnalysisFinding.created_at, AnalysisFinding.id)
            )
        ).all()
    )
    action_ids = list(
        (
            await db.scalars(
                select(WorkbookAction.id)
                .where(
                    WorkbookAction.analysis_session_id == session.id,
                    WorkbookAction.user_id == session.user_id,
                )
                .order_by(WorkbookAction.created_at, WorkbookAction.id)
            )
        ).all()
    )
    return {
        **serialize_session(session),
        "messages": [serialize_message(message) for message in messages],
        "findings": [serialize_finding(finding) for finding in findings],
        "workbook_action_ids": action_ids,
    }
