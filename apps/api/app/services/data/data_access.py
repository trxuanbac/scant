"""Shared validation for the existing spreadsheet API entry points."""
import json
import re
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from app.core.config import settings
from app.models.entities import Project, UploadedFile


async def owned_dataset(db, file_id, user):
    if user is None:
        raise HTTPException(401, 'Vui lòng đăng nhập để truy cập tệp đã lưu.')
    record = await db.scalar(select(UploadedFile).join(Project).where(
        UploadedFile.id == file_id, Project.user_id == user.id,
    ))
    if record is None:
        raise HTTPException(404, 'Không tìm thấy tệp dữ liệu.')
    return record


def safe_dataset_name(filename):
    name = Path((filename or 'dataset.xlsx').replace('\\', '/')).name
    if Path(name).suffix.lower() not in {'.xlsx', '.xlsm', '.xls', '.csv'}:
        raise HTTPException(422, 'Chỉ hỗ trợ XLSX, XLSM, XLS hoặc CSV.')
    return re.sub(r'[\x00-\x1f\x7f]', '_', name)[-180:]


def save_dataset(contents, filename, user_tag):
    name = safe_dataset_name(filename)
    if not contents or len(contents) > 50 * 1024 * 1024:
        raise HTTPException(413, 'Tệp phải có dữ liệu và không vượt quá 50MB.')
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Independent requests must not overwrite another user's or tab's workbook.
    path = settings.UPLOAD_DIR / f'preview_{uuid4().hex}_{name}'
    path.write_bytes(contents)
    return str(path)


def validated_highlight(cells, color):
    try:
        values = json.loads(cells) if cells.lstrip().startswith(('[', '{')) else cells.split(',')
    except (ValueError, TypeError):
        raise HTTPException(422, 'Danh sách ô không hợp lệ.')
    if not isinstance(values, list) or not 1 <= len(values) <= 50000:
        raise HTTPException(422, 'Chọn từ 1 đến 50.000 ô mỗi lần.')
    result = []
    for value in values:
        if not isinstance(value, str):
            raise HTTPException(422, 'Địa chỉ ô phải là chuỗi A1 hợp lệ.')
        value = value.strip().upper()
        match = re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]{0,6})', value)
        if not match:
            raise HTTPException(422, 'Địa chỉ ô không hợp lệ.')
        column = 0
        for char in match[1]:
            column = column * 26 + ord(char) - 64
        if column > 16384 or int(match[2]) > 1048576:
            raise HTTPException(422, 'Địa chỉ ô vượt giới hạn Excel.')
        result.append(value)
    clean_color = color.lstrip('#').upper()
    if not re.fullmatch(r'(?:[0-9A-F]{6}|[0-9A-F]{8})', clean_color):
        raise HTTPException(422, 'Màu phải là mã HEX 6 hoặc 8 ký tự.')
    return list(dict.fromkeys(result)), clean_color
