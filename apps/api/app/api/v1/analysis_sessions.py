"""Authenticated restore and review boundary for workbook analysis sessions."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.analysis_session import AnalysisFinding, AnalysisSession
from app.models.entities import User
from app.services.data.analysis_contracts import AnalysisScopeError, normalize_analysis_scope
from app.services.data.analysis_session_service import (
    owned_session,
    serialize_finding,
    serialize_session,
    serialize_session_detail,
)


router = APIRouter(prefix="/data/analysis-sessions", tags=["data"])


class ScopeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: dict[str, Any] = Field(...)


@router.get("")
async def list_analysis_sessions(
    source_id: str | None = Query(None, min_length=1, max_length=64),
    source_version: str | None = Query(None, pattern=r"^[a-f0-9]{64}$"),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    statement = select(AnalysisSession).where(AnalysisSession.user_id == user.id)
    if source_id is not None:
        statement = statement.where(AnalysisSession.source_id == source_id)
    if source_version is not None:
        statement = statement.where(AnalysisSession.source_version == source_version)
    sessions = list(
        (
            await db.scalars(
                statement.order_by(AnalysisSession.updated_at.desc(), AnalysisSession.id).limit(limit)
            )
        ).all()
    )
    return {"items": [serialize_session(session) for session in sessions]}


@router.get("/{session_id}")
async def get_analysis_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await owned_session(db, user.id, session_id)
    return await serialize_session_detail(db, session)


@router.patch("/{session_id}/scope")
async def update_analysis_scope(
    session_id: str,
    body: ScopeUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await owned_session(db, user.id, session_id)
    try:
        scope = normalize_analysis_scope(body.scope, available_sheets=list(session.available_sheets_json))
    except AnalysisScopeError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.scope_json = scope.as_dict()
    await db.flush()
    return serialize_session(session)


@router.post("/{session_id}/findings/{finding_id}/accept")
async def accept_analysis_finding(
    session_id: str,
    finding_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await owned_session(db, user.id, session_id)
    finding = await db.scalar(
        select(AnalysisFinding).where(
            AnalysisFinding.id == finding_id,
            AnalysisFinding.session_id == session_id,
        )
    )
    if finding is None:
        raise HTTPException(404, "Không tìm thấy phát hiện phân tích.")
    finding.status = "accepted"
    await db.flush()
    return serialize_finding(finding)


@router.post("/{session_id}/archive")
async def archive_analysis_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await owned_session(db, user.id, session_id)
    session.status = "archived"
    await db.flush()
    return serialize_session(session)
