import test from "node:test";
import assert from "node:assert/strict";

import {
  AUTO_JOB_STATE_KEY,
  buildAutoJobSnapshot,
  canSafelySwitchAutoContext,
  compactAutoJobMetadata,
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
