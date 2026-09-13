"""Authenticated, version-checked ledger for local spreadsheet display layers."""
import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Literal, Optional

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import User, AuditLog
from app.models.workbook_action import WorkbookAction
from app.services.data.data_access import owned_dataset, validated_highlight
from app.services.data.url_dataset_loader import url_dataset_loader

router = APIRouter(prefix='/data/workbook-actions', tags=['data'])


class LayerSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['HIGHLIGHT_CELLS', 'CLEAR_HIGHLIGHTS']
    sheet: str = Field(min_length=1, max_length=31)
    cells: list[str] = Field(default_factory=list, max_length=50000)
    color: str = '#FFFF00'
    label: str = Field(default='', max_length=250)


async def source_bytes(db, user, file, file_id, data_source_url):
    if file_id:
        from pathlib import Path
        record = await owned_dataset(db, file_id, user)
        path = Path(record.file_path)
        if not path.is_file():
            raise HTTPException(404, 'Tệp dữ liệu không còn tồn tại.')
        if path.stat().st_size > 50 * 1024 * 1024:
            raise HTTPException(413, 'Tệp vượt giới hạn 50MB.')
        content = path.read_bytes()
    elif file:
        content = await file.read(50 * 1024 * 1024 + 1)
    elif data_source_url:
        try:
            content, _, _ = await url_dataset_loader.load(data_source_url)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    else:
        raise HTTPException(422, 'Cần cung cấp workbook để kiểm tra phiên bản.')
    if not content or len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, 'Tệp trống hoặc vượt giới hạn 50MB.')
    return content


def key_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


async def lock_owner(db, user):
    # Works for SQLite's single writer and PostgreSQL row locks.
    await db.execute(update(User).where(User.id == user.id).values(id=User.id))


async def records(db, user_id, source_key, source_hash):
    return list((await db.scalars(select(WorkbookAction).where(
        WorkbookAction.user_id == user_id, WorkbookAction.source_key == source_key,
        WorkbookAction.source_hash == source_hash,
    ).order_by(WorkbookAction.applied_at, WorkbookAction.created_at, WorkbookAction.id))).all())


def revision(items):
    return key_hash(json.dumps(sorted((item.id, item.status) for item in items if item.status in {'applied', 'undone'})))


def serialize(item):
    return {'id': item.id, 'status': item.status, 'source_hash': item.source_hash,
            'action': item.payload_json, 'preview': item.preview_json,
            'created_at': item.created_at.isoformat(), 'applied_at': item.applied_at.isoformat() if item.applied_at else None}


def audit(db, user, item, event):
    db.add(AuditLog(user_id=user.id, action=event, resource_type='workbook_layer', resource_id=item.id,
                    details_json={'source_hash': item.source_hash, 'sheet': item.payload_json['sheet'],
                                  'cell_count': len(item.payload_json.get('cells', [])), 'target': 'scant_display'}))


@router.post('/preview')
async def preview_action(source_key: str = Form(..., min_length=1, max_length=1000), action: str = Form(...),
                         file: Optional[UploadFile] = File(None), file_id: Optional[str] = Form(None),
                         data_source_url: Optional[str] = Form(None), user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    try:
        spec = LayerSpec.model_validate_json(action)
    except ValidationError:
        raise HTTPException(422, 'Hành động không hợp lệ hoặc chưa được hỗ trợ.')
    if spec.type == 'HIGHLIGHT_CELLS':
        spec.cells, normalized_color = validated_highlight(json.dumps(spec.cells), spec.color)
        spec.color = "#" + normalized_color[-6:]
    content = await source_bytes(db, user, file, file_id, data_source_url)
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=False)
        try:
            if spec.sheet not in wb.sheetnames:
                raise HTTPException(422, 'Sheet không tồn tại trong workbook.')
            ws = wb[spec.sheet]
            sample = []
            for address in spec.cells[:200]:
                cell = ws[address]
                sample.append({'cell': address, 'value': cell.value if isinstance(cell.value, (str, int, float, bool, type(None))) else str(cell.value),
                               'after_color': spec.color})
        finally:
            wb.close()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, 'Lịch sử bền vững hiện hỗ trợ workbook XLSX/XLSM hợp lệ.')
    await lock_owner(db, user)
    digest = hashlib.sha256(content).hexdigest()
    items = await records(db, user.id, key_hash(source_key), digest)
    item = WorkbookAction(user_id=user.id, source_key=key_hash(source_key), source_hash=digest,
                          base_revision=revision(items), payload_json=spec.model_dump(), preview_json=sample)
    db.add(item)
    await db.flush()
    audit(db, user, item, 'WORKBOOK_LAYER_PROPOSED')
    return serialize(item)


