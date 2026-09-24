const STAGE_DEFINITIONS = [
  { id: "request", label: "Đọc yêu cầu", aliases: ["understand_request"] },
  { id: "template", label: "Đọc mẫu", aliases: ["template_profile", "understand_request"] },
  { id: "outline", label: "Lập đề cương", aliases: ["generate_outline"] },
  { id: "research", label: "Tìm và kiểm tra nguồn", aliases: ["research"] },
  { id: "writing", label: "Soạn nội dung", aliases: ["draft_sections"] },
  { id: "images", label: "Tìm ảnh phù hợp", aliases: ["image_research"] },
  { id: "references", label: "Tạo tài liệu tham khảo", aliases: ["bibliography", "draft_sections"] },
  { id: "integrity", label: "Kiểm định cuối", aliases: ["integrity", "run_quality_check", "completed", "review_needed"] },
];

const PIPELINE_STAGE_BY_ID = {
  template: "template_profile",
  research: "research",
  writing: "draft_sections",
  images: "image_research",
  references: "bibliography",
  integrity: "integrity",
};

function timelineMatch(timeline, aliases) {
  return [...timeline].reverse().find((item) => aliases.includes(item?.stage));
}

function groundingIssueMessage(issue, code) {
  if (issue?.message) return String(issue.message);
  if (code === "NUMERIC_CONFLICT") return "Số liệu trong báo cáo chưa khớp với dữ liệu nguồn.";
  if (code === "OFF_TOPIC" || code === "FINAL_DOC_OFF_TOPIC") {
    return issue?.term
      ? `Nội dung không phù hợp với đề tài: ${issue.term}.`
      : "Báo cáo có nội dung chưa phù hợp với đề tài.";
  }
  if (code === "HALLUCINATED_ENTITY") {
    const entities = Array.isArray(issue?.entities) ? issue.entities.filter(Boolean).join(", ") : "";
    return entities
      ? `Có thông tin chưa được dữ liệu nguồn xác nhận: ${entities}.`
      : "Có thông tin chưa được dữ liệu nguồn xác nhận.";
  }
  if (code === "TEMPLATE_LEAK" || code === "FINAL_DOC_DIRTY_TEXT") {
    return "Báo cáo còn nội dung hướng dẫn hoặc ký hiệu mẫu cần được làm sạch.";
  }
  if (code === "UNSUPPORTED_CAUSAL_CLAIM") {
    return issue?.text
      ? `Nhận định nguyên nhân chưa có bằng chứng: ${issue.text}`
      : "Báo cáo có nhận định nguyên nhân chưa được nguồn dữ liệu hỗ trợ.";
  }
  if (code === "NO_VALIDATION_RESULTS") {
    return "Kiểm định nội dung chưa có đủ kết quả để xác nhận báo cáo.";
  }
  if (issue?.text) return String(issue.text);
  if (issue?.term) return `${code}: ${issue.term}`;
  return `Kiểm định nội dung phát hiện vấn đề: ${code}.`;
}

function normalizeReviewIssue(issue, severity, source, fallbackCode) {
  const value = issue && typeof issue === "object" ? issue : { message: String(issue || "") };
  const code = String(value.code || value.type || fallbackCode);
  return {
    code,
    message: source === "grounding"
      ? groundingIssueMessage(value, code)
      : String(value.message || value.text || code),
    severity,
    source,
  };
}

function buildReviewIssues(metadata, integrity) {
  const grounding = metadata?.grounding_gate || {};
  const blocking = Array.isArray(integrity?.blocking_errors) ? integrity.blocking_errors : [];
  const warnings = Array.isArray(integrity?.warnings) ? integrity.warnings : [];
  const groundingErrors = Array.isArray(grounding?.errors) ? grounding.errors : [];
  const issues = [
    ...blocking.map((issue, index) => normalizeReviewIssue(issue, "error", "integrity", `integrity_error_${index + 1}`)),
    ...groundingErrors.map((issue, index) => normalizeReviewIssue(issue, "error", "grounding", `grounding_error_${index + 1}`)),
    ...warnings.map((issue, index) => normalizeReviewIssue(issue, "warning", "integrity", `integrity_warning_${index + 1}`)),
  ];

  if (grounding?.final === false && groundingErrors.length === 0) {
    issues.splice(blocking.length, 0, normalizeReviewIssue(
      { type: grounding.reason || "grounding_review" },
      "error",
      "grounding",
      "grounding_review",
    ));
  }

  const seen = new Set();
  return issues.filter((issue) => {
    const key = `${issue.code}|${issue.message}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/**
 * @param {{ metadata?: Record<string, any>, timeline?: Array<Record<string, any>>, status?: string }} input
 */
export function buildReportResearchProgress({ metadata = {}, timeline = [], status = "queued" } = {}) {
  const pipeline = metadata?.pipeline || {};
  const currentStage = metadata?.current_stage || timeline.at(-1)?.stage || "queued";
  const currentIndex = STAGE_DEFINITIONS.findIndex((stage) => stage.aliases.includes(currentStage));

  return STAGE_DEFINITIONS.map((definition, index) => {
    const pipelineKey = PIPELINE_STAGE_BY_ID[definition.id];
    const checkpoint = pipelineKey ? pipeline[pipelineKey] : null;
    const timelineItem = timelineMatch(timeline, definition.aliases);
    let stageStatus = checkpoint?.status || (timelineItem ? "completed" : "pending");

    if (stageStatus === "failed") stageStatus = "failed";
    else if (checkpoint?.status === "running" || definition.aliases.includes(currentStage)) stageStatus = "running";
    else if (currentIndex >= 0 && index < currentIndex) stageStatus = "completed";

    if (definition.id === "request" && (metadata?.template_profile || currentIndex > 0)) stageStatus = "completed";
    if (definition.id === "outline" && (metadata?.research_plan || currentIndex > 2)) stageStatus = "completed";
    if (definition.id === "integrity" && status === "review_needed") stageStatus = "review";
    if (definition.id === "integrity" && status === "completed") stageStatus = "completed";
    if (status === "failed" && definition.aliases.includes(currentStage)) stageStatus = "failed";

    return {
      id: definition.id,
      label: definition.label,
      status: stageStatus,
      message: checkpoint?.message || timelineItem?.message || "",
    };
  });
}

/** @param {Record<string, any>} metadata */
export function summarizeResearchSetup(metadata = {}) {
  const profile = metadata?.template_profile || {};
  const integrity = metadata?.integrity_result || {};
  return {
    templateMode: profile.has_uploaded_template ? "Theo mẫu đã tải" : "Theo quy chuẩn hiện hành",
    citationStyle: String(profile.citation_style || "numbered").toUpperCase(),
    sources: Number(integrity?.counts?.sources ?? metadata?.source_candidates?.length ?? 0),
    citedSources: Number(integrity?.counts?.cited_sources ?? metadata?.bibliography?.source_ids?.length ?? 0),
    images: Number(integrity?.counts?.images ?? metadata?.image_results?.filter?.((item) => item.status === "inserted")?.length ?? 0),
    blockingErrors: integrity?.blocking_errors || [],
    warnings: integrity?.warnings || [],
    reviewIssues: buildReviewIssues(metadata, integrity),
    ready: integrity?.ready,
  };
}
