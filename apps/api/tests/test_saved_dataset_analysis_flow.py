from pathlib import Path
import hashlib

import pytest
from fastapi import HTTPException

from app.api.v1 import reports as reports_api
from app.core.config import settings
from app.main import app
from app.models.entities import Project, UploadedFile
from test_admin_core import auth, ctx


async def add_dataset(factory, root: Path, owner: str, file_id: str = "saved-dataset") -> UploadedFile:
    path = root / f"{file_id}.csv"
    path.write_text("name,revenue\nA,100\nB,200\n", encoding="utf-8")
    project_id = f"project-{owner}-{file_id}"
    record = UploadedFile(
        id=file_id,
        project_id=project_id,
        filename=path.name,
        original_name="Doanh_thu.csv",
        file_type="excel",
        mime_type="text/csv",
        file_size=path.stat().st_size,
        file_path=str(path),
        file_hash="a" * 64,
        metadata_json={},
    )
    async with factory() as db:
        db.add(Project(id=project_id, user_id=owner, name="Dataset", type="data_analysis"))
        await db.flush()
        db.add(record)
        await db.commit()
    return record


@pytest.mark.asyncio
async def test_signed_url_rejects_foreign_saved_dataset(ctx, tmp_path, monkeypatch):
    client, factory = ctx
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    await add_dataset(factory, tmp_path, "admin", "private-dataset")

    response = await client.post(
        "/api/v1/files/private-dataset/signed-url",
        headers=auth("user"),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_saved_dataset_resolver_accepts_owner_and_hides_foreign_file(ctx, tmp_path, monkeypatch):
    _, factory = ctx
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    await add_dataset(factory, tmp_path, "admin")
    resolver = getattr(reports_api, "_resolve_stored_dataset_source", None)
    assert callable(resolver)

    async with factory() as db:
        admin = await db.get(reports_api.User, "admin")
        user = await db.get(reports_api.User, "user")
        record, path = await resolver(db, admin, "saved-dataset")
        assert record.original_name == "Doanh_thu.csv"
        assert path.read_text(encoding="utf-8").startswith("name,revenue")
        with pytest.raises(HTTPException) as rejected:
            await resolver(db, user, "saved-dataset")
        assert rejected.value.status_code == 404


@pytest.mark.asyncio
async def test_saved_dataset_profile_returns_display_identity(ctx, tmp_path, monkeypatch):
    client, factory = ctx
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    await add_dataset(factory, tmp_path, "admin")

    response = await client.get(
        "/api/v1/data/profile/saved-dataset",
        headers=auth("admin"),
    )

    assert response.status_code == 200, response.text
    assert response.json()["file_id"] == "saved-dataset"
    assert response.json()["file_name"] == "Doanh_thu.csv"
    assert response.json()["original_name"] == "Doanh_thu.csv"
    assert response.json()["source_version"]["source_id"] == "saved-dataset"
    assert response.json()["source_version"]["version"] == hashlib.sha256(
        b"name,revenue\nA,100\nB,200\n"
    ).hexdigest()


@pytest.mark.asyncio
async def test_auto_create_rejects_foreign_or_conflicting_saved_dataset(ctx, tmp_path, monkeypatch):
    client, factory = ctx
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    await add_dataset(factory, tmp_path, "admin", "report-dataset")

    foreign = await client.post(
        "/api/v1/reports/auto-create",
        headers=auth("user"),
        data={"prompt": "Phân tích doanh thu", "dataset_file_id": "report-dataset"},
    )
    assert foreign.status_code == 404

    conflicting = await client.post(
        "/api/v1/reports/auto-create",
        headers=auth("admin"),
        data={
            "prompt": "Phân tích doanh thu",
            "dataset_file_id": "report-dataset",
            "data_source_url": "https://example.com/data.csv",
        },
    )
    assert conflicting.status_code == 422


def test_auto_create_schema_accepts_saved_dataset_identifier():
    operation = app.openapi()["paths"]["/api/v1/reports/auto-create"]["post"]
    schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    if "$ref" in schema:
        schema = app.openapi()["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    assert "dataset_file_id" in schema["properties"]
