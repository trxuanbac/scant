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
    ready: false,
  });
});

