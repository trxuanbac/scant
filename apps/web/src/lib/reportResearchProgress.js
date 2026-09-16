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
    ready: integrity?.ready,
  };
}
