import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.entities import Job
from app.repositories.base import BaseRepository
from app.repositories.project_repo import project_repo
from app.repositories.report_repo import report_repo, section_repo
from app.api.v1.reports import _looks_like_generic_data_task_title
from app.services.agent.agentic_report_orchestrator import agentic_orchestrator


def test_length_plan_treats_requested_pages_as_body_pages():
    plan = agentic_orchestrator._resolve_length_plan("Số trang mục tiêu: 5 trang A4")

    assert plan["target_pages"] == 5
    assert plan["body_pages"] == 5
    assert plan["front_matter_pages"] == 2
    assert plan["estimated_total_pages"] == 7
    assert plan["target_words"] == 1500
    assert plan["target_chapters"] <= 3


def test_section_word_targets_do_not_explode_short_reports():
    class Section:
        def __init__(self, title: str, level: int):
            self.title = title
            self.level = level

    sections = [
        Section("Mở đầu", 1),
        Section("Thực trạng", 1),
        Section("Giải pháp", 1),
        Section("Kết luận", 1),
        Section("TÀI LIỆU THAM KHẢO", 1),
    ]
    plan = agentic_orchestrator._resolve_length_plan("viết 5 trang")
    targets = agentic_orchestrator._allocate_section_word_targets(sections, plan)

    assert sum(targets.values()) <= 1650
    assert targets["TÀI LIỆU THAM KHẢO"] <= 80
    assert min(words for title, words in targets.items() if title != "TÀI LIỆU THAM KHẢO") >= 140


def test_generic_data_task_titles_are_detected():
    assert _looks_like_generic_data_task_title("Tác vụ: Phân tích dữ liệu từ file Excel/CSV đã tải lên")
    assert _looks_like_generic_data_task_title("Module: Phân tích dữ liệu")
    assert not _looks_like_generic_data_task_title("Báo cáo phân tích dữ liệu bảng lương nhân viên")


@pytest.mark.live
@pytest.mark.asyncio
async def test_one_click_auto_create_flow(client: AsyncClient):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "autouser@corp.com",
        "password": "Password123!",
        "name": "Auto User"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Auto create with prompt
    form_data = {"prompt": "Báo cáo Tự động Thị trường Năng lượng Mặt trời 2026"}
    auto_res = await client.post("/api/v1/reports/auto-create", data=form_data, headers=headers)
    assert auto_res.status_code == 200
    data = auto_res.json()
    assert "job_id" in data
    assert "report_id" in data
    assert "project_id" in data
    assert data["status"] == "running"
    job_id = data["job_id"]

    # Pause Job
    pause_res = await client.post(f"/api/v1/reports/jobs/{job_id}/pause", headers=headers)
    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "paused"

    # Resume Job
    resume_res = await client.post(f"/api/v1/reports/jobs/{job_id}/resume", headers=headers)
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "running"

    # Cancel Job
    cancel_res = await client.post(f"/api/v1/reports/jobs/{job_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    # Retry Job
    retry_res = await client.post(f"/api/v1/reports/jobs/{job_id}/retry", headers=headers)
    assert retry_res.status_code == 200
    assert retry_res.json()["status"] == "running"


@pytest.mark.live
@pytest.mark.asyncio
async def test_auto_create_accepts_dataset_link_sheet_range_and_analysis_request(client: AsyncClient, monkeypatch):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "auto_link_data@corp.com",
        "password": "Password123!",
        "name": "Auto Link Data"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    csv_content = b"Nhan vien,Phong ban,Luong\nA,Ke toan,100\nB,Kinh doanh,200\nC,Nhan su,300\n"
    data_url = "https://example.com/bang-luong.csv"

    async def fake_load(url: str, sheet_range: str = None):
        assert url == data_url
        return csv_content, "bang-luong.csv", "text/csv"

    monkeypatch.setattr("app.services.data.url_dataset_loader.url_dataset_loader.load", fake_load)
    auto_res = await client.post("/api/v1/reports/auto-create", data={
        "prompt": "Module: Phân tích dữ liệu",
        "data_source_url": data_url,
        "sheet_range": "A1:C3",
        "analysis_request": "Phân tích lương theo phòng ban",
    }, headers=headers)

    assert auto_res.status_code == 200
    files_res = await client.get("/api/v1/files", headers=headers)
    datasets = [item for item in files_res.json() if item["file_type"] == "excel"]
    assert len(datasets) == 1
    metadata = datasets[0]["metadata_json"]
    assert metadata["source_url"] == data_url
    assert metadata["sheet_range"] == "A1:C3"
    assert metadata["analysis_request"] == "Phân tích lương theo phòng ban"
    assert metadata["dataset_profile"]["total_rows"] == 2


@pytest.mark.live
@pytest.mark.asyncio
async def test_agentic_background_workflow_completes_with_sections(db_session: AsyncSession):
    project = await project_repo.create(db_session, obj_in={
        "user_id": "workflow-user",
        "name": "Báo cáo lõi hoạt động thật",
        "type": "business_report",
        "description": "Kiểm tra engine nền tạo đề cương và nội dung thật.",
        "metadata_json": {"audience": "Ban điều hành"},
    })
    report = await report_repo.create(db_session, obj_in={
        "project_id": project.id,
        "title": project.name,
        "report_type": project.type,
        "status": "generating",
        "revision": 1,
    })

    job_repo = BaseRepository[Job](Job)
    job = await job_repo.create(db_session, obj_in={
        "project_id": project.id,
        "job_type": "one_click_auto_report",
        "status": "running",
        "progress_percent": 5,
        "status_message": "Starting test workflow",
        "metadata_json": {"report_id": report.id, "project_id": project.id},
    })

    result = await agentic_orchestrator._run_workflow_with_session(
        db=db_session,
        job_id=job.id,
        project_id=project.id,
        report_id=report.id,
        instructions="Sinh báo cáo kiểm thử có nội dung hoàn chỉnh.",
    )

    assert result["status"] == "completed"
    refreshed_job = await job_repo.get(db_session, job.id)
    assert refreshed_job.status == "completed"
    assert refreshed_job.progress_percent == 100

    sections = await section_repo.get_by_report(db_session, report.id)
    assert len(sections) > 0
    assert all(section.status == "draft" for section in sections)
    assert sum(section.word_count for section in sections) > 0
