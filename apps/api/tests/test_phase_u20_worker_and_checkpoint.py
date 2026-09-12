import pytest
from app.services.worker.checkpoint_engine import checkpoint_engine
from app.services.worker.queue_manager import ProductionTaskQueue, TaskState


def test_pipeline_checkpoint_engine():
    job_id = "test-job-stage-checkpoint-100"

    # Stage 1
    checkpoint_engine.save_checkpoint(job_id, "understand_request", {"intent": "business_report", "topics": 4})
    assert checkpoint_engine.is_stage_completed(job_id, "understand_request") is True
    assert checkpoint_engine.is_stage_completed(job_id, "draft_sections") is False

    # Stage 2
    checkpoint_engine.save_checkpoint(job_id, "inspect_template", {"template_name": "Executive Template"})
    assert checkpoint_engine.get_last_completed_stage(job_id) == "inspect_template"

    ck_data = checkpoint_engine.get_checkpoint(job_id, "understand_request")
    assert ck_data["intent"] == "business_report"

    # Clear
    checkpoint_engine.clear_checkpoints(job_id)
    assert checkpoint_engine.is_stage_completed(job_id, "understand_request") is False


@pytest.mark.asyncio
async def test_production_task_queue_execution():
    task_queue = ProductionTaskQueue()

    # Register handler
    task_queue.register_handler("deep_research_task", lambda payload: {"status": "researched", "sources_found": 8})

    # Enqueue task with idempotency key
    task1 = await task_queue.enqueue(
        task_name="deep_research_task",
        payload={"topic": "Digital Banking 2026"},
        idempotency_key="idemp-key-001"
    )
    assert task1.state == TaskState.QUEUED

    # Enqueue duplicate with same idempotency key
    task2 = await task_queue.enqueue(
        task_name="deep_research_task",
        payload={"topic": "Digital Banking 2026 Duplicate"},
        idempotency_key="idemp-key-001"
    )
    assert task2.task_id == task1.task_id

    # Process task via worker
    processed = await task_queue.process_next_task()
    assert processed.task_id == task1.task_id
    assert processed.state == TaskState.COMPLETED
    assert processed.result["sources_found"] == 8


@pytest.mark.asyncio
async def test_task_queue_cancellation():
    task_queue = ProductionTaskQueue()

    task = await task_queue.enqueue(
        task_name="long_running_ocr",
        payload={"file_id": "file-123"}
    )
    assert task.state == TaskState.QUEUED

    cancelled = task_queue.cancel_task(task.task_id)
    assert cancelled is True
    assert task_queue.get_task(task.task_id).state == TaskState.CANCELLED


@pytest.mark.asyncio
async def test_task_queue_tracks_stage_progress_and_retryable_snapshot():
    queue = ProductionTaskQueue()
    task = await queue.enqueue(
        task_name="auto_report",
        payload={"project_id": "project-123"},
        max_retries=2,
    )

    updated = queue.update_progress(task.task_id, stage="draft_sections", progress_pct=45)
    snapshot = queue.get_task_snapshot(task.task_id)

    assert updated is True
    assert snapshot["id"] == task.task_id
    assert snapshot["state"] == TaskState.QUEUED
    assert snapshot["stage"] == "draft_sections"
    assert snapshot["progress_pct"] == 45
    assert snapshot["retry_count"] == 0
    assert snapshot["max_retries"] == 2
    assert snapshot["retryable"] is True
