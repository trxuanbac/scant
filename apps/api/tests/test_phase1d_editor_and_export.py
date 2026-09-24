import os
import base64
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import ExportRecord


@pytest.mark.asyncio
async def test_full_phase1d_editor_and_export_flow(client: AsyncClient):
    # 1. Register & Project
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "editor_user@test.com",
        "password": "Password123!",
        "name": "Tran Thi E"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_res = await client.post("/api/v1/projects", json={
        "name": "Báo cáo Tốt nghiệp CNTT",
        "type": "academic",
        "topic_details": {
            "university": "Đại học Bách Khoa Hà Nội",
            "student_name": "Tran Thi E",
            "student_id": "20210005",
            "instructor": "PGS. TS. Nguyen Van F"
        }
    }, headers=headers)
    project_id = proj_res.json()["id"]

    # 2. Add verified source
    await client.post("/api/v1/research/sources", json={
        "project_id": project_id,
        "title": "ASP.NET Core Architecture Official Guide",
        "url": "https://learn.microsoft.com/aspnet/core",
        "authors": "Microsoft",
        "publisher": "Microsoft Press",
        "published_date": "2024",
        "source_type": "official_doc",
        "reliability_score": 0.98,
        "summary": "ASP.NET Core is an open source web framework."
    }, headers=headers)

    # 3. Create Report with Chapters
    report_res = await client.post("/api/v1/reports", json={
        "project_id": project_id,
        "title": "Báo cáo Đồ án Website Thương mại Điện tử",
        "report_type": "academic",
        "outline": [
            {
                "title": "CHƯƠNG 1: TỔNG QUAN ĐỀ TÀI",
                "level": 1,
                "position": 1,
                "children": [
                    {"title": "1.1 Bối cảnh chọn đề tài", "level": 2, "position": 2, "children": []}
                ]
            }
        ]
    }, headers=headers)
    assert report_res.status_code == 201
    report_data = report_res.json()
    report_id = report_data["id"]
    section_id = report_data["sections"][0]["id"]

    # 4. AI Draft Section
    draft_res = await client.post("/api/v1/ai/draft-section", json={
        "project_id": project_id,
        "report_id": report_id,
        "section_id": section_id,
        "instruction": "Trình bày tổng quan về ASP.NET Core MVC"
    }, headers=headers)
    assert draft_res.status_code == 200
    assert len(draft_res.json()["text"]) > 0

    # 5. Check Quality Gate
    qc_res = await client.post(f"/api/v1/ai/check-report/{report_id}", headers=headers)
    assert qc_res.status_code == 200
    qc_data = qc_res.json()
    assert qc_data["overall_score"] > 0

    # 6. Export DOCX
    docx_res = await client.post("/api/v1/exports/docx", json={
        "report_id": report_id,
        "export_format": "docx",
        "include_cover": True,
        "include_toc": True,
        "include_references": True
    }, headers=headers)
    assert docx_res.status_code == 200
    docx_data = docx_res.json()
    assert docx_data["file_size"] > 0
    assert "download_url" in docx_data

    # 7. Export PDF/HTML
    pdf_res = await client.post("/api/v1/exports/pdf", json={
        "report_id": report_id,
        "export_format": "pdf"
    }, headers=headers)
    assert pdf_res.status_code == 200
    assert pdf_res.json()["file_size"] > 0


@pytest.mark.asyncio
async def test_preview_html_loads_for_plain_report(client: AsyncClient):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "preview_user@test.com",
        "password": "Password123!",
        "name": "Preview User"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_res = await client.post("/api/v1/projects", json={
        "name": "Preview Regression",
        "type": "academic",
    }, headers=headers)
    project_id = proj_res.json()["id"]

    report_res = await client.post("/api/v1/reports", json={
        "project_id": project_id,
        "title": "Báo cáo kiểm tra preview",
        "report_type": "academic",
        "outline": [
            {"title": "CHƯƠNG 1: KIỂM TRA", "level": 1, "position": 1, "children": []}
        ]
    }, headers=headers)
    report_data = report_res.json()
    report_id = report_data["id"]
    section_id = report_data["sections"][0]["id"]

    await client.put(f"/api/v1/reports/sections/{section_id}", json={
        "plain_text": "Đây là nội dung kiểm tra bản xem theo mẫu.",
        "content_json": {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Đây là nội dung kiểm tra bản xem theo mẫu."}]}
            ],
        },
        "word_count": 8,
        "status": "draft",
    }, headers=headers)

    preview_res = await client.get(f"/api/v1/exports/report/{report_id}/preview-html", headers=headers)
    assert preview_res.status_code == 200
    assert "html_document" in preview_res.json()


