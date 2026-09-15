from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.entities import User, Project, UploadedFile
from app.api.deps import get_current_user, get_current_user_optional
from app.services.data.data_engine import data_engine
from app.services.data.spreadsheet_visual_engine import spreadsheet_visual_engine
from app.services.data.sheet_analysis_service import sheet_analysis_service
from app.services.data.spreadsheet_query_engine import spreadsheet_query_engine
from app.services.data.workbook_chat_service import workbook_chat_service
from app.services.data.workbook_scanner import workbook_scanner
from app.services.data.action_engine import spreadsheet_action_engine
from app.services.data.google_sheets_service import google_sheets_service
from app.services.data.url_dataset_loader import url_dataset_loader
from app.core.config import settings
from uuid import uuid4
from urllib.parse import urlencode
from app.services.storage.signed_url_service import signed_url_service
from app.services.data.data_access import owned_dataset, safe_dataset_name, save_dataset, validated_highlight
from app.services.data.analysis_source import resolve_analysis_source
from app.services.data.analysis_contracts import (
    AnalysisScopeError,
    bind_analysis_evidence,
    normalize_analysis_scope,
)
from app.services.data.analysis_session_service import get_or_create_session, record_exchange
from fastapi.responses import FileResponse

router = APIRouter(prefix="/data", tags=["data"])


def analysis_scope_or_422(raw_scope, source, *, sheet_name=None, selected_range=None):
    try:
        return normalize_analysis_scope(
            raw_scope,
            available_sheets=list(source.sheet_names),
            sheet_name=sheet_name,
            selected_range=selected_range,
        )
    except AnalysisScopeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def persist_analysis_exchange(db, user, source, scope, client_key, question, payload):
    bound = bind_analysis_evidence(
        payload,
        source_version=source.source_version,
        scope=scope,
    )
    if user is None:
        return bound
    session = await get_or_create_session(
        db,
        user,
        source.source_version,
        source.sheet_names,
        scope,
        client_key,
    )
    await record_exchange(db, session, question, bound)
    bound["analysis_session_id"] = session.id
    return bound


class AggregationRequest(BaseModel):
    file_id: str
    group_by: str
    metric_column: str
    aggregation: str = "sum"  # sum, mean, count, min, max
    top_n: int = 10


class ChartSpecRequest(BaseModel):
    file_id: str
    chart_type: str = "bar"  # bar, line, pie, donut, horizontal_bar, area
    group_by: str
    metric_column: str
    aggregation: str = "sum"
    title: Optional[str] = None


@router.post("/preview-upload")
async def preview_uploaded_dataset(
    file: Optional[UploadFile] = File(None),
    data_source_url: Optional[str] = Form(None),
    sheet_range: Optional[str] = Form(None),
    analysis_request: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    has_file = file is not None and bool(file.filename and file.filename.strip())
    url_str = (data_source_url or "").strip()

    if not has_file and not url_str:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng tải tệp dữ liệu từ máy hoặc dán link dữ liệu công khai."
        )

    source_mode = "file" if has_file else "url"
    source = await resolve_analysis_source(
        db,
        current_user,
        file=file if has_file else None,
        data_source_url=url_str if not has_file else None,
        sheet_range=sheet_range,
    )
    filename = source.source_version.display_name
    mime_type = source.source_version.mime_type
    tmp_path = source.path

    try:
        profile = data_engine.profile_dataset(str(tmp_path), sheet_range=sheet_range)
        visual_workbook = spreadsheet_visual_engine.extract_visual_workbook(str(tmp_path))
        selected_sheet_name, selected_cell_range = data_engine.parse_sheet_range(sheet_range)
        normalized_scope = analysis_scope_or_422(
            None,
            source,
            sheet_name=selected_sheet_name or (source.sheet_names[0] if selected_cell_range else None),
            selected_range=selected_cell_range,
        )
        initial_analysis = await sheet_analysis_service.analyze_sheet(str(tmp_path), sheet_name=selected_sheet_name)
        scanner_source_type = "google_sheets" if url_dataset_loader.is_google_sheets(url_str) else source_mode
        workbook_ctx = workbook_scanner.scan_workbook(
            file_path=str(tmp_path),
            source_type=scanner_source_type,
            source_url=url_str if source_mode == "url" else None,
            preferred_active_sheet=selected_sheet_name,
        )
        facts = profile.get("verified_facts", [])
        key_facts = facts[:30]
        return bind_analysis_evidence({
            "ok": True,
            "source_mode": source_mode,
            "source_url": url_str if source_mode == "url" else "",
            "sheet_range": sheet_range or "",
            "analysis_request": analysis_request or "",
            "file_name": filename,
            "mime_type": mime_type,
            "source_version": source.source_version.as_dict(),
            "sheet_count": profile.get("sheet_count"),
            "total_rows": profile.get("total_rows"),
            "total_columns": profile.get("total_columns"),
            "columns": profile.get("columns", []),
            "preview_rows": profile.get("preview_rows", []),
            "verified_facts": key_facts,
            "warnings": profile.get("warnings", []),
            "sheets": [
                {
                    "name": sheet.get("name"),
                    "row_count": sheet.get("row_count"),
                    "column_count": sheet.get("column_count"),
                    "columns": sheet.get("columns", [])[:80],
                    "records": sheet.get("records", [])[:100],
                    "statistics": sheet.get("statistics", {}),
                }
                for sheet in profile.get("sheets", [])[:10]
            ],
            "visual_workbook": visual_workbook,
            "initial_analysis": initial_analysis,
            "workbook_context": workbook_ctx,
        }, source_version=source.source_version, scope=normalized_scope)
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không thể đọc dữ liệu: {str(e)}")


