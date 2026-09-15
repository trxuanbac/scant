"""durable analysis sessions

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=20), nullable=False),
        sa.Column("source_version", sa.String(length=64), nullable=False),
        sa.Column("source_display_name", sa.String(length=255), nullable=False),
        sa.Column("source_mime_type", sa.String(length=100), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column("available_sheets_json", sa.JSON(), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("client_key_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "source_id",
            "source_kind",
            "source_version",
            "client_key_hash",
            name="uq_analysis_sessions_owner_client_source",
        ),
    )
    op.create_index(
        "ix_analysis_sessions_owner_source_updated",
        "analysis_sessions",
        ["user_id", "source_id", "source_version", "updated_at"],
        unique=False,
    )
    op.create_table(
        "analysis_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["analysis_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_analysis_messages_session_sequence"),
    )
    op.create_index(
        "ix_analysis_messages_session_created",
        "analysis_messages",
        ["session_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "analysis_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("action_ids_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["analysis_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["analysis_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_findings_session_created",
        "analysis_findings",
        ["session_id", "created_at"],
        unique=False,
    )
    with op.batch_alter_table("workbook_actions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("analysis_session_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_workbook_actions_analysis_session_id",
            "analysis_sessions",
            ["analysis_session_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_workbook_actions_analysis_session",
            ["analysis_session_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("workbook_actions", schema=None) as batch_op:
        batch_op.drop_index("ix_workbook_actions_analysis_session")
        batch_op.drop_constraint("fk_workbook_actions_analysis_session_id", type_="foreignkey")
        batch_op.drop_column("analysis_session_id")
    op.drop_index("ix_analysis_findings_session_created", table_name="analysis_findings")
    op.drop_table("analysis_findings")
    op.drop_index("ix_analysis_messages_session_created", table_name="analysis_messages")
    op.drop_table("analysis_messages")
    op.drop_index("ix_analysis_sessions_owner_source_updated", table_name="analysis_sessions")
    op.drop_table("analysis_sessions")
