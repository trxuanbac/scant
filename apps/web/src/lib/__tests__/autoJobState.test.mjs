import test from "node:test";
import assert from "node:assert/strict";

import {
  AUTO_JOB_STATE_KEY,
  buildAutoJobSnapshot,
  canSafelySwitchAutoContext,
  compactAutoJobMetadata,
  getAutoExportFailureMessage,
  getAutoJobNextActionMessage,
  getAutoJobUiState,
  isAutoJobInFlight,
  shouldRestoreAutoJob,
} from "../autoJobState.js";

test("detects in-flight auto jobs", () => {
  assert.equal(isAutoJobInFlight("queued"), true);
  assert.equal(isAutoJobInFlight("running"), true);
  assert.equal(isAutoJobInFlight("paused"), true);
  assert.equal(isAutoJobInFlight("completed"), false);
  assert.equal(isAutoJobInFlight("failed"), false);
  assert.equal(isAutoJobInFlight("cancelled"), false);
});

test("keeps only compact workflow metadata in local storage", () => {
  const compact = compactAutoJobMetadata({
    current_stage: "research",
    pipeline: { research: { status: "running" } },
    source_candidates: Array.from({ length: 100 }, (_, index) => ({ id: index, excerpt: "large".repeat(100) })),
    claim_source_ledger: { large: true },
  });

  assert.deepEqual(compact, {
    current_stage: "research",
    pipeline: { research: { status: "running" } },
  });
});

test("builds a restorable auto job snapshot while preserving active report", () => {
  const snapshot = buildAutoJobSnapshot({
    jobId: "job-1",
    reportId: "report-1",
    projectType: "research",
    status: "running",
    progress: 42,
    statusMessage: "Dang soan thao...",
    timeline: [{ stage: "research", progress: 45 }],
    metadata: { current_stage: "research" },
  });

  assert.equal(snapshot.storageKey, AUTO_JOB_STATE_KEY);
  assert.deepEqual(snapshot.value, {
    jobId: "job-1",
    reportId: "report-1",
    projectType: "research",
    status: "running",
    progress: 42,
    statusMessage: "Dang soan thao...",
    timeline: [{ stage: "research", progress: 45 }],
    metadata: { current_stage: "research" },
  });
});

test("restores only valid unfinished jobs", () => {
  assert.equal(shouldRestoreAutoJob(null), false);
  assert.equal(shouldRestoreAutoJob({ jobId: "", status: "running" }), false);
  assert.equal(shouldRestoreAutoJob({ jobId: "job-1", status: "completed" }), false);
  assert.equal(shouldRestoreAutoJob({ jobId: "job-1", status: "failed" }), false);
  assert.equal(shouldRestoreAutoJob({ jobId: "job-1", status: "running" }), true);
});

test("blocks context switches while an auto job is unfinished", () => {
  assert.equal(canSafelySwitchAutoContext("running"), false);
  assert.equal(canSafelySwitchAutoContext("paused"), false);
  assert.equal(canSafelySwitchAutoContext("completed"), true);
  assert.equal(canSafelySwitchAutoContext(""), true);
});

test("presents review-needed as a finished report with a warning", () => {
  const state = getAutoJobUiState("review_needed", 1, "vi");

  assert.equal(state.tone, "review");
  assert.equal(state.terminal, true);
  assert.equal(state.canCancel, false);
  assert.equal(state.title, "Báo cáo đã tạo – cần rà soát 1 nội dung");
});

test("only allows cancellation while an auto job is active", () => {
  assert.equal(getAutoJobUiState("running", 0, "vi").canCancel, true);
  assert.equal(getAutoJobUiState("paused", 0, "vi").canCancel, true);
  assert.equal(getAutoJobUiState("completed", 0, "vi").canCancel, false);
  assert.equal(getAutoJobUiState("failed", 0, "vi").canCancel, false);
});

test("treats cancelled jobs as terminal and retryable", () => {
  const state = getAutoJobUiState("cancelled", 0, "vi");

  assert.equal(state.terminal, true);
  assert.equal(state.canCancel, false);
  assert.equal(state.canRetry, true);
  assert.equal(state.title, "Đã hủy tạo báo cáo");
});

test("only failed and cancelled jobs can be retried", () => {
  assert.equal(getAutoJobUiState("failed", 0, "vi").canRetry, true);
  assert.equal(getAutoJobUiState("cancelled", 0, "vi").canRetry, true);
  assert.equal(getAutoJobUiState("review_needed", 1, "vi").canRetry, false);
  assert.equal(getAutoJobUiState("completed", 0, "vi").canRetry, false);
});

test("describes cancelled-job recovery and export failures", () => {
  assert.equal(
    getAutoJobNextActionMessage("retry_or_create_new", "vi"),
    "Quy trình đã được hủy. Bạn có thể chạy lại hoặc đổi module để tạo báo cáo mới.",
  );
  assert.equal(
    getAutoExportFailureMessage(true, "vi"),
    "Không thể xuất bản Word hiện tại. Hãy thử lại hoặc mở báo cáo để rà soát.",
  );
  assert.equal(
    getAutoExportFailureMessage(false, "en"),
    "The report was created, but Word export failed. Try exporting again.",
  );
});
