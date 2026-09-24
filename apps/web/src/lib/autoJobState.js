export const AUTO_JOB_STATE_KEY = "ai_report_studio:auto_job_state";

const IN_FLIGHT_STATUSES = new Set(["queued", "running", "paused"]);

/**
 * @typedef {Object} AutoJobSnapshotInput
 * @property {string} jobId
 * @property {string | null} [reportId]
 * @property {string} projectType
 * @property {string} status
 * @property {number} [progress]
 * @property {string} [statusMessage]
 * @property {Array} [timeline]
 * @property {Object} [metadata]
 */

export function isAutoJobInFlight(status) {
  return IN_FLIGHT_STATUSES.has(String(status || "").toLowerCase());
}

export function canSafelySwitchAutoContext(status) {
  return !isAutoJobInFlight(status);
}

export function getAutoJobUiState(status, blockingCount = 0, locale = "vi") {
  const normalized = String(status || "").toLowerCase();
  const vi = locale === "vi";
  if (normalized === "review_needed") {
    const count = Math.max(0, Number(blockingCount) || 0);
    return {
      tone: "review",
      terminal: true,
      canCancel: false,
      canRetry: false,
      title: vi
        ? `Báo cáo đã tạo – cần rà soát ${count || "một vài"} nội dung`
        : `Report created – ${count || "some"} item${count === 1 ? "" : "s"} need review`,
    };
  }
  if (normalized === "completed") {
    return {
      tone: "success",
      terminal: true,
      canCancel: false,
      canRetry: false,
      title: vi ? "Báo cáo đã hoàn thành" : "Report completed",
    };
  }
  if (normalized === "cancelled") {
    return {
      tone: "error",
      terminal: true,
      canCancel: false,
      canRetry: true,
      title: vi ? "Đã hủy tạo báo cáo" : "Report creation cancelled",
    };
  }
  if (normalized === "failed") {
    return {
      tone: "error",
      terminal: true,
      canCancel: false,
      canRetry: true,
      title: vi ? "Không thể hoàn tất báo cáo" : "Could not complete the report",
    };
  }
  return {
    tone: "running",
    terminal: false,
    canCancel: isAutoJobInFlight(normalized),
    canRetry: false,
    title: vi ? "AI đang tự động phân tích và tạo tài liệu" : "AI is analyzing and creating the document",
  };
}

export function getAutoJobNextActionMessage(nextAction, locale = "vi") {
  const vi = locale === "vi";
  if (nextAction === "open_report") {
    return vi ? "Báo cáo đã sẵn sàng, bạn có thể mở Studio để chỉnh sửa." : "The report is ready. Open Studio to edit.";
  }
  if (nextAction === "open_report_for_review") {
    return vi
      ? "Báo cáo đã được tạo. Mở Studio để kiểm tra nội dung được đánh dấu hoặc tải bản Word hiện tại."
      : "The report was created. Open Studio to review flagged content or download the current Word draft.";
  }
  if (nextAction === "retry") {
    return vi ? "Quy trình lỗi. Có thể chạy lại sau khi xem thông báo lỗi." : "The workflow failed. You can retry after reviewing the error.";
  }
  if (nextAction === "retry_or_create_new") {
    return vi
      ? "Quy trình đã được hủy. Bạn có thể chạy lại hoặc đổi module để tạo báo cáo mới."
      : "The workflow was cancelled. Retry it or change modules to create a new report.";
  }
  if (nextAction === "resume") {
    return vi ? "Quy trình đang tạm dừng, bấm Tiếp tục để chạy tiếp." : "The workflow is paused. Resume it to continue.";
  }
  return vi ? "Tiếp tục chờ hệ thống xử lý." : "Keep waiting for the workflow to proceed.";
}

export function getAutoExportFailureMessage(reviewCopy = false, locale = "vi") {
  if (reviewCopy) {
    return locale === "vi"
      ? "Không thể xuất bản Word hiện tại. Hãy thử lại hoặc mở báo cáo để rà soát."
      : "Could not export the current Word draft. Try again or open the report for review.";
  }
  return locale === "vi"
    ? "Báo cáo đã tạo nhưng xuất Word thất bại. Hãy thử xuất lại."
    : "The report was created, but Word export failed. Try exporting again.";
}

export function shouldRestoreAutoJob(value) {
  return Boolean(value?.jobId && isAutoJobInFlight(value.status));
}

export function compactAutoJobMetadata(metadata = {}) {
  const keys = [
    "current_stage",
    "pipeline",
    "template_profile",
    "bibliography",
    "image_results",
    "image_warnings",
    "integrity_result",
    "report_id",
  ];
  return Object.fromEntries(keys.filter((key) => metadata?.[key] !== undefined).map((key) => [key, metadata[key]]));
}

/**
 * @param {AutoJobSnapshotInput} input
 */
export function buildAutoJobSnapshot({
  jobId,
  reportId = null,
  projectType,
  status,
  progress = 0,
  statusMessage = "",
  timeline = [],
  metadata = {},
}) {
  return {
    storageKey: AUTO_JOB_STATE_KEY,
    value: {
      jobId,
      reportId,
      projectType,
      status,
      progress,
      statusMessage,
      timeline,
      metadata: compactAutoJobMetadata(metadata),
    },
  };
}