@router.post("/analyze-sheet")
async def analyze_specific_sheet(
    file: Optional[UploadFile] = File(None),
    file_id: Optional[str] = Form(None),
    data_source_url: Optional[str] = Form(None),
    sheet_name: Optional[str] = Form(None),
    force_refresh: bool = Form(False),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    source = await resolve_analysis_source(
        db, current_user, file=file, file_id=file_id, data_source_url=data_source_url
    )

    try:
        normalized_scope = analysis_scope_or_422(
            None,
            source,
            sheet_name=sheet_name or source.sheet_names[0],
        )
        analysis = await sheet_analysis_service.analyze_sheet(
            file_path=str(source.path),
            sheet_name=sheet_name,
            force_refresh=force_refresh,
        )
        return bind_analysis_evidence(
            {"ok": True, "analysis": analysis},
            source_version=source.source_version,
            scope=normalized_scope,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi khi phân tích sheet: {str(e)}")


@router.post("/workbook-chat")
async def chat_with_workbook(
    file: Optional[UploadFile] = File(None),
    file_id: Optional[str] = Form(None),
    data_source_url: Optional[str] = Form(None),
    sheet_name: Optional[str] = Form(None),
    message: str = Form(...),
    selected_range: Optional[str] = Form(None),
    scope: Optional[str] = Form(None),
    conversation_id: Optional[str] = Form(None, max_length=1000),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    user_tag = str(current_user.id) if current_user else "guest"
    client_key = (conversation_id or "").strip() or uuid4().hex
    source = await resolve_analysis_source(
        db, current_user, file=file, file_id=file_id, data_source_url=data_source_url
    )

    try:
        normalized_scope = analysis_scope_or_422(
            scope,
            source,
            sheet_name=sheet_name,
            selected_range=selected_range,
        )
        response = await workbook_chat_service.chat(
            file_path=str(source.path),
            message=message,
            sheet_name=sheet_name,
            selected_range=normalized_scope.cell_range or selected_range,
            conversation_id=f"{user_tag}:{source.source_version.version}:{client_key}",
            scope=normalized_scope.as_legacy_dict(),
        )
        return await persist_analysis_exchange(
            db,
            current_user,
            source,
            normalized_scope,
            client_key,
            message,
            {"ok": True, **response},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi xử lý câu hỏi bảng tính: {str(e)}")


@router.post("/workbook-analysis-action")
async def run_workbook_analysis_action(
    file: Optional[UploadFile] = File(None),
    file_id: Optional[str] = Form(None),
    data_source_url: Optional[str] = Form(None),
    sheet_name: Optional[str] = Form(None),
    prompt: str = Form(...),
    selected_range: Optional[str] = Form(None),
    scope: Optional[str] = Form(None),
    highlight_color: Optional[str] = Form(None),
    conversation_id: Optional[str] = Form(None, max_length=1000),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    user_tag = str(current_user.id) if current_user else "guest"
    client_key = (conversation_id or "").strip() or uuid4().hex
    source = await resolve_analysis_source(
        db, current_user, file=file, file_id=file_id, data_source_url=data_source_url
    )

    try:
        normalized_scope = analysis_scope_or_422(
            scope,
            source,
            sheet_name=sheet_name,
            selected_range=selected_range,
        )
        response = await workbook_chat_service.analyze_action(
            file_path=str(source.path),
            prompt=prompt,
            sheet_name=sheet_name,
            selected_range=normalized_scope.cell_range or selected_range,
            conversation_id=f"{user_tag}:{source.source_version.version}:{client_key}",
            scope=normalized_scope.as_legacy_dict(),
            highlight_color=highlight_color,
            data_source_url=data_source_url,
            user=current_user,
            db=db,
        )
        return await persist_analysis_exchange(
            db,
            current_user,
            source,
            normalized_scope,
            client_key,
            prompt,
            {"ok": True, **response},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi chạy phân tích workbook: {str(e)}")


@router.post("/cross-file-compare")
async def cross_file_compare(
    file_1: Optional[UploadFile] = File(None),
    file_2: Optional[UploadFile] = File(None),
    file_id_1: Optional[str] = Form(None),
    file_id_2: Optional[str] = Form(None),
    sheet1_name: Optional[str] = Form(None),
    sheet2_name: Optional[str] = Form(None),
    key_column_1: Optional[str] = Form(None),
    key_column_2: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    user_tag = str(current_user.id) if current_user else "guest"

    path1 = None
    if file_id_1:
        f1 = await owned_dataset(db, file_id_1, current_user)
        if f1 and Path(f1.file_path).exists():
            path1 = f1.file_path
    elif file_1 and file_1.filename:
        c1 = await file_1.read(50 * 1024 * 1024 + 1)

        path1 = save_dataset(c1, file_1.filename, user_tag)

    path2 = None
    if file_id_2:
        f2 = await owned_dataset(db, file_id_2, current_user)
        if f2 and Path(f2.file_path).exists():
            path2 = f2.file_path
    elif file_2 and file_2.filename:
        c2 = await file_2.read(50 * 1024 * 1024 + 1)

        path2 = save_dataset(c2, file_2.filename, user_tag)

    if not path1 or not path2:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp đầy đủ 2 file để đối chiếu.")

    try:
        res = spreadsheet_query_engine.cross_file_compare(
            file_path_1=path1,
            sheet1_name=sheet1_name,
            file_path_2=path2,
            sheet2_name=sheet2_name,
            key_column_1=key_column_1,
            key_column_2=key_column_2,
        )
        return {"ok": True, **res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi đối chiếu 2 file: {str(e)}")


@router.post("/action-undo")
async def undo_spreadsheet_action(
    session_id: str = Form("default"),
    spreadsheet_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session_id = f"{current_user.id}:{session_id}"
    res = spreadsheet_action_engine.undo_last_action(session_id=session_id)
    # Also attempt Google Sheets undo if user token is available
    token, _ = await google_sheets_service.get_valid_access_token(user=current_user, db=db)
    if token:
        gs_undo = await google_sheets_service.undo_highlight(session_id=session_id, access_token=token)
        res["google_undo"] = gs_undo
    return res


@router.post("/google-sync-retry")
async def retry_google_sheets_sync(
    spreadsheet_id: str = Form(...),
    sheet_name: str = Form("Sheet1"),
    cells: str = Form(...),  # JSON list string or comma-separated
    color_hex: str = Form("#FEF08A"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Direct 1-click retry to sync cell formatting to Google Sheets."""
    clean_id = google_sheets_service.extract_spreadsheet_id(spreadsheet_id) or spreadsheet_id
    token, err = await google_sheets_service.get_valid_access_token(user=current_user, db=db)
    if not token:
        return {
            "ok": False,
            "synced_to_google_sheets": False,
            "verified_on_google_sheets": False,
            "error": "Ứng dụng chưa có quyền chỉnh sửa Google Sheets. Vui lòng cấp quyền (Google Sheets Write Scope) để đồng bộ.",
            "requires_auth": True,
        }

    cell_list, color_hex = validated_highlight(cells, color_hex)

    res = await google_sheets_service.highlight_cells(
        spreadsheet_id=clean_id,
        sheet_name=sheet_name,
        cell_addresses=cell_list,
        color_hex=color_hex,
        access_token=token,
    )
    return {"ok": res.get("success", False), **res}


@router.post("/clear-google-highlights")
async def clear_google_highlights(
    spreadsheet_id: str = Form(...),
    sheet_name: str = Form("Sheet1"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Restores original formatting on Google Sheets for the active sheet."""
    clean_id = google_sheets_service.extract_spreadsheet_id(spreadsheet_id) or spreadsheet_id
    token, _ = await google_sheets_service.get_valid_access_token(user=current_user, db=db)
    if not token:
        return {"ok": False, "error": "Thiếu quyền truy cập Google Sheets."}

    res = await google_sheets_service.clear_all_highlights(
        spreadsheet_id=clean_id,
        sheet_name=sheet_name,
        access_token=token,
    )
    return res


@router.post("/apply-modifications")
async def apply_workbook_modifications(
    file: Optional[UploadFile] = File(None),
    file_id: Optional[str] = Form(None),
    data_source_url: Optional[str] = Form(None),
    sheet_name: Optional[str] = Form("Sheet1"),
    cells: str = Form(...),  # JSON list string e.g. '["H11","I25"]' or comma-separated
    color_hex: str = Form("FFFF00"),
    sync_google: bool = Form(False),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    target_path = None
    orig_filename = "workbook.xlsx"
    user_tag = str(current_user.id) if current_user else "guest"
    if file_id:
        f = await owned_dataset(db, file_id, current_user)
        if f and Path(f.file_path).exists():
            target_path = f.file_path
            orig_filename = f.filename
    elif file is not None and bool(file.filename and file.filename.strip()):
        contents = await file.read(50 * 1024 * 1024 + 1)

        orig_filename = file.filename
        target_path = save_dataset(contents, file.filename, user_tag)
    elif data_source_url and data_source_url.strip():
        contents, filename, mime_type = await url_dataset_loader.load(data_source_url.strip())

        orig_filename = filename
        target_path = save_dataset(contents, filename, user_tag)

    if not target_path or not Path(target_path).exists():
        raise HTTPException(status_code=400, detail="Không tìm thấy file để áp dụng chỉnh sửa.")

    cell_list, color_hex = validated_highlight(cells, color_hex)

    # Validate the reviewed sheet before either local or remote writes.
    import openpyxl
    try:
        workbook = openpyxl.load_workbook(target_path, read_only=True)
        try:
            if sheet_name not in workbook.sheetnames:
                raise HTTPException(422, "Sheet không tồn tại. Hãy chọn lại sheet.")
        finally:
            workbook.close()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Không đọc được workbook để xác nhận thay đổi.")

    # Check and sync to Google Sheets if document is from Google Sheets
    google_sync_res = {
        "is_google_sheet": False,
        "spreadsheet_id": None,
        "synced_to_google_sheets": False,
        "verified_on_google_sheets": False,
        "google_sync_error": None,
    }
    spreadsheet_id = google_sheets_service.extract_spreadsheet_id(data_source_url)
    if spreadsheet_id and cell_list and sync_google:
        google_sync_res["is_google_sheet"] = True
        google_sync_res["spreadsheet_id"] = spreadsheet_id
        token, token_err = await google_sheets_service.get_valid_access_token(user=current_user, db=db)
        if token:
            gs_out = await google_sheets_service.highlight_cells(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name or "Sheet1",
                cell_addresses=cell_list,
                color_hex=color_hex,
                access_token=token,
            )
            google_sync_res["synced_to_google_sheets"] = gs_out.get("synced_to_google_sheets", False)
            google_sync_res["verified_on_google_sheets"] = gs_out.get("verified_on_google_sheets", False)
            google_sync_res["google_sync_error"] = gs_out.get("error")
        else:
            google_sync_res["google_sync_error"] = (
                "Ứng dụng chưa có quyền chỉnh sửa Google Sheets. Vui lòng cấp quyền chỉnh sửa để đồng bộ."
            )

    try:
        out_stem = Path(safe_dataset_name(orig_filename)).stem
        out_filename = f"{out_stem}_highlighted.xlsx"
        out_path = str(settings.UPLOAD_DIR / f"modified_{uuid4().hex}_{out_filename}")

        spreadsheet_query_engine.apply_highlights_to_workbook(
            file_path=target_path,
            sheet_name=sheet_name or "Sheet1",
            cell_addresses=cell_list,
            color_hex=color_hex.replace("#", "").upper(),
            output_path=out_path,
        )

        return {
            "ok": True,
            "modified_file_name": out_filename,
            "highlighted_count": len(cell_list),
            "download_url": "/api/v1/data/download-file?" + urlencode({"filename": Path(out_path).name, "token": signed_url_service.generate_signed_token("data/" + Path(out_path).name, user_tag, 900)}),
            "google_sync": google_sync_res,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi khi lưu chỉnh sửa vào XLSX: {str(e)}")


@router.get("/download-file")
async def download_data_file(
    filename: str,
    token: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    safe_name = Path(filename).name
    valid, key, _ = signed_url_service.verify_and_decode_token(token or "")
    if not valid or key != "data/" + safe_name or filename != safe_name:
        raise HTTPException(403, "Liên kết tải tệp không hợp lệ hoặc đã hết hạn.")
    file_path = settings.UPLOAD_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File không tồn tại hoặc đã hết hạn.")

    return FileResponse(
        path=str(file_path),
        filename=safe_name.split("_", 2)[-1] if "_" in safe_name else safe_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/profile/{file_id}")
async def profile_file_dataset(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    source = await resolve_analysis_source(db, current_user, file_id=file_id)

    try:
        normalized_scope = analysis_scope_or_422(None, source)
        profile = data_engine.profile_dataset(str(source.path))
        visual_workbook = spreadsheet_visual_engine.extract_visual_workbook(str(source.path))
        profile["file_id"] = source.source_version.source_id
        profile["file_name"] = source.source_version.display_name
        profile["original_name"] = source.source_version.display_name
        profile["source_version"] = source.source_version.as_dict()
        profile["visual_workbook"] = visual_workbook
        return bind_analysis_evidence(
            profile,
            source_version=source.source_version,
            scope=normalized_scope,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error analyzing dataset: {str(e)}")


@router.post("/aggregate")
async def aggregate_dataset(
    req: AggregationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    f = await owned_dataset(db, req.file_id, current_user)
    if not f or not Path(f.file_path).exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        return data_engine.aggregate_data(
            file_path=f.file_path,
            group_by=req.group_by,
            metric_column=req.metric_column,
            aggregation=req.aggregation,
            top_n=req.top_n,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Aggregation error: {str(e)}")


@router.post("/chart-spec")
async def create_chart_specification(
    req: ChartSpecRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    f = await owned_dataset(db, req.file_id, current_user)
    if not f or not Path(f.file_path).exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        return data_engine.build_chart_specification(
            file_path=f.file_path,
            chart_type=req.chart_type,
            group_by=req.group_by,
            metric_column=req.metric_column,
            aggregation=req.aggregation,
            title=req.title,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Chart building error: {str(e)}")


# Phase U17: Connectors, Mapping, Dependency Graph

class ConnectorTestRequest(BaseModel):
    connector_type: str  # csv, postgresql, mysql, rest
    config: Dict[str, Any]


class SmartMappingRequest(BaseModel):
    columns: List[str]


class SaveMappingRequest(BaseModel):
    columns: List[str]
    mapping: Dict[str, str]


class RegisterDependencyRequest(BaseModel):
    report_id: str
    source_node: str  # dataset_id or kpi_id
    target_node: str  # chart_id or section_id


class InvalidateDependencyRequest(BaseModel):
    report_id: str
    source_node: str


@router.post("/connectors/test")
async def test_connector(
    req: ConnectorTestRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.data.connectors import get_connector
    connector = get_connector(req.connector_type, req.config)
    return await connector.test_connection()


@router.post("/connectors/schema")
async def get_connector_schema(
    req: ConnectorTestRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.data.connectors import get_connector
    connector = get_connector(req.connector_type, req.config)
    return await connector.get_schema()


@router.post("/mapping/infer")
async def infer_canonical_mapping(
    req: SmartMappingRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.data.smart_mapping_service import smart_mapping_service
    mapping = smart_mapping_service.infer_canonical_mapping(req.columns)
    fingerprint = smart_mapping_service.compute_fingerprint(req.columns)
    return {"fingerprint": fingerprint, "mapping": mapping}


@router.post("/mapping/save")
async def save_canonical_mapping(
    req: SaveMappingRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.data.smart_mapping_service import smart_mapping_service
    fp = smart_mapping_service.save_custom_mapping(req.columns, req.mapping)
    return {"status": "saved", "fingerprint": fp}


@router.post("/dependency/register")
async def register_dependency(
    req: RegisterDependencyRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.data.dependency_graph_service import dependency_graph_service
    dependency_graph_service.register_dependency(req.report_id, req.source_node, req.target_node)
    return {"status": "registered", "source": req.source_node, "target": req.target_node}


@router.post("/dependency/invalidate")
async def invalidate_dependency(
    req: InvalidateDependencyRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.data.dependency_graph_service import dependency_graph_service
    stale_nodes = dependency_graph_service.invalidate_source(req.report_id, req.source_node)
    return {"report_id": req.report_id, "stale_nodes": list(stale_nodes)}
