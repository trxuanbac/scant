import hashlib
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import User, Project, UploadedFile, Document
from app.repositories.project_repo import project_repo, file_repo, document_repo
from app.schemas.project import FileSummary
from app.api.deps import get_current_user
from app.services.documents.pdf_parser import pdf_parser
from app.services.documents.docx_parser import docx_parser
from app.services.data.data_engine import data_engine
from app.services.knowledge.retrieval_service import retrieval_service
from app.services.data.data_access import owned_dataset

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".pptx", ".txt", ".md", ".zip", ".png", ".jpg"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


async def _compare_dataset_with_existing(
    db: AsyncSession,
    user_id: str,
    profile: Dict[str, Any],
    current_file_id: str,
) -> Dict[str, Any]:
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
            await file_repo.update(db, db_obj=best_file, obj_in={
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

    group_id = f"dataset-group-{current_file_id}"
    return {
        "status": "primary",
        "comparison_status": "primary",
        "similarity_score": 1.0,
        "schema_match": False,
        "schema_signature": data_engine.dataset_schema_signature(profile),
        "row_signature": data_engine.dataset_row_signature(profile),
        "dataset_group_id": group_id,
        "dataset_role": "primary",
    }


@router.get("", response_model=List[FileSummary])
async def list_files(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(UploadedFile)
        .join(Project, UploadedFile.project_id == Project.id)
        .where(Project.user_id == current_user.id)
        .order_by(UploadedFile.created_at.desc())
    )
    res = await db.execute(stmt)
    return [FileSummary.model_validate(f) for f in res.scalars().all()]


@router.post("/upload", response_model=FileSummary)
async def upload_file(
    project_id: str = Form(...),
    document_type: str = Form("reference"),  # requirement, rubric, reference, source_code, dataset
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await project_repo.get(db, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    filename = file.filename or "uploaded_file"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 50MB limit")

    file_hash = hashlib.sha256(contents).hexdigest()
    file_type_cat = "pdf" if ext == ".pdf" else "docx" if ext in [".docx", ".doc"] else "excel" if ext in [".xlsx", ".xls", ".csv"] else "zip" if ext == ".zip" else "text"

    if file_type_cat == "excel":
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
        if duplicate_file:
            metadata = {
                **(duplicate_file.metadata_json or {}),
                "dataset_comparison": {
                    **((duplicate_file.metadata_json or {}).get("dataset_comparison") or {}),
                    "last_duplicate_upload_ignored": filename,
                },
            }
            duplicate_file = await file_repo.update(db, db_obj=duplicate_file, obj_in={"metadata_json": metadata})
            return FileSummary.model_validate(duplicate_file)

    # Save to disk
    stored_filename = f"{project_id}_{file_hash[:12]}_{filename}"
    file_path = settings.UPLOAD_DIR / stored_filename
    with open(file_path, "wb") as f:
        f.write(contents)

    # Create UploadedFile record
    uploaded_file = await file_repo.create(db, obj_in={
        "project_id": project_id,
        "filename": stored_filename,
        "original_name": filename,
        "file_type": file_type_cat,
        "mime_type": file.content_type or "application/octet-stream",
        "file_size": len(contents),
        "file_path": str(file_path),
        "file_hash": file_hash,
        "is_parsed": False,
        "metadata_json": {}
    })

    # Auto parse text content into Knowledge Base Document
    try:
        content_text = ""
        metadata = {}
        analysis = None
        if file_type_cat == "pdf":
            parsed = pdf_parser.extract_text_and_metadata(str(file_path))
            content_text = parsed["full_text"]
            metadata = parsed["metadata"]
        elif file_type_cat == "docx":
            parsed = docx_parser.extract_document(str(file_path))
            content_text = parsed["full_text"]
            metadata = {"headings_count": len(parsed["headings"]), "tables_count": parsed["tables_count"]}
        elif file_type_cat == "excel":
            analysis = data_engine.profile_dataset(str(file_path))
            content_text = data_engine.format_profile_for_prompt(analysis)
            dataset_comparison = await _compare_dataset_with_existing(db, current_user.id, analysis, uploaded_file.id)
            metadata = {"dataset_profile": analysis, "dataset_comparison": dataset_comparison}
        elif file_type_cat == "text":
            content_text = contents.decode("utf-8", errors="ignore")

        if content_text:
            await document_repo.create(db, obj_in={
                "project_id": project_id,
                "file_id": uploaded_file.id,
                "title": filename,
                "content_text": content_text,
                "content_json": analysis if file_type_cat == "excel" else {},
                "document_type": document_type,
                "token_count": len(content_text) // 4,
            })
            await file_repo.update(db, db_obj=uploaded_file, obj_in={"is_parsed": True, "metadata_json": metadata})
    except Exception:
        pass

    return FileSummary.model_validate(uploaded_file)


@router.get("/project/{project_id}", response_model=List[FileSummary])
async def list_project_files(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await project_repo.get(db, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    files = await file_repo.get_multi(db, project_id=project_id)
    return [FileSummary.model_validate(f) for f in files]


@router.get("/project/{project_id}/search")
async def search_knowledge_base(
    project_id: str,
    query: str,
    top_k: int = 4,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    project = await project_repo.get(db, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    docs = await document_repo.get_multi(db, project_id=project_id)
    docs_payload = [
        {
            "id": d.id,
            "original_name": d.title,
            "content_text": d.content_text
        }
        for d in docs
    ]

    return retrieval_service.search_relevant_chunks(query=query, documents=docs_payload, top_k=top_k)


# Phase U21: Signed URL Generation & Secure Download

@router.post("/{file_id}/signed-url")
async def generate_file_signed_url(
    file_id: str,
    expires_in_seconds: int = 3600,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.storage.signed_url_service import signed_url_service
    f = await owned_dataset(db, file_id, current_user)

    token = signed_url_service.generate_signed_token(
        storage_key=f.file_path,
        user_id=current_user.id,
        expires_in_seconds=expires_in_seconds
    )
    return {
        "file_id": f.id,
        "filename": f.original_name,
        "signed_token": token,
        "download_url": f"/api/v1/files/download/signed/{token}",
        "expires_in_seconds": expires_in_seconds,
    }


@router.get("/download/signed/{token}")
async def download_file_by_signed_token(token: str):
    from fastapi.responses import FileResponse, Response
    from app.services.storage.signed_url_service import signed_url_service
    from app.services.storage.storage_provider import storage_provider

    is_valid, storage_key, error = signed_url_service.verify_and_decode_token(token)
    if not is_valid or not storage_key:
        raise HTTPException(status_code=403, detail=error or "Invalid or expired signed URL.")

    if not Path(storage_key).exists():
        raise HTTPException(status_code=404, detail="File not found on storage.")

    filename = Path(storage_key).name
    return FileResponse(
        path=storage_key,
        filename=filename,
        media_type="application/octet-stream"
    )
