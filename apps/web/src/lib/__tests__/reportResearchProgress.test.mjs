import test from "node:test";
import assert from "node:assert/strict";

import { buildReportResearchProgress, summarizeResearchSetup } from "../reportResearchProgress.js";

test("maps durable pipeline checkpoints to eight user-facing stages", () => {
  const stages = buildReportResearchProgress({
    status: "running",
    metadata: {
      current_stage: "image_research",
      template_profile: { has_uploaded_template: true },
      research_plan: { questions: [] },
      pipeline: {
        template_profile: { status: "completed" },
        research: { status: "completed" },
        draft_sections: { status: "completed" },
        bibliography: { status: "completed" },
        image_research: { status: "running", message: "Đang tìm ảnh" },
      },
    },
  });

  assert.equal(stages.length, 8);
  assert.equal(stages.find((item) => item.id === "research").status, "completed");
  assert.equal(stages.find((item) => item.id === "images").status, "running");
  assert.equal(stages.find((item) => item.id === "integrity").status, "pending");
});

test("shows integrity review and summarizes grounded output", () => {
  const metadata = {
    template_profile: { has_uploaded_template: false, citation_style: "apa7" },
    integrity_result: {
      ready: false,
      counts: { sources: 7, cited_sources: 4, images: 2 },
      blocking_errors: [{ code: "unsupported_claim", message: "Thiếu nguồn" }],
      warnings: [{ code: "no_relevant_image", message: "Không có ảnh" }],
    },
  };

  const stages = buildReportResearchProgress({ status: "review_needed", metadata });
  const summary = summarizeResearchSetup(metadata);

  assert.equal(stages.at(-1).status, "review");
  assert.deepEqual(summary, {
    templateMode: "Theo quy chuẩn hiện hành",
    citationStyle: "APA7",
    sources: 7,
    citedSources: 4,
    images: 2,
    blockingErrors: [{ code: "unsupported_claim", message: "Thiếu nguồn" }],
    warnings: [{ code: "no_relevant_image", message: "Không có ảnh" }],
    reviewIssues: [
      { code: "unsupported_claim", message: "Thiếu nguồn", severity: "error", source: "integrity" },
      { code: "no_relevant_image", message: "Không có ảnh", severity: "warning", source: "integrity" },
    ],
    ready: false,
  });
});

test("combines grounding failures and integrity warnings into actionable review issues", () => {
  const summary = summarizeResearchSetup({
    grounding_gate: {
      final: false,
      errors: [
        { type: "NUMERIC_CONFLICT", generated: [125], expected_values: [100] },
        { type: "OFF_TOPIC", term: "ARM" },
      ],
    },
    integrity_result: {
      ready: true,
      blocking_errors: [],
      warnings: [{ code: "no_relevant_image", message: "Không tìm thấy ảnh phù hợp" }],
    },
  });

  assert.deepEqual(summary.reviewIssues, [
    {
      code: "NUMERIC_CONFLICT",
      message: "Số liệu trong báo cáo chưa khớp với dữ liệu nguồn.",
      severity: "error",
      source: "grounding",
    },
    {
      code: "OFF_TOPIC",
      message: "Nội dung không phù hợp với đề tài: ARM.",
      severity: "error",
      source: "grounding",
    },
    {
      code: "no_relevant_image",
      message: "Không tìm thấy ảnh phù hợp",
      severity: "warning",
      source: "integrity",
    },
  ]);
});

test("explains a failed grounding gate even when it has no structured errors", () => {
  const summary = summarizeResearchSetup({
    grounding_gate: { final: false, reason: "NO_VALIDATION_RESULTS", errors: [] },
    integrity_result: { ready: true, blocking_errors: [], warnings: [] },
  });

  assert.deepEqual(summary.reviewIssues, [
    {
      code: "NO_VALIDATION_RESULTS",
      message: "Kiểm định nội dung chưa có đủ kết quả để xác nhận báo cáo.",
      severity: "error",
      source: "grounding",
    },
  ]);
});
