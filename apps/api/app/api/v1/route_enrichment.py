"""Download a verified, enriched copy of a logistics route workbook."""

import io
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user_optional
from app.core.config import settings
from app.services.data.google_routes import GoogleRoutesClient, RoutesProviderError
from app.services.data.route_enrichment import enrich_workbook, load_reference_points
from app.services.data.url_dataset_loader import url_dataset_loader


router = APIRouter(prefix="/data/route-enrichment", tags=["data"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _is_looker_report(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in {"datastudio.google.com", "lookerstudio.google.com"} or (
        host == "lookerstudio.googleusercontent.com"
    )


def _mapped_looker_source(url: str) -> str:
    if not _is_looker_report(url):
        return ""
    parts = urlparse(url).path.strip("/").split("/")
    report_position = next((index for index, part in enumerate(parts) if part == "reporting"), -1)
    report_id = parts[report_position + 1] if 0 <= report_position < len(parts) - 1 else ""
    if report_id and report_id == settings.ROUTE_LOOKER_REPORT_ID.strip():
        return settings.ROUTE_LOOKER_SOURCE_URL.strip()
    return ""


@router.get("/status")
async def route_enrichment_status(_user=Depends(get_current_user_optional)):
    return {
        "maps_configured": bool(settings.GOOGLE_MAPS_ROUTES_API_KEY.strip()),
        "supported_looker_report_id": settings.ROUTE_LOOKER_REPORT_ID.strip() if settings.ROUTE_LOOKER_SOURCE_URL.strip() else "",
        "accepted_sources": ["public_google_sheet", "public_csv", "xlsx_reference_upload"],
    }


@router.post("/export")
async def export_enriched_routes(
    file: UploadFile = File(...),
    source_url: str = Form(...),
    reference_file: UploadFile | None = File(None),
    _user=Depends(get_current_user_optional),
):
    source_url = source_url.strip()
    if not source_url or urlparse(source_url).scheme != "https":
        raise HTTPException(422, "Vui lòng nhập link nguồn HTTPS hợp lệ.")
    mapped_source = _mapped_looker_source(source_url)
    if _is_looker_report(source_url) and reference_file is None and not mapped_source:
        raise HTTPException(
            422,
            "Link Looker Studio là trang báo cáo, không phải bảng tọa độ. Hãy xuất biểu đồ HUB thành CSV/XLSX và đính kèm, hoặc dán link Google Sheet/CSV gốc.",
        )
    if not settings.GOOGLE_MAPS_ROUTES_API_KEY.strip():
        raise HTTPException(503, "Máy chủ chưa cấu hình GOOGLE_MAPS_ROUTES_API_KEY và bật Routes API/billing.")
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(422, "File lộ trình phải là Excel .xlsx.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File Excel vượt giới hạn 20 MB.")
    try:
        if reference_file:
            reference_name = Path(reference_file.filename or "").name
            reference_content = await reference_file.read(MAX_UPLOAD_BYTES + 1)
            if len(reference_content) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "Bảng tọa độ vượt giới hạn 20 MB.")
        else:
            reference_content, reference_name, _ = await url_dataset_loader.load(mapped_source or source_url)
        points = load_reference_points(reference_content, reference_name)
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=8.0)) as http_client:
            routes = GoogleRoutesClient(settings.GOOGLE_MAPS_ROUTES_API_KEY, http_client)
            output, summary = await enrich_workbook(content, points, routes.compute_distance_meters, source_url)
    except HTTPException:
        raise
    except RoutesProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, "Không thể đọc file Excel hoặc bảng tọa độ hợp lệ.") from exc
    download_name = "Lo_trinh_Google_Maps_da_kiem_tra.xlsx"
    counts = {
        "X-Routes-Total": summary.total,
        "X-Routes-Completed": summary.completed,
        "X-Routes-Missing-Waypoint": summary.missing_waypoint,
        "X-Routes-Maps-Failed": summary.maps_failed,
        "X-Routes-Round-Trips": summary.round_trips,
        "X-Routes-Large-Difference": summary.large_difference,
        "X-Routes-Missing-Links": summary.missing_links,
        "X-Routes-Validation-Failed": summary.validation_failed,
    }
    return StreamingResponse(
        io.BytesIO(output),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(download_name)}",
            **{name: str(value) for name, value in counts.items()},
            "Access-Control-Expose-Headers": "Content-Disposition, " + ", ".join(counts),
        },
    )
