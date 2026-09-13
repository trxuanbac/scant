from sqlalchemy import create_engine

from app.migrations.schema_registry import (
    HEAD_TABLE_COLUMNS,
    LEGACY_TABLE_COLUMNS,
    SchemaSnapshot,
    classify_unversioned_schema,
    inspect_schema,
    load_target_metadata,
)


def test_target_metadata_registers_every_current_table():
    metadata = load_target_metadata()

    assert set(metadata.tables) >= {
        "users",
        "auth_accounts",
        "admin_configuration",
        "billing_payments",
        "billing_subscriptions",
        "claims",
        "evidences",
        "image_assets",
        "workbook_actions",
    }
    assert set(metadata.tables) == set(HEAD_TABLE_COLUMNS)


def test_known_empty_legacy_and_head_schemas_are_classified():
    assert classify_unversioned_schema(SchemaSnapshot(tables={})) == "empty"
    assert (
        classify_unversioned_schema(
            SchemaSnapshot(tables=LEGACY_TABLE_COLUMNS)
        )
        == "legacy"
    )
    assert (
        classify_unversioned_schema(
            SchemaSnapshot(tables=HEAD_TABLE_COLUMNS)
        )
        == "head"
    )


def test_unknown_unversioned_schema_is_rejected():
    snapshot = SchemaSnapshot(
        tables={"users": ("id", "invented_column")}
    )

    assert classify_unversioned_schema(snapshot) == "unknown"


def test_inspector_ignores_migration_and_sqlite_internal_tables():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id VARCHAR(36))")
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32))"
        )

        snapshot = inspect_schema(connection)

    engine.dispose()
    assert snapshot.tables == {"users": ("id",)}
