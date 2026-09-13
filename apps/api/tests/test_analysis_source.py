import hashlib
import io

import openpyxl
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.models.entities import Project, UploadedFile, User
from app.services.data.analysis_source import resolve_analysis_source
from app.services.data.url_dataset_loader import url_dataset_loader
from test_admin_core import ctx


def workbook_bytes() -> bytes:
    workbook = openpyxl.Workbook()
    workbook.active.title = "Doanh thu"
    workbook.active.append(["Tháng", "Giá trị"])
    workbook.active.append(["T1", 100])
    workbook.create_sheet("Chi phí").append(["Mục", "Giá trị"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def upload(name: str, content: bytes, mime_type: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=name, headers=Headers({"content-type": mime_type}))


@pytest.mark.asyncio
async def test_resolver_hashes_owned_stored_bytes_and_discovers_sheets(ctx, tmp_path):
    _, factory = ctx
    content = workbook_bytes()
    path = tmp_path / "stored.xlsx"
    path.write_bytes(content)
    async with factory() as db:
        db.add(Project(id="analysis-project", user_id="user", name="Analysis", type="data_analysis"))
        await db.flush()
        db.add(
            UploadedFile(
                id="stored-source",
                project_id="analysis-project",
                filename="stored.xlsx",
                original_name="Báo cáo tháng.xlsx",
                file_type="excel",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                file_size=len(content),
                file_path=str(path),
                file_hash="0" * 64,
            )
        )
        await db.commit()

    async with factory() as db:
        user = await db.get(User, "user")
        source = await resolve_analysis_source(db, user, file_id="stored-source")

    assert source.path == path
    assert source.content == content
    assert source.sheet_names == ("Doanh thu", "Chi phí")
    assert source.source_version.as_dict() == {
        "source_id": "stored-source",
        "source_kind": "stored_file",
        "version": hashlib.sha256(content).hexdigest(),
        "display_name": "Báo cáo tháng.xlsx",
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "size_bytes": len(content),
    }


@pytest.mark.asyncio
async def test_resolver_gives_upload_and_link_opaque_content_versions(ctx, tmp_path, monkeypatch):
    _, factory = ctx
    monkeypatch.setattr("app.services.data.data_access.settings.UPLOAD_DIR", tmp_path)
    content = b"name,value\nA,10\n"
    async with factory() as db:
        user = await db.get(User, "user")
        direct = await resolve_analysis_source(db, user, file=upload("sales.csv", content, "text/csv"))

        async def linked_load(url: str, sheet_range=None):
            assert url == "https://example.test/sales.csv"
            assert sheet_range is None
            return content, "linked-sales.csv", "text/csv"

        monkeypatch.setattr(url_dataset_loader, "load", linked_load)
        linked = await resolve_analysis_source(db, user, data_source_url="https://example.test/sales.csv")

    digest = hashlib.sha256(content).hexdigest()
    assert direct.source_version.source_kind == "upload"
    assert linked.source_version.source_kind == "linked"
    assert direct.source_version.version == linked.source_version.version == digest
    assert direct.source_version.source_id not in {"sales.csv", digest}
    assert linked.source_version.source_id not in {"https://example.test/sales.csv", digest}
    assert direct.sheet_names == ("sales",)
    assert linked.sheet_names == ("linked-sales",)


@pytest.mark.asyncio
async def test_resolver_rejects_multiple_or_oversized_sources(ctx, monkeypatch):
    _, factory = ctx
    monkeypatch.setattr("app.services.data.analysis_source.MAX_ANALYSIS_BYTES", 8)
    async with factory() as db:
        user = await db.get(User, "user")
        with pytest.raises(HTTPException) as multiple:
            await resolve_analysis_source(db, user, file=upload("a.csv", b"a\n1", "text/csv"), file_id="stored")
        assert multiple.value.status_code == 422

        with pytest.raises(HTTPException) as oversized:
            await resolve_analysis_source(db, user, file=upload("large.csv", b"123456789", "text/csv"))
        assert oversized.value.status_code == 413


@pytest.mark.asyncio
async def test_resolver_hides_foreign_files_and_reports_missing_owned_paths(ctx, tmp_path):
    _, factory = ctx
    async with factory() as db:
        db.add(Project(id="private-analysis", user_id="admin", name="Private", type="data_analysis"))
        await db.flush()
        db.add(
            UploadedFile(
                id="missing-source",
                project_id="private-analysis",
                filename="missing.csv",
                original_name="missing.csv",
                file_type="excel",
                mime_type="text/csv",
                file_size=10,
                file_path=str(tmp_path / "missing.csv"),
                file_hash="a" * 64,
            )
        )
        await db.commit()

    async with factory() as db:
        user = await db.get(User, "user")
        with pytest.raises(HTTPException) as foreign:
            await resolve_analysis_source(db, user, file_id="missing-source")
        assert foreign.value.status_code == 404

        admin = await db.get(User, "admin")
        with pytest.raises(HTTPException) as missing:
            await resolve_analysis_source(db, admin, file_id="missing-source")
        assert missing.value.status_code == 404
