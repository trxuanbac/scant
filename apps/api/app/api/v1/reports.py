import asyncio
import base64
import html
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.entities import User, Project, Report, ReportSection, TemplateVersion, Job, UploadedFile
from app.repositories.base import BaseRepository
from app.repositories.project_repo import project_repo
from app.repositories.report_repo import report_repo, section_repo
from app.schemas.report import (
    ReportCreate, ReportUpdate, ReportResponse, ReportDetailResponse,
    ReportSectionCreate, ReportSectionUpdate, ReportSectionResponse, OutlineItem
)
from app.api.deps import get_current_user
from app.core.config import settings
from app.services.data.data_access import owned_dataset

router = APIRouter(prefix="/reports", tags=["reports"])


async def _ensure_report_owner(db: AsyncSession, report: Report, current_user: User) -> Project:
    project = await project_repo.get(db, report.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Report not found")
    return project


async def _ensure_section_owner(db: AsyncSession, section: ReportSection, current_user: User) -> Report:
    report = await report_repo.get(db, section.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Section not found")
    await _ensure_report_owner(db, report, current_user)
    return report


async def _ensure_job_owner(db: AsyncSession, job: Job, current_user: User) -> Project:
    project = await project_repo.get(db, job.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return project


async def _resolve_stored_dataset_source(
    db: AsyncSession,
    current_user: User,
    dataset_file_id: str,
) -> tuple[UploadedFile, Path]:
    record = await owned_dataset(db, dataset_file_id, current_user)
    stored_path = Path(record.file_path).resolve()
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    try:
        stored_path.relative_to(upload_root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp dữ liệu.")
    if not stored_path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp dữ liệu.")
    if stored_path.suffix.lower() not in {".xlsx", ".xlsm", ".xls", ".csv"}:
        raise HTTPException(status_code=422, detail="Tệp đã chọn không phải dữ liệu bảng tính được hỗ trợ.")
    if stored_path.stat().st_size > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Tệp vượt quá giới hạn dung lượng 50MB.")
    return record, stored_path


async def _resolve_template_version_id(db: AsyncSession, template_id: Optional[str]) -> Optional[str]:
    if not template_id or template_id.startswith("external_"):
        return None
    existing_version = await BaseRepository[TemplateVersion](TemplateVersion).get(db, template_id)
    if existing_version:
        return existing_version.id
    stmt = (
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template_id)
        .order_by(TemplateVersion.version_number.desc(), TemplateVersion.created_at.desc())
    )
    res = await db.execute(stmt)
    version = res.scalars().first()
    return version.id if version else None


def _clean_generated_report_title(prompt: str, suggested_title: Optional[str]) -> str:
    """Keep project/report titles as a real topic, not a whole chat answer."""
    candidates: List[str] = []
    text = (prompt or "").strip()
    title = (suggested_title or "").strip()
    if title:
        candidates.append(title)

    topic_patterns = [
        r"(?:đề\s*tài|de\s*tai|topic|chủ\s*đề|chu\s*de)\s*[:：]\s*[\"“”']?(.+)",
        r"[\"“”']([^\"“”']{12,180})[\"“”']",
    ]
    for pattern in topic_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidates.insert(0, match.group(1).strip())

    if text:
        candidates.append(text)

    stop_markers = [
        "\n",
        "Nếu bạn",
        "Neu ban",
        "tôi gợi ý",
        "toi goi y",
        "yêu cầu",
        "yeu cau",
        "số trang",
        "so trang",
        "khoảng",
        "khoang",
    ]
    for candidate in candidates:
        clean = re.sub(r"\s+", " ", candidate).strip(" .,:;“”\"'")
        for marker in stop_markers:
            idx = clean.lower().find(marker.lower())
            if idx > 8:
                clean = clean[:idx].strip(" .,:;“”\"'")
        clean = re.sub(r"^(đề\s*tài|de\s*tai|topic|chủ\s*đề|chu\s*de)\s*[:：]\s*", "", clean, flags=re.IGNORECASE)
        if 8 <= len(clean) <= 180:
            return clean
    return (title or text[:80] or "Báo cáo mới").strip()


def _looks_like_generic_data_task_title(title: str) -> bool:
    lower = (title or "").strip().lower()
    return (
        lower.startswith(("tác vụ:", "task:", "module:", "mô-đun:"))
        or "phân tích dữ liệu từ file excel/csv" in lower
        or "analyze the uploaded excel/csv dataset" in lower
        or "dataset analysis from spreadsheet files" in lower
    )


def _thumbnail_lines(report: Report, sections: List[ReportSection], max_lines: int = 13) -> List[str]:
    lines = [report.title]
    for section in sections:
        if section.title:
            lines.append(section.title)
        for raw_line in (section.plain_text or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if line:
                lines.extend(textwrap.wrap(line, width=64)[:2])
        if len(lines) >= max_lines:
            break
    return [line[:92] for line in lines[:max_lines]]


def _build_report_thumbnail_data_url(report: Report, sections: List[ReportSection]) -> str:
    lines = _thumbnail_lines(report, sections)
    type_label = html.escape((report.report_type or "DOCUMENT").upper())
    title = html.escape(report.title[:72])
    rows = []
    y = 178
    for index, line in enumerate(lines[1:] or ["Tài liệu này chưa có nội dung xem trước."]):
        escaped = html.escape(line)
        weight = "700" if index == 0 else "400"
        size = 18 if index == 0 else 14
        fill = "#111827" if index == 0 else "#475569"
        rows.append(f'<text x="72" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}">{escaped}</text>')
        y += 28 if index == 0 else 22

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="420" height="560" viewBox="0 0 420 560">
  <rect width="420" height="560" rx="18" fill="#f8fafc"/>
  <rect x="38" y="26" width="344" height="508" rx="10" fill="#ffffff" stroke="#dbe3ef" stroke-width="2"/>
  <rect x="72" y="66" width="112" height="24" rx="8" fill="#eef2ff"/>
  <text x="84" y="83" font-size="12" font-weight="800" fill="#4f46e5">{type_label}</text>
  <text x="72" y="126" font-size="22" font-weight="800" fill="#0f172a">{title}</text>
  <line x1="72" y1="148" x2="348" y2="148" stroke="#e2e8f0" stroke-width="2"/>
  {''.join(rows)}
  <rect x="72" y="444" width="84" height="42" rx="6" fill="#eef2ff" stroke="#c7d2fe"/>
  <rect x="168" y="444" width="84" height="42" rx="6" fill="#ecfdf5" stroke="#bbf7d0"/>
  <rect x="264" y="444" width="84" height="42" rx="6" fill="#f8fafc" stroke="#e2e8f0"/>
  <text x="72" y="516" font-size="12" font-weight="700" fill="#64748b">{len(sections)} mục · {sum(section.word_count or 0 for section in sections)} từ</text>
</svg>'''
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


async def _compare_dataset_with_existing_for_auto_create(
    db: AsyncSession,
    user_id: str,
    profile: Dict[str, Any],
    current_file_id: str,
) -> Dict[str, Any]:
    from app.services.data.data_engine import data_engine

    stmt = (
        select(UploadedFile)
        .join(Project, UploadedFile.project_id == Project.id)
        .where(
            Project.user_id == user_id,
            UploadedFile.file_type == "excel",
            UploadedFile.id != current_file_id,
        )
        .order_by(UploadedFile.created_at.asc())
    )
    res = await db.execute(stmt)
    best_file = None
    best_result = None
    for existing in res.scalars().all():
        existing_profile = (existing.metadata_json or {}).get("dataset_profile")
        if not existing_profile:
            continue
        result = data_engine.compare_dataset_profiles(profile, existing_profile)
        if best_result is None or result["similarity_score"] > best_result["similarity_score"]:
            best_result = result
            best_file = existing

    if best_file and best_result and best_result["status"] in {"duplicate", "similar"}:
        primary_meta = best_file.metadata_json or {}
        primary_comparison = primary_meta.get("dataset_comparison") or {}
        group_id = primary_comparison.get("dataset_group_id") or f"dataset-group-{best_file.id}"
        if not primary_comparison.get("dataset_group_id"):
            await BaseRepository[UploadedFile](UploadedFile).update(db, db_obj=best_file, obj_in={
                "metadata_json": {
                    **primary_meta,
                    "dataset_comparison": {
                        **primary_comparison,
                        "dataset_group_id": group_id,
                        "dataset_role": "primary",
                        "comparison_status": "primary",
                        "similarity_score": 1.0,
                    },
                }
            })
        return {
            **best_result,
            "dataset_group_id": group_id,
            "dataset_role": "similar",
            "comparison_status": best_result["status"],
            "primary_file_id": best_file.id,
            "primary_file_name": best_file.original_name,
        }

    return {
        "status": "primary",
        "comparison_status": "primary",
        "similarity_score": 1.0,
        "schema_match": False,
        "schema_signature": data_engine.dataset_schema_signature(profile),
        "row_signature": data_engine.dataset_row_signature(profile),
        "dataset_group_id": f"dataset-group-{current_file_id}",
        "dataset_role": "primary",
    }


@router.get("", response_model=List[ReportResponse])
async def list_reports(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Report)
        .join(Project, Report.project_id == Project.id)
        .where(Project.user_id == current_user.id)
        .order_by(Report.updated_at.desc())
    )
    res = await db.execute(stmt)
    return [ReportResponse.model_validate(r) for r in res.scalars().all()]


@router.post("", response_model=ReportDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    report_in: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await project_repo.get(db, report_in.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    settings = report_in.document_settings or {
        "paper": "A4",
        "font_family": "Times New Roman",
        "font_size": 13,
        "line_spacing": 1.5,
        "margins": {"top": 20, "bottom": 20, "left": 30, "right": 20},
        "citation_style": "IEEE"
    }

    report = await report_repo.create(db, obj_in={
        "project_id": report_in.project_id,
        "template_version_id": await _resolve_template_version_id(db, report_in.template_version_id),
        "title": report_in.title,
        "report_type": report_in.report_type,
        "status": "drafting",
        "revision": 1,
        "document_settings_json": settings,
    })

    # If outline is provided, populate report sections
    sections_created: List[ReportSection] = []
    global_pos = 0

    if report_in.outline:
        for parent_item in report_in.outline:
            global_pos += 1
            # Initial placeholder Tiptap structure
            parent_tiptap = {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": parent_item.level},
                        "content": [{"type": "text", "text": parent_item.title}]
                    },
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": f"Nội dung cho {parent_item.title}..."}]
                    }
                ]
            }

            parent_sec = await section_repo.create(db, obj_in={
                "report_id": report.id,
                "parent_id": None,
                "title": parent_item.title,
                "position": global_pos,
                "level": parent_item.level,
                "section_number": parent_item.section_number,
                "status": "planned",
                "content_json": parent_tiptap,
                "plain_text": f"{parent_item.title}\n\nNội dung cho {parent_item.title}...",
                "word_count": len(f"{parent_item.title} Nội dung".split()),
                "structured_summary_json": {}
            })
            sections_created.append(parent_sec)

            for child_item in parent_item.children:
                global_pos += 1
                child_tiptap = {
                    "type": "doc",
                    "content": [
                        {
                            "type": "heading",
                            "attrs": {"level": child_item.level},
                            "content": [{"type": "text", "text": child_item.title}]
                        },
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": f"Nội dung chi tiết cho mục {child_item.title}..."}]
                        }
                    ]
                }
                child_sec = await section_repo.create(db, obj_in={
                    "report_id": report.id,
                    "parent_id": parent_sec.id,
                    "title": child_item.title,
                    "position": global_pos,
                    "level": child_item.level,
                    "section_number": child_item.section_number,
                    "status": "planned",
                    "content_json": child_tiptap,
                    "plain_text": f"{child_item.title}\n\nNội dung chi tiết cho mục {child_item.title}...",
                    "word_count": len(f"{child_item.title} Nội dung chi tiết".split()),
                    "structured_summary_json": {}
                })
                sections_created.append(child_sec)

    return ReportDetailResponse(
        id=report.id,
        project_id=report.project_id,
        template_version_id=report.template_version_id,
        title=report.title,
        report_type=report.report_type,
        status=report.status,
        revision=report.revision,
        document_settings_json=report.document_settings_json,
        created_at=report.created_at,
        updated_at=report.updated_at,
        sections=[ReportSectionResponse.model_validate(s) for s in sections_created],
        total_words=sum(s.word_count for s in sections_created),
        sources_count=0,
        citations_count=0,
    )


@router.get("/{report_id}", response_model=ReportDetailResponse)
async def get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await report_repo.get_with_sections(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    project = await project_repo.get(db, report.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Report not found")

    sections = await section_repo.get_by_report(db, report_id)
    from app.repositories.source_repo import source_repo
    sources = await source_repo.get_by_project(db, project.id)

    return ReportDetailResponse(
        id=report.id,
        project_id=report.project_id,
        template_version_id=report.template_version_id,
        title=report.title,
        report_type=report.report_type,
        status=report.status,
        revision=report.revision,
        document_settings_json=report.document_settings_json,
        created_at=report.created_at,
        updated_at=report.updated_at,
        sections=[ReportSectionResponse.model_validate(s) for s in sections],
        total_words=sum(s.word_count for s in sections),
        sources_count=len(sources),
        citations_count=0,
    )


@router.get("/{report_id}/thumbnail")
async def get_report_thumbnail(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await report_repo.get(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await _ensure_report_owner(db, report, current_user)
    sections = await section_repo.get_by_report(db, report_id)
    return {
        "report_id": report.id,
        "mime_type": "image/svg+xml",
        "image_data_url": _build_report_thumbnail_data_url(report, sections),
    }


@router.get("/{report_id}/quality-audit")
async def audit_report_quality(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.quality.report_quality_repair_service import report_quality_repair_service

    report = await report_repo.get(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    project = await _ensure_report_owner(db, report, current_user)
    sections = await section_repo.get_by_report(db, report_id)
    return report_quality_repair_service.audit(report, project, sections)


@router.get("/{report_id}/grounding-debug")
async def report_grounding_debug(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await report_repo.get(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await _ensure_report_owner(db, report, current_user)
    sections = await section_repo.get_by_report(db, report_id)
    from app.services.quality.grounding_guard import grounding_guard

    validations = [
        ((sec.structured_summary_json or {}).get("grounding") or {}).get("validation", {})
        for sec in sections
        if ((sec.structured_summary_json or {}).get("grounding") or {}).get("validation")
    ]
    return {
        "report_id": report.id,
        "status": report.status,
        "final_quality_gate": (report.document_settings_json or {}).get("grounding_gate"),
        "readiness_score": grounding_guard.readiness_score(validations),
        "sections": [
            {
                "id": sec.id,
                "title": sec.title,
                "status": sec.status,
                "facts_used": ((sec.structured_summary_json or {}).get("grounding") or {}).get("facts_used", []),
                "source_ranges": ((sec.structured_summary_json or {}).get("grounding") or {}).get("source_ranges", []),
                "validation": ((sec.structured_summary_json or {}).get("grounding") or {}).get("validation", {}),
                "repair_count": ((sec.structured_summary_json or {}).get("grounding") or {}).get("repair_count", 0),
            }
            for sec in sections
        ],
    }


@router.post("/{report_id}/quality-repair")
async def repair_report_quality(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.quality.report_quality_repair_service import report_quality_repair_service

    report = await report_repo.get(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    project = await _ensure_report_owner(db, report, current_user)
    sections = await section_repo.get_by_report(db, report_id)
    return await report_quality_repair_service.repair(db, report, project, sections)


@router.post("/{report_id}/sections/{section_id}/quality-repair")
async def repair_report_section_quality(
    report_id: str,
    section_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.quality.report_quality_repair_service import report_quality_repair_service

    report = await report_repo.get(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    project = await _ensure_report_owner(db, report, current_user)
    sections = await section_repo.get_by_report(db, report_id)
    try:
        return await report_quality_repair_service.repair_section(db, report, project, sections, section_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Section not found")


@router.put("/sections/{section_id}", response_model=ReportSectionResponse)
async def update_section(
    section_id: str,
    section_in: ReportSectionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    section = await section_repo.get(db, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    await _ensure_section_owner(db, section, current_user)

    update_dict = section_in.model_dump(exclude_unset=True)
    if "plain_text" in update_dict and "word_count" not in update_dict:
        update_dict["word_count"] = len((update_dict["plain_text"] or "").split())

    updated = await section_repo.update(db, db_obj=section, obj_in=update_dict)
    return ReportSectionResponse.model_validate(updated)


@router.post("/{report_id}/insert-analysis-finding")
async def insert_analysis_finding(
    report_id: str,
    title: str = Form("Kết quả Phân tích Dữ liệu"),
    summary: str = Form(""),
    table_data: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Inserts a structured Excel / data analysis finding directly as a formatted section into a DOCX report."""
    report = await report_repo.get(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await _ensure_report_owner(db, report, current_user)

    existing_sections = await section_repo.get_by_report_id(db, report.id)
    new_position = len(existing_sections) + 1

    paragraphs: List[Dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 2},
            "content": [{"type": "text", "text": title}],
        }
    ]

    if summary.strip():
        for line in summary.strip().split("\n"):
            if line.strip():
                paragraphs.append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": line.strip()}],
                })

    tiptap_doc = {
        "type": "doc",
        "content": paragraphs,
    }

    sec = await section_repo.create(db, obj_in={
        "report_id": report.id,
        "parent_id": None,
        "title": title,
        "position": new_position,
        "level": 2,
        "section_number": f"{new_position}",
        "status": "completed",
        "content_json": tiptap_doc,
        "plain_text": f"{title}\n\n{summary}",
        "word_count": len(f"{title} {summary}".split()),
        "structured_summary_json": {"source": "excel_analysis_workspace"},
    })

    return {
        "ok": True,
        "section_id": sec.id,
        "report_id": report.id,
        "message": f"Đã chèn kết quả phân tích vào mục '{title}' của báo cáo thành công!",
    }


@router.post("/{report_id}/generate-all")
async def start_agentic_report_generation(
    report_id: str,
    instructions: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Starts the 12-step autonomous document generation engine."""
    report = await report_repo.get(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    project = await project_repo.get(db, report.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.models.entities import Job
    from app.repositories.base import BaseRepository
    from app.services.agent.agentic_report_orchestrator import agentic_orchestrator

    job_repo = BaseRepository[Job](Job)
    job = await job_repo.create(db, obj_in={
        "project_id": project.id,
        "job_type": "agentic_report_generation",
        "status": "running",
        "progress_percent": 5,
        "status_message": "Đang khởi tạo Agentic Report Engine...",
        "payload_json": {"report_id": report.id},
    })

    # Run workflow
    asyncio_task = asyncio.create_task(
        agentic_orchestrator.run_workflow(
            db=db,
            job_id=job.id,
            project_id=project.id,
            report_id=report.id,
            instructions=instructions,
        )
    )

    return {
        "job_id": job.id,
        "status": "running",
        "message": "Hệ thống Agentic Report Engine đã bắt đầu thực thi tự động.",
    }


@router.post("/auto-create")
async def one_click_auto_create(
    prompt: str = Form(...),
    template_id: Optional[str] = Form(None),
    use_uploaded_template: bool = Form(False),
    data_source_url: Optional[str] = Form(None),
    dataset_file_id: Optional[str] = Form(None),
    sheet_range: Optional[str] = Form(None),
    analysis_request: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Phase U11: One-Click Autonomous Report Generation."""
    from app.services.editor.outline_service import outline_service
    from app.schemas.ai import AnalyzeIntentRequest
    from app.models.entities import Job, UploadedFile, Document
    from app.repositories.base import BaseRepository
    from app.repositories.project_repo import file_repo, document_repo
    from app.repositories.template_repo import template_repo, template_version_repo
    from app.services.agent.agentic_report_orchestrator import agentic_orchestrator
    from app.services.documents.pdf_parser import pdf_parser
    from app.services.documents.docx_parser import docx_parser
    from app.services.data.data_engine import data_engine
    from app.services.data.url_dataset_loader import url_dataset_loader
    from app.services.templates.template_reverse_engineering_service import template_reverse_engineer
    from app.core.config import settings
    import hashlib
    from pathlib import Path

    uploaded_dataset_files = [
        item for item in (files or [])
        if Path(item.filename or "").suffix.lower() in {".xlsx", ".xlsm", ".xls", ".csv"}
    ]
    if dataset_file_id and ((data_source_url or "").strip() or uploaded_dataset_files):
        raise HTTPException(status_code=422, detail="Chỉ chọn một nguồn dữ liệu bảng tính cho mỗi báo cáo.")

    stored_dataset = None
    stored_dataset_path = None
    if dataset_file_id:
        stored_dataset, stored_dataset_path = await _resolve_stored_dataset_source(
            db,
            current_user,
            dataset_file_id,
        )

    # 1. AI Intent Analysis
    intent = await outline_service.analyze_intent(AnalyzeIntentRequest(user_prompt=prompt))

    clean_title = _clean_generated_report_title(prompt, intent.suggested_title)

    # 2. Create Project
    project = await project_repo.create(db, obj_in={
        "user_id": current_user.id,
        "name": clean_title,
        "type": intent.suggested_type,
        "description": intent.objective,
        "metadata_json": {
            "document_type": intent.suggested_type,
            "document_profile": intent.suggested_type,
            "audience": intent.target_audience,
            "custom_fields": intent.suggested_custom_fields or [],
        }
    })

    resolved_template_version_id = await _resolve_template_version_id(db, template_id)

    inferred_dataset_title = None
    has_tabular_dataset = False

    async def store_dataset_from_bytes(contents: bytes, filename: str, mime_type: str, source_url: Optional[str] = None):
        nonlocal inferred_dataset_title, has_tabular_dataset
        has_tabular_dataset = True
        file_hash = hashlib.sha256(contents).hexdigest()
        duplicate_stmt = (
            select(UploadedFile)
            .join(Project, UploadedFile.project_id == Project.id)
            .where(
                Project.user_id == current_user.id,
                UploadedFile.file_type == "excel",
                UploadedFile.file_hash == file_hash,
            )
            .order_by(UploadedFile.created_at.asc())
        )
        duplicate_res = await db.execute(duplicate_stmt)
        duplicate_file = duplicate_res.scalars().first()
        duplicate_profile = (duplicate_file.metadata_json or {}).get("dataset_profile") if duplicate_file else None
        if duplicate_file and duplicate_profile and not sheet_range:
            inferred_dataset_title = inferred_dataset_title or data_engine.infer_report_title(duplicate_profile)
            txt = data_engine.format_profile_for_prompt(duplicate_profile)
            await document_repo.create(db, obj_in={
                "project_id": project.id,
                "file_id": None,
                "title": duplicate_file.original_name,
                "content_text": txt,
                "content_json": duplicate_profile,
                "document_type": "dataset",
                "token_count": len(txt) // 4,
            })
            return

        stored_filename = f"{project.id}_{file_hash[:12]}_{filename}"
        file_path = settings.UPLOAD_DIR / stored_filename
        with open(file_path, "wb") as out_f:
            out_f.write(contents)
        try:
            dataset_profile = data_engine.profile_dataset(str(file_path), sheet_range=sheet_range)
            inferred_dataset_title = inferred_dataset_title or data_engine.infer_report_title(dataset_profile)
        except Exception as ex:
            dataset_profile = {
                "file_name": filename,
                "source_type": "excel",
                "sheets": [],
                "verified_facts": [],
                "warnings": [f"Không thể phân tích dữ liệu: {str(ex)}"],
                "grounding_rules": data_engine.grounding_rules(),
                "selection": {"sheet_range": sheet_range or "", "sheet_name": "", "range": ""},
            }
        dataset_metadata = {
            "dataset_profile": dataset_profile,
            "source_url": source_url or "",
            "sheet_range": sheet_range or "",
            "analysis_request": analysis_request or "",
        }
        up_file = await file_repo.create(db, obj_in={
            "project_id": project.id,
            "filename": stored_filename,
            "original_name": filename,
            "file_type": "excel",
            "mime_type": mime_type or "application/octet-stream",
            "file_size": len(contents),
            "file_path": str(file_path),
            "file_hash": file_hash,
            "is_parsed": True,
            "metadata_json": dataset_metadata,
        })
        comparison = await _compare_dataset_with_existing_for_auto_create(db, current_user.id, dataset_profile, up_file.id)
        dataset_metadata = {**dataset_metadata, "dataset_comparison": comparison}
        up_file = await file_repo.update(db, db_obj=up_file, obj_in={"metadata_json": dataset_metadata})
        txt = data_engine.format_profile_for_prompt(dataset_profile)
        if analysis_request:
            txt = f"{txt}\n\nYÊU CẦU PHÂN TÍCH CỦA NGƯỜI DÙNG:\n{analysis_request}"
        await document_repo.create(db, obj_in={
            "project_id": project.id,
            "file_id": up_file.id,
            "title": filename,
            "content_text": txt,
            "content_json": dataset_profile,
            "document_type": "dataset",
            "token_count": len(txt) // 4,
        })

    if stored_dataset is not None and stored_dataset_path is not None:
        await store_dataset_from_bytes(
            stored_dataset_path.read_bytes(),
            stored_dataset.original_name,
            stored_dataset.mime_type,
        )

    if (data_source_url or "").strip():
        try:
            linked_contents, linked_filename, linked_mime = await url_dataset_loader.load(
                data_source_url.strip(), sheet_range=sheet_range
            )
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as ex:
            raise HTTPException(status_code=400, detail=f"Không thể tải dữ liệu từ liên kết: {str(ex)}")
        await store_dataset_from_bytes(linked_contents, linked_filename, linked_mime, data_source_url.strip())

    # 3. Upload and parse any attached files
    if files:
        for f in files:
            contents = await f.read()
            if not contents:
                continue
            filename = f.filename or "attachment"
            ext = Path(filename).suffix.lower()
            file_hash = hashlib.sha256(contents).hexdigest()
            cat = "pdf" if ext == ".pdf" else "docx" if ext in [".docx", ".doc"] else "excel" if ext in [".xlsx", ".xls", ".xlsm", ".csv"] else "text"
            if cat == "excel":
                has_tabular_dataset = True
                duplicate_stmt = (
                    select(UploadedFile)
                    .join(Project, UploadedFile.project_id == Project.id)
                    .where(
                        Project.user_id == current_user.id,
                        UploadedFile.file_type == "excel",
                        UploadedFile.file_hash == file_hash,
                    )
                    .order_by(UploadedFile.created_at.asc())
                )
                duplicate_res = await db.execute(duplicate_stmt)
                duplicate_file = duplicate_res.scalars().first()
                duplicate_profile = (duplicate_file.metadata_json or {}).get("dataset_profile") if duplicate_file else None
                if duplicate_file and duplicate_profile and not sheet_range:
                    inferred_dataset_title = inferred_dataset_title or data_engine.infer_report_title(duplicate_profile)
                    txt = data_engine.format_profile_for_prompt(duplicate_profile)
                    await document_repo.create(db, obj_in={
                        "project_id": project.id,
                        "file_id": None,
                        "title": duplicate_file.original_name,
                        "content_text": txt,
                        "content_json": duplicate_profile,
                        "document_type": "dataset",
                        "token_count": len(txt) // 4,
                    })
                    continue
            stored_filename = f"{project.id}_{file_hash[:12]}_{filename}"
            file_path = settings.UPLOAD_DIR / stored_filename
            with open(file_path, "wb") as out_f:
                out_f.write(contents)

            if (
                resolved_template_version_id is None
                and ext in [".docx", ".doc"]
                and (
                    use_uploaded_template
                    or any(marker in filename.lower() for marker in ["mau", "mẫu", "template"])
                )
            ):
                schema = None
                try:
                    schema = await template_reverse_engineer.reverse_engineer_docx(str(file_path))
                except Exception:
                    try:
                        parsed = docx_parser.extract_document(str(file_path))
                        headings = parsed.get("headings", [])
                        schema = {
                            "document_type": intent.suggested_type or "custom",
                            "title": Path(filename).stem,
                            "sections": [
                                {
                                    "title": h.get("text", ""),
                                    "level": h.get("level") or 1,
                                    "is_required": True,
                                }
                                for h in headings[:30]
                                if h.get("text")
                            ],
                            "fields": [],
                            "styles": (parsed.get("sections") or [{}])[0],
                            "fixed_content": [],
                            "replaceable_content": parsed.get("paragraphs", [])[:60],
                            "instructions": ["Giữ bố cục mẫu DOCX và chèn nội dung báo cáo đã sinh vào các phần nội dung chính."],
                            "repeating_blocks": [],
                            "explicit_placeholders": [],
                        }
                    except Exception:
                        schema = {
                            "document_type": intent.suggested_type or "custom",
                            "title": Path(filename).stem,
                            "sections": [],
                            "fields": [],
                            "styles": {},
                            "fixed_content": [],
                            "replaceable_content": [],
                            "instructions": ["Giữ bố cục mẫu DOCX và chèn nội dung báo cáo đã sinh vào tài liệu."],
                            "repeating_blocks": [],
                            "explicit_placeholders": [],
                        }

                template = await template_repo.create(db, obj_in={
                    "user_id": current_user.id,
                    "name": Path(filename).stem,
                    "category": intent.suggested_type or "academic",
                    "description": f"Mẫu DOCX tự nhận diện từ file {filename}",
                    "is_system": False,
                    "is_public": False,
                    "visibility": "my",
                    "organization": "User Upload",
                    "schema_json": schema,
                })
                version = await template_version_repo.create(db, obj_in={
                    "template_id": template.id,
                    "version_number": 1,
                    "styles_json": schema.get("styles", {}),
                    "placeholders_json": {
                        "explicit": schema.get("explicit_placeholders", []),
                        "detected": schema.get("fields", []),
                    },
                    "schema_json": schema,
                    "file_path": str(file_path),
                })
                resolved_template_version_id = version.id

            dataset_profile = None
            if cat == "excel":
                try:
                    dataset_profile = data_engine.profile_dataset(str(file_path), sheet_range=sheet_range)
                    inferred_dataset_title = inferred_dataset_title or data_engine.infer_report_title(dataset_profile)
                except Exception as ex:
                    dataset_profile = {
                        "file_name": filename,
                        "source_type": "excel",
                        "sheets": [],
                        "verified_facts": [],
                        "warnings": [f"Không thể phân tích dữ liệu: {str(ex)}"],
                        "grounding_rules": data_engine.grounding_rules(),
                        "selection": {"sheet_range": sheet_range or "", "sheet_name": "", "range": ""},
                    }

            dataset_metadata = {
                "dataset_profile": dataset_profile,
                "sheet_range": sheet_range or "",
                "analysis_request": analysis_request or "",
            } if dataset_profile else {}
            up_file = await file_repo.create(db, obj_in={
                "project_id": project.id,
                "filename": stored_filename,
                "original_name": filename,
                "file_type": cat,
                "mime_type": f.content_type or "application/octet-stream",
                "file_size": len(contents),
                "file_path": str(file_path),
                "file_hash": file_hash,
                "is_parsed": True,
                "metadata_json": dataset_metadata,
            })
            if dataset_profile:
                comparison = await _compare_dataset_with_existing_for_auto_create(db, current_user.id, dataset_profile, up_file.id)
                dataset_metadata = {**dataset_metadata, "dataset_comparison": comparison}
                up_file = await file_repo.update(db, db_obj=up_file, obj_in={"metadata_json": dataset_metadata})

            # Extract text
            try:
                txt = ""
                if cat == "pdf":
                    txt = pdf_parser.extract_text_and_metadata(str(file_path)).get("full_text", "")
                elif cat == "docx":
                    txt = docx_parser.extract_document(str(file_path)).get("full_text", "")
                elif cat == "text":
                    txt = contents.decode("utf-8", errors="ignore")
                elif cat == "excel":
                    txt = data_engine.format_profile_for_prompt(dataset_profile or data_engine.profile_dataset(str(file_path)))
                    if analysis_request:
                        txt = f"{txt}\n\nYÊU CẦU PHÂN TÍCH CỦA NGƯỜI DÙNG:\n{analysis_request}"
                if txt:
                    await document_repo.create(db, obj_in={
                        "project_id": project.id,
                        "file_id": up_file.id,
                        "title": filename,
                        "content_text": txt,
                        "content_json": dataset_profile or {},
                        "document_type": "dataset" if cat == "excel" else "reference",
                        "token_count": len(txt) // 4,
                    })
            except Exception:
                pass

    if has_tabular_dataset:
        next_name = inferred_dataset_title if inferred_dataset_title and _looks_like_generic_data_task_title(project.name) else project.name
        project = await project_repo.update(db, db_obj=project, obj_in={
            "name": next_name,
            "type": "data_analysis",
            "description": f"Tự động phân tích dữ liệu từ file đã tải lên: {next_name}.",
            "metadata_json": {
                **(project.metadata_json or {}),
                "dataset_inferred_title": inferred_dataset_title,
                "document_type": "data_analysis",
                "document_profile": "data_analysis",
                "data_first": True,
            },
        })

    # 4. Create Initial Report
    report = await report_repo.create(db, obj_in={
        "project_id": project.id,
        "template_version_id": resolved_template_version_id,
        "title": project.name,
        "report_type": intent.suggested_type,
        "status": "generating",
        "revision": 1,
    })

    # 5. Create Job Record
    job_repo = BaseRepository[Job](Job)
    job = await job_repo.create(db, obj_in={
        "project_id": project.id,
        "job_type": "one_click_auto_report",
        "status": "running",
        "progress_percent": 5,
        "status_message": "Đang khởi tạo quy trình One-Click Auto Report...",
        "payload_json": {"report_id": report.id, "prompt": prompt},
        "metadata_json": {"report_id": report.id, "project_id": project.id},
    })

    # 6. Launch background execution in independent standalone session
    asyncio.create_task(
        agentic_orchestrator.run_workflow(
            job_id=job.id,
            project_id=project.id,
            report_id=report.id,
            instructions=prompt,
        )
    )

    return {
        "job_id": job.id,
        "project_id": project.id,
        "report_id": report.id,
        "status": "running",
        "message": "Hệ thống One-Click Auto Report đang tự động khởi tạo báo cáo hoàn chỉnh.",
    }


@router.post("/jobs/{job_id}/pause")
async def pause_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.repositories.base import BaseRepository

    job_repo = BaseRepository[Job](Job)
    job = await job_repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await _ensure_job_owner(db, job, current_user)

    await job_repo.update(db, db_obj=job, obj_in={"status": "paused", "status_message": "Quy trình đang tạm dừng."})
    return {"job_id": job.id, "status": "paused"}


@router.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.repositories.base import BaseRepository

    job_repo = BaseRepository[Job](Job)
    job = await job_repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await _ensure_job_owner(db, job, current_user)

    await job_repo.update(db, db_obj=job, obj_in={"status": "running", "status_message": "Tiếp tục thực thi quy trình..."})
    return {"job_id": job.id, "status": "running"}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.repositories.base import BaseRepository

    job_repo = BaseRepository[Job](Job)
    job = await job_repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await _ensure_job_owner(db, job, current_user)

    await job_repo.update(db, db_obj=job, obj_in={"status": "cancelled", "status_message": "Quy trình đã bị hủy bỏ."})
    return {"job_id": job.id, "status": "cancelled"}


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.repositories.base import BaseRepository
    from app.services.agent.agentic_report_orchestrator import agentic_orchestrator

    job_repo = BaseRepository[Job](Job)
    job = await job_repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await _ensure_job_owner(db, job, current_user)

    report_id = (job.metadata_json or {}).get("report_id") or (job.payload_json or {}).get("report_id")
    if not report_id:
        raise HTTPException(status_code=400, detail="Cannot retry: missing report_id in job metadata")

    await job_repo.update(db, db_obj=job, obj_in={
        "status": "running",
        "progress_percent": 5,
        "status_message": "Đang thực hiện lại quy trình...",
        "error_message": None,
    })

    asyncio.create_task(
        agentic_orchestrator.run_workflow(
            db=db,
            job_id=job.id,
            project_id=job.project_id,
            report_id=report_id,
            instructions=(job.payload_json or {}).get("prompt"),
        )
    )

    return {"job_id": job.id, "status": "running", "message": "Đã khởi động lại quy trình thành công."}


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.repositories.base import BaseRepository

    job_repo = BaseRepository[Job](Job)
    job = await job_repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await _ensure_job_owner(db, job, current_user)
    metadata = job.metadata_json or {}
    payload = job.payload_json or {}
    timeline = metadata.get("timeline") or []
    report_id = metadata.get("report_id") or payload.get("report_id")
    can_retry = job.status in ["failed", "cancelled"] and bool(report_id)
    next_action = "wait"
    if job.status == "completed":
        next_action = "open_report"
    elif job.status == "review_needed":
        next_action = "open_report_for_review"
    elif job.status == "failed":
        next_action = "retry"
    elif job.status == "cancelled":
        next_action = "retry_or_create_new"
    elif job.status == "paused":
        next_action = "resume"

    return {
        "job_id": job.id,
        "status": job.status,
        "progress_percent": job.progress_percent,
        "status_message": job.status_message,
        "current_stage": metadata.get("current_stage"),
        "timeline": timeline,
        "can_retry": can_retry,
        "next_action": next_action,
        "error_message": job.error_message,
        "metadata": metadata,
        "payload": payload,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.post("/bulk-preview")
async def preview_bulk_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Parses and validates CSV/Excel for batch generation."""
    from app.services.automation.bulk_report_service import bulk_report_service
    contents = await file.read()
    filename = (file.filename or "batch.csv").lower()
    rows = await bulk_report_service.parse_batch_file(contents, filename)
    return {"total_rows": len(rows), "preview": rows[:10], "all_rows": rows}


@router.post("/bulk-create")
async def launch_bulk_create(
    file: UploadFile = File(...),
    batch_title: Optional[str] = Form("Đợt Sinh Báo Cáo Tự Động"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launches parallel batch report generation from CSV/XLSX job sheet."""
    from app.services.automation.bulk_report_service import bulk_report_service
    contents = await file.read()
    filename = (file.filename or "batch.csv").lower()
    rows = await bulk_report_service.parse_batch_file(contents, filename)
    if not rows:
        raise HTTPException(status_code=400, detail="Tập tin tải lên không chứa dòng dữ liệu hợp lệ.")

    res = await bulk_report_service.launch_batch_job(
        user_id=current_user.id,
        batch_title=batch_title or "Đợt Sinh Báo Cáo Hàng Loạt",
        items=rows,
        db=db,
    )
    return res
