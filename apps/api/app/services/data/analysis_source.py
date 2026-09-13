"""Resolve one safe workbook source and fingerprint the exact analyzed bytes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import openpyxl
import pandas as pd
from fastapi import HTTPException, UploadFile

from app.models.entities import User
from app.services.data.analysis_contracts import SourceVersion
from app.services.data.data_access import owned_dataset, safe_dataset_name, save_dataset
from app.services.data.url_dataset_loader import url_dataset_loader


MAX_ANALYSIS_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ResolvedAnalysisSource:
    path: Path
    content: bytes
    source_version: SourceVersion
    sheet_names: tuple[str, ...]


def _sheet_names(path: Path, display_name: str) -> tuple[str, ...]:
    if path.suffix.lower() == ".csv":
        return (Path(display_name).stem or "Sheet1",)
    if path.suffix.lower() == ".xls":
        with pd.ExcelFile(path) as workbook:
            return tuple(workbook.sheet_names)
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=False)
        try:
            return tuple(workbook.sheetnames)
        finally:
            workbook.close()
    except Exception as exc:
        raise HTTPException(422, "Workbook không hợp lệ hoặc không thể đọc danh sách sheet.") from exc


def _validate_content(content: bytes) -> None:
    if not content:
        raise HTTPException(413, "Tệp dữ liệu đang trống.")
    if len(content) > MAX_ANALYSIS_BYTES:
        raise HTTPException(413, "Tệp vượt giới hạn 50MB.")


async def resolve_analysis_source(
    db,
    user: User | None,
    *,
    file: UploadFile | None = None,
    file_id: str | None = None,
    data_source_url: str | None = None,
    sheet_range: str | None = None,
) -> ResolvedAnalysisSource:
    has_upload = file is not None and bool(file.filename and file.filename.strip())
    has_file_id = bool(file_id and file_id.strip())
    has_url = bool(data_source_url and data_source_url.strip())
    if sum((has_upload, has_file_id, has_url)) != 1:
        raise HTTPException(422, "Cần cung cấp đúng một nguồn dữ liệu.")

    if has_file_id:
        record = await owned_dataset(db, file_id.strip(), user)
        path = Path(record.file_path)
        if not path.is_file():
            raise HTTPException(404, "Tệp dữ liệu không còn tồn tại.")
        if path.stat().st_size > MAX_ANALYSIS_BYTES:
            raise HTTPException(413, "Tệp vượt giới hạn 50MB.")
        content = path.read_bytes()
        display_name = safe_dataset_name(record.original_name or record.filename)
        mime_type = record.mime_type or "application/octet-stream"
        source_kind = "stored_file"
        source_id = record.id
    elif has_upload:
        content = await file.read(MAX_ANALYSIS_BYTES + 1)
        display_name = safe_dataset_name(file.filename)
        mime_type = file.content_type or "application/octet-stream"
        _validate_content(content)
        path = Path(save_dataset(content, display_name, str(user.id) if user else "guest"))
        source_kind = "upload"
        source_id = ""
    else:
        try:
            content, loaded_name, mime_type = await url_dataset_loader.load(
                data_source_url.strip(), sheet_range=sheet_range
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        display_name = safe_dataset_name(loaded_name)
        _validate_content(content)
        path = Path(save_dataset(content, display_name, str(user.id) if user else "guest"))
        source_kind = "linked"
        source_id = ""

    _validate_content(content)
    version = hashlib.sha256(content).hexdigest()
    if not source_id:
        source_id = "src_" + hashlib.sha256(f"{source_kind}:{version}".encode()).hexdigest()[:32]
    sheets = _sheet_names(path, display_name)
    if not sheets:
        raise HTTPException(422, "Workbook không có sheet để phân tích.")
    identity = SourceVersion(
        source_id=source_id,
        source_kind=source_kind,
        version=version,
        display_name=display_name,
        mime_type=mime_type,
        size_bytes=len(content),
    )
    return ResolvedAnalysisSource(path=path, content=content, source_version=identity, sheet_names=sheets)