@pytest.mark.asyncio
async def test_invalid_final_docx_is_blocked_but_review_draft_is_exported(
    client: AsyncClient,
    db_session: AsyncSession,
):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "draft_export_user@test.com",
        "password": "Password123!",
        "name": "Draft Export User",
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_res = await client.post("/api/v1/projects", json={
        "name": "Nghiên cứu thị trường xe điện Việt Nam",
        "type": "market_research",
        "topic_details": {"topic": "Thị trường xe điện Việt Nam"},
    }, headers=headers)
    project_id = proj_res.json()["id"]

    report_res = await client.post("/api/v1/reports", json={
        "project_id": project_id,
        "title": "Báo cáo thị trường xe điện Việt Nam",
        "report_type": "market_research",
        "outline": [
            {"title": "1. Tổng quan thị trường", "level": 1, "position": 1, "children": []},
        ],
    }, headers=headers)
    report_data = report_res.json()
    report_id = report_data["id"]
    section_id = report_data["sections"][0]["id"]

    await client.put(f"/api/v1/reports/sections/{section_id}", json={
        "plain_text": "ARM và x86 được so sánh theo server throughput trong cloud workload.",
        "word_count": 11,
        "status": "draft",
    }, headers=headers)

    final_res = await client.post("/api/v1/exports/docx", json={
        "report_id": report_id,
    }, headers=headers)
    assert final_res.status_code == 422
    assert final_res.json()["detail"]["validation"]["valid"] is False

    draft_res = await client.post("/api/v1/exports/docx", json={
        "report_id": report_id,
        "review_draft": True,
    }, headers=headers)
    assert draft_res.status_code == 200
    draft_payload = draft_res.json()
    assert draft_payload["filename"].startswith("BAN_NHAP_")
    assert draft_payload["download_url"].rsplit("/", 1)[-1].startswith("BAN_NHAP_")

    record = await db_session.scalar(
        select(ExportRecord)
        .where(ExportRecord.report_id == report_id)
        .order_by(ExportRecord.created_at.desc())
    )
    assert record is not None
    assert record.settings_json["review_draft"] is True
    assert record.settings_json["document_label"] == "BAN_NHAP"
    assert record.settings_json["document_status"] == "review_draft"
    assert record.settings_json["review_required"] is True
    assert record.settings_json["validation"]["valid"] is False


@pytest.mark.asyncio
async def test_report_thumbnail_uses_real_report_content(client: AsyncClient):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "thumbnail_user@test.com",
        "password": "Password123!",
        "name": "Thumbnail User"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_res = await client.post("/api/v1/projects", json={
        "name": "Thumbnail Project",
        "type": "business_report",
    }, headers=headers)
    project_id = proj_res.json()["id"]

    report_res = await client.post("/api/v1/reports", json={
        "project_id": project_id,
        "title": "Báo cáo thumbnail thật",
        "report_type": "business_report",
        "outline": [
            {"title": "Tóm tắt điều hành", "level": 1, "position": 1, "children": []}
        ]
    }, headers=headers)
    report_data = report_res.json()
    report_id = report_data["id"]
    section_id = report_data["sections"][0]["id"]

    await client.put(f"/api/v1/reports/sections/{section_id}", json={
        "plain_text": "Doanh thu tháng 8 tăng nhờ nhóm khách hàng doanh nghiệp.",
        "word_count": 9,
        "status": "draft",
    }, headers=headers)

    thumb_res = await client.get(f"/api/v1/reports/{report_id}/thumbnail", headers=headers)
    assert thumb_res.status_code == 200
    payload = thumb_res.json()
    assert payload["mime_type"] == "image/svg+xml"
    assert payload["image_data_url"].startswith("data:image/svg+xml;base64,")
    decoded = base64.b64decode(payload["image_data_url"].split(",", 1)[1]).decode("utf-8")
    assert "Báo cáo thumbnail thật" in decoded
    assert "Doanh thu tháng 8 tăng" in decoded
