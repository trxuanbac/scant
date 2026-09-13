"""Canonical model registry and fingerprints for unversioned SCANT schemas."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.schema import MetaData

from app.core.database import Base


HEAD_ONLY_TABLES = frozenset(
    {
        "admin_configuration",
        "billing_payments",
        "billing_subscriptions",
        "claims",
        "evidences",
        "image_assets",
        "workbook_actions",
    }
)

LEGACY_MISSING_COLUMNS = MappingProxyType(
    {
        "auth_accounts": frozenset(
            {"access_token", "refresh_token", "scopes", "token_expiry"}
        ),
        "sources": frozenset(
            {
                "abstract",
                "access_status",
                "canonical_url",
                "dataset_id",
                "doi",
                "domain_trust",
                "file_id",
                "language",
                "organization",
                "provider",
                "provider_source_id",
                "publication_name",
                "publication_year",
                "subtitle",
                "updated_at",
                "verification_details_json",
                "verification_score",
                "verification_status",
            }
        ),
        "citations": frozenset(
            {
                "citation_number",
                "claim_id",
                "evidence_id",
                "report_id",
                "support_level",
                "verification_status",
            }
        ),
        "automations": frozenset(
            {
                "analysis_mode",
                "analysis_prompt",
                "description",
                "next_run_at",
                "source_config_json",
                "source_type",
                "timezone",
            }
        ),
        "automation_runs": frozenset(
            {
                "duration_ms",
                "failed_step",
                "output_files_json",
                "source_snapshot_json",
            }
        ),
    }
)


@dataclass(frozen=True)
class SchemaSnapshot:
    tables: Mapping[str, tuple[str, ...]]


def load_target_metadata() -> MetaData:
    """Import every model module before exposing Alembic target metadata."""
    import app.models.admin_billing  # noqa: F401
    import app.models.admin_configuration  # noqa: F401
    import app.models.entities  # noqa: F401
    import app.models.workbook_action  # noqa: F401
    import app.migrations.admin_console  # noqa: F401

    return Base.metadata


def _metadata_columns() -> dict[str, tuple[str, ...]]:
    metadata = load_target_metadata()
    return {
        table_name: tuple(column.name for column in table.columns)
        for table_name, table in sorted(metadata.tables.items())
    }


HEAD_TABLE_COLUMNS = MappingProxyType(_metadata_columns())
LEGACY_TABLE_COLUMNS = MappingProxyType(
    {
        table_name: tuple(
            column
            for column in columns
            if column not in LEGACY_MISSING_COLUMNS.get(table_name, frozenset())
        )
        for table_name, columns in HEAD_TABLE_COLUMNS.items()
        if table_name not in HEAD_ONLY_TABLES
    }
)


def inspect_schema(connection: Connection) -> SchemaSnapshot:
    """Read application table and column names without changing the schema."""
    inspector = inspect(connection)
    tables = {}
    for table_name in sorted(inspector.get_table_names()):
        if table_name == "alembic_version" or table_name.startswith("sqlite_"):
            continue
        tables[table_name] = tuple(
            column["name"] for column in inspector.get_columns(table_name)
        )
    return SchemaSnapshot(tables=tables)


def _same_shape(
    actual: Mapping[str, tuple[str, ...]],
    expected: Mapping[str, tuple[str, ...]],
) -> bool:
    if set(actual) != set(expected):
        return False
    return all(set(actual[name]) == set(expected[name]) for name in expected)


def classify_unversioned_schema(
    snapshot: SchemaSnapshot,
) -> Literal["empty", "legacy", "head", "unknown"]:
    if not snapshot.tables:
        return "empty"
    if _same_shape(snapshot.tables, LEGACY_TABLE_COLUMNS):
        return "legacy"
    if _same_shape(snapshot.tables, HEAD_TABLE_COLUMNS):
        return "head"
    return "unknown"
