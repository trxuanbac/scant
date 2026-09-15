"""Durable, owner-scoped workbook analysis sessions and reviewed findings."""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from app.core.database import Base
from app.models.entities import generate_uuid, get_utc_now


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(String(64), nullable=False)
    source_kind = Column(String(20), nullable=False)
    source_version = Column(String(64), nullable=False)
    source_display_name = Column(String(255), nullable=False)
    source_mime_type = Column(String(100), nullable=False)
    source_size_bytes = Column(Integer, nullable=False)
    available_sheets_json = Column(JSON, nullable=False)
    scope_json = Column(JSON, nullable=False)
    client_key_hash = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False, default="Phiên phân tích")
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=get_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=get_utc_now, onupdate=get_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source_id",
            "source_version",
            "client_key_hash",
            name="uq_analysis_sessions_owner_client_source",
        ),
        Index(
            "ix_analysis_sessions_owner_source_updated",
            "user_id",
            "source_id",
            "source_version",
            "updated_at",
        ),
    )


class AnalysisMessage(Base):
    __tablename__ = "analysis_messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("analysis_sessions.id", ondelete="CASCADE"), nullable=False)
    sequence = Column(Integer, nullable=False)
    role = Column(String(20), nullable=False)
    content_text = Column(Text, nullable=False)
    response_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=get_utc_now)

    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_analysis_messages_session_sequence"),
        Index("ix_analysis_messages_session_created", "session_id", "created_at"),
    )


class AnalysisFinding(Base):
    __tablename__ = "analysis_findings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("analysis_sessions.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(String(36), ForeignKey("analysis_messages.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="proposed")
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False)
    evidence_json = Column(JSON, nullable=False)
    result_json = Column(JSON, nullable=False, default=dict)
    action_ids_json = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=get_utc_now)

    __table_args__ = (
        Index("ix_analysis_findings_session_created", "session_id", "created_at"),
    )
