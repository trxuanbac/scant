from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import ImageAsset, Project, Report, User
from app.schemas.asset import (
    ImageAssetResponse,
    ImageQuerySuggestionRequest,
    ImportWebImageRequest,
    WebImageSearchRequest,
    WebImageSearchResponse,
)
from app.services.assets.image_service import ImageValidationError, image_service

router = APIRouter(prefix="/assets", tags=["assets"])


async def _ensure_project_owner(db: AsyncSession, project_id: str, current_user: User) -> Project:
    project = await db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _ensure_report_owner(db: AsyncSession, report_id: Optional[str], current_user: User) -> Optional[Report]:
    if not report_id:
        return None
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    project = await _ensure_project_owner(db, report.project_id, current_user)
    if report.project_id != project.id:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/images/upload", response_model=ImageAssetResponse)
async def upload_image_asset(
    project_id: str = Form(...),
    report_id: Optional[str] = Form(None),
    source_type: str = Form("upload"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_project_owner(db, project_id, current_user)
    if report_id:
        await _ensure_report_owner(db, report_id, current_user)

    data = await file.read()
    try:
        asset = await image_service.create_asset(
            db,
            project_id=project_id,
            report_id=report_id,
            user_id=current_user.id,
            file_name=file.filename or "image",
            data=data,
            source_type=source_type if source_type in {"upload", "paste", "drag_drop"} else "upload",
        )
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return image_service.response_for_asset(asset)


@router.get("/images/project/{project_id}", response_model=List[ImageAssetResponse])
async def list_project_images(
    project_id: str,
    report_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_project_owner(db, project_id, current_user)
    stmt = select(ImageAsset).where(ImageAsset.project_id == project_id)
    if report_id:
        stmt = stmt.where((ImageAsset.report_id == report_id) | (ImageAsset.report_id.is_(None)))
    stmt = stmt.order_by(ImageAsset.created_at.desc()).limit(200)
    res = await db.execute(stmt)
    return [image_service.response_for_asset(asset) for asset in res.scalars().all()]


@router.post("/images/search", response_model=WebImageSearchResponse)
async def search_web_images(
    req: WebImageSearchRequest,
    current_user: User = Depends(get_current_user),
):
    payload = await image_service.search_web_images(
        query=req.query,
        license_mode=req.license_mode,
        max_results=req.max_results,
    )
    return payload


@router.post("/images/import-web", response_model=ImageAssetResponse)
async def import_web_image(
    req: ImportWebImageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_project_owner(db, req.project_id, current_user)
    if req.report_id:
        await _ensure_report_owner(db, req.report_id, current_user)
    try:
        asset = await image_service.import_search_result(
            db,
            project_id=req.project_id,
            report_id=req.report_id,
            user_id=current_user.id,
            result={
                "imageUrl": str(req.image_url),
                "sourcePageUrl": str(req.source_page_url) if req.source_page_url else None,
                "title": req.title,
                "license": req.license,
                "attribution": req.attribution,
            },
        )
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Không thể tải và lưu ảnh từ web.") from exc

    return image_service.response_for_asset(asset)


@router.post("/images/suggest-queries")
async def suggest_image_queries(
    req: ImageQuerySuggestionRequest,
    current_user: User = Depends(get_current_user),
):
    return {
        "queries": image_service.suggest_queries(
            section_title=req.section_title,
            section_text=req.section_text,
            report_title=req.report_title,
            max_queries=req.max_queries,
        )
    }


@router.get("/images/{asset_id}", response_model=ImageAssetResponse)
async def get_image_asset(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(ImageAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Image not found")
    await _ensure_project_owner(db, asset.project_id, current_user)
    return image_service.response_for_asset(asset)


@router.get("/images/{asset_id}/content")
async def get_image_content(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(ImageAsset, asset_id)
    if not asset or not Path(asset.storage_path).exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(
        path=asset.storage_path,
        media_type=asset.mime_type,
        filename=asset.file_name,
    )