@router.get('/history')
async def history(source_key: str = Query(..., max_length=1000), source_hash: str = Query(..., pattern=r'^[a-f0-9]{64}$'),
                  user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = await records(db, user.id, key_hash(source_key), source_hash)
    layers = []
    for item in items:
        if item.status != 'applied':
            continue
        if item.payload_json['type'] == 'CLEAR_HIGHLIGHTS':
            layers = [layer for layer in layers if layer['sheet'] != item.payload_json['sheet']]
        else:
            layers.append({'id': item.id, **item.payload_json})
    return {'items': [serialize(item) for item in sorted(items, key=lambda item: (item.created_at, item.id), reverse=True)[:100]], 'layers': layers, 'undo_id': next((item.id for item in reversed(items) if item.status == 'applied'), None), 'revision': revision(items), 'has_state': any(item.status in {'applied', 'undone'} for item in items)}


async def owned_action(db, user, action_id):
    item = await db.scalar(select(WorkbookAction).where(WorkbookAction.id == action_id, WorkbookAction.user_id == user.id))
    if item is None:
        raise HTTPException(404, 'Không tìm thấy hành động.')
    return item


@router.post('/{action_id}/confirm')
async def confirm(action_id: str, file: Optional[UploadFile] = File(None), file_id: Optional[str] = Form(None),
                  data_source_url: Optional[str] = Form(None), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await owned_action(db, user, action_id)
    content = await source_bytes(db, user, file, file_id, data_source_url)
    if hashlib.sha256(content).hexdigest() != item.source_hash:
        raise HTTPException(409, 'Workbook đã thay đổi. Hãy xem trước lại.')
    await lock_owner(db, user)
    await db.refresh(item)
    if item.status == 'applied':
        return serialize(item)
    if item.status != 'pending':
        raise HTTPException(409, 'Hành động không còn chờ xác nhận.')
    items = await records(db, user.id, item.source_key, item.source_hash)
    if revision(items) != item.base_revision:
        raise HTTPException(409, 'Các lớp màu đã thay đổi. Hãy xem trước lại.')
    item.status = 'applied'
    item.applied_at = datetime.now(timezone.utc)
    audit(db, user, item, 'WORKBOOK_LAYER_APPLIED')
    await db.flush()
    return serialize(item)


@router.post('/{action_id}/cancel')
async def cancel(action_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await lock_owner(db, user)
    item = await owned_action(db, user, action_id)
    if item.status == 'cancelled':
        return serialize(item)
    if item.status != 'pending':
        raise HTTPException(409, 'Chỉ hủy được hành động đang chờ.')
    item.status = 'cancelled'
    audit(db, user, item, 'WORKBOOK_LAYER_CANCELLED')
    return serialize(item)


@router.post('/{action_id}/undo')
async def undo(action_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await lock_owner(db, user)
    item = await owned_action(db, user, action_id)
    if item.status == 'undone':
        return serialize(item)
    applied = [entry for entry in await records(db, user.id, item.source_key, item.source_hash) if entry.status == 'applied']
    if not applied or applied[-1].id != item.id:
        raise HTTPException(409, 'Chỉ hoàn tác hành động được áp dụng gần nhất.')
    item.status = 'undone'
    audit(db, user, item, 'WORKBOOK_LAYER_UNDONE')
    return serialize(item)


@router.post('/source')
async def source_version(file: Optional[UploadFile] = File(None), file_id: Optional[str] = Form(None),
                         data_source_url: Optional[str] = Form(None), user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    content = await source_bytes(db, user, file, file_id, data_source_url)
    return {'source_hash': hashlib.sha256(content).hexdigest()}
