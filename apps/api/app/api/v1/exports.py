import os
import re
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import User, Report, Project, ExportRecord, TemplateVersion, ImageAsset
from app.repositories.report_repo import report_repo, section_repo
from app.repositories.project_repo import project_repo
from app.repositories.source_repo import source_repo
from app.repositories.base import BaseRepository
from app.schemas.export import ExportRequest, ExportResponse
from app.api.deps import get_current_user, get_current_user_optional
from app.services.exports.docx_exporter import docx_exporter
from app.services.exports.pdf_exporter import pdf_exporter
from app.services.quality.grounding_guard import grounding_guard
from app.api.v1.templates import _docx_to_preview_html

router = APIRouter(prefix="/exports", tags=["exports"])
export_repo = BaseRepository[ExportRecord](ExportRecord)


def _mark_docx_as_review_draft(file_path: str, report_title: str) -> str:
    generated_path = Path(file_path)
    safe_title = re.sub(r"[^\w.-]+", "_", report_title, flags=re.UNICODE).strip("._")
    safe_title = safe_title[:80] or "bao_cao"
    unique_suffix = generated_path.stem.removeprefix("report_")
    draft_path = generated_path.with_name(
        f"BAN_NHAP_{safe_title}_{unique_suffix}{generated_path.suffix}"
    )
    generated_path.replace(draft_path)
    return str(draft_path)


async def _load_image_assets_for_export(db: AsyncSession, project_id: str, report_id: str):
    res = await db.execute(
        select(ImageAsset).where(
            ImageAsset.project_id == project_id,
            (ImageAsset.report_id == report_id) | (ImageAsset.report_id.is_(None)),
        )
    )
    return {asset.id: asset for asset in res.scalars().all()}


@router.post("/docx", response_model=ExportResponse)
async def export_docx(
    req: ExportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await report_repo.get(db, req.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    project = await project_repo.get(db, report.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    sections = await section_repo.get_by_report(db, report.id)
    sources = await source_repo.get_by_project(db, project.id)
    image_assets = await _load_image_assets_for_export(db, project.id, report.id)
    template_path = None
    if report.template_version_id:
      template_version = await BaseRepository[TemplateVersion](TemplateVersion).get(db, report.template_version_id)
      if template_version and template_version.file_path:
          template_path = template_version.file_path

    file_path = docx_exporter.generate_docx(
        report_title=report.title,
        topic_details=project.topic_details_json or {},
        sections=sections,
        sources=sources,
        document_settings=report.document_settings_json or {},
        include_cover=req.include_cover,
        include_toc=req.include_toc,
        include_references=req.include_references,
        citation_style=req.citation_style,
        template_path=template_path,
        image_assets=image_assets,
    )
    topic_context = " ".join(
        str(value)
        for value in [report.title, *(project.topic_details_json or {}).values()]
        if value
    )
    final_validation = grounding_guard.validate_docx(file_path, topic_text=topic_context)
    if not final_validation.get("valid") and not req.review_draft:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "File Word cuối chưa sạch, cần sửa trước khi xuất FINAL.",
                "validation": final_validation,
            },
        )

    if req.review_draft:
        file_path = _mark_docx_as_review_draft(file_path, report.title)

    filename = Path(file_path).name
    file_size = os.path.getsize(file_path)

    document_status = "review_draft" if req.review_draft else "final"
    document_label = "BAN_NHAP" if req.review_draft else "FINAL"

    record = await export_repo.create(db, obj_in={
        "report_id": report.id,
        "export_format": "docx",
        "file_path": file_path,
        "file_size": file_size,
        "settings_json": {
            **req.model_dump(),
            "document_label": document_label,
            "document_status": document_status,
            "review_required": not final_validation.get("valid", False),
            "validation": final_validation,
            "final_validation": final_validation,
        },
        "status": "completed",
    })

    return ExportResponse(
        id=record.id,
        report_id=report.id,
        export_format="docx",
        download_url=f"/api/v1/exports/download/{filename}",
        filename=(filename if req.review_draft else f"{report.title.replace(' ', '_')}.docx"),
        file_size=file_size,
        created_at=record.created_at,
    )


@router.post("/pdf", response_model=ExportResponse)
async def export_pdf(
    req: ExportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await report_repo.get(db, req.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    project = await project_repo.get(db, report.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    sections = await section_repo.get_by_report(db, report.id)
    sources = await source_repo.get_by_project(db, project.id)
    image_assets = await _load_image_assets_for_export(db, project.id, report.id)

    file_path = pdf_exporter.generate_pdf(
        report_title=report.title,
        topic_details=project.topic_details_json or {},
        sections=sections,
        sources=sources,
        citation_style=req.citation_style,
    )

    filename = Path(file_path).name
    file_size = os.path.getsize(file_path)

    record = await export_repo.create(db, obj_in={
        "report_id": report.id,
        "export_format": "pdf",
        "file_path": file_path,
        "file_size": file_size,
        "settings_json": req.model_dump(),
        "status": "completed",
    })

    return ExportResponse(
        id=record.id,
        report_id=report.id,
        export_format="pdf",
        download_url=f"/api/v1/exports/download/{filename}",
        filename=f"{report.title.replace(' ', '_')}.html",
        file_size=file_size,
        created_at=record.created_at,
    )


@router.get("/report/{report_id}/preview-html")
async def preview_report_as_template_html(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await report_repo.get(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    project = await project_repo.get(db, report.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    sections = await section_repo.get_by_report(db, report.id)
    sources = await source_repo.get_by_project(db, project.id)
    image_assets = await _load_image_assets_for_export(db, project.id, report.id)
    template_path = None
    if report.template_version_id:
        template_version = await BaseRepository[TemplateVersion](TemplateVersion).get(db, report.template_version_id)
        if template_version and template_version.file_path:
            template_path = template_version.file_path

    try:
        file_path = docx_exporter.generate_docx(
            report_title=report.title,
            topic_details=project.topic_details_json or {},
            sections=sections,
            sources=sources,
            document_settings=report.document_settings_json or {},
            include_cover=True,
            include_toc=True,
            include_references=True,
            citation_style="IEEE",
            template_path=template_path,
            image_assets=image_assets,
        )
        html_document = _docx_to_preview_html(file_path)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không thể dựng bản xem theo mẫu. "
                "Bạn vẫn có thể mở Studio để chỉnh sửa hoặc thử xuất DOCX lại. "
                f"Chi tiết kỹ thuật: {str(exc)[:240]}"
            ),
        )

    return {
        "report_id": report.id,
        "template_applied": bool(template_path),
        "download_url": f"/api/v1/exports/download/{Path(file_path).name}",
        "html_document": html_document,
    }


@router.get("/download/{file_name}")
async def download_export(file_name: str):
    file_path = settings.EXPORT_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    ext = file_path.suffix.lower()
    media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if ext == ".docx" else "text/html"

    return FileResponse(
        path=str(file_path),
        filename=file_name,
        media_type=media_type,
    )
