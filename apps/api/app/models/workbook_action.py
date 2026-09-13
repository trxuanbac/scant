"""Durable history of SCANT display layers, never implicit remote mutations."""
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, Index
from app.core.database import Base
from app.models.entities import generate_uuid, get_utc_now


class WorkbookAction(Base):
    __tablename__ = 'workbook_actions'
    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    source_key = Column(String(64), nullable=False)
    source_hash = Column(String(64), nullable=False)
    base_revision = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default='pending')
    payload_json = Column(JSON, nullable=False)
    preview_json = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=get_utc_now)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index('ix_workbook_actions_owner_source', 'user_id', 'source_key', 'source_hash', 'created_at'),)
