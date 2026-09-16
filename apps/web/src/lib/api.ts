import { formatApiErrorMessage } from "./apiErrors";
import { resolveApiBase } from "./apiBase";

const CONFIGURED_API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8050/api/v1";

export const API_BASE = resolveApiBase(CONFIGURED_API_BASE, typeof window !== "undefined");

export function resolveApiDownloadUrl(downloadUrl?: string): string {
  if (!downloadUrl) return "#";
  if (downloadUrl.startsWith("http")) return downloadUrl;
  const apiOrigin = API_BASE.replace(/\/api\/v1\/?$/, "");
  return `${apiOrigin}${downloadUrl.startsWith("/") ? downloadUrl : `/${downloadUrl}`}`;
}

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data: any) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

export async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 204) {
    return {} as T;
  }

  const contentType = response.headers.get("content-type");
  const isJson = contentType && contentType.includes("application/json");
  const data = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const errorMsg = formatApiErrorMessage(data);
    throw new ApiError(errorMsg, response.status, data);
  }

  return data as T;
}

export const api = {
  // Auth
  auth: {
    register: (data: any) => request<any>("/auth/register", { method: "POST", body: JSON.stringify(data) }),
    login: (data: any) => request<any>("/auth/login", { method: "POST", body: JSON.stringify(data) }),
    google: (data: { credential: string }) => request<any>("/auth/google", { method: "POST", body: JSON.stringify(data) }),
    googleCode: (data: { code: string; redirect_uri?: string }) =>
      request<any>("/auth/google/code", { method: "POST", body: JSON.stringify(data) }),
    me: () => request<any>("/auth/me"),
  },

  // Projects
  projects: {
    list: () => request<any[]>("/projects"),
    get: (id: string) => request<any>(`/projects/${id}`),
    create: (data: any) => request<any>("/projects", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: any) => request<any>(`/projects/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) => request<any>(`/projects/${id}`, { method: "DELETE" }),
  },

  // Files
  files: {
    upload: (formData: FormData) => request<any>("/files/upload", { method: "POST", body: formData }),
    list: () => request<any[]>("/files"),
    listByProject: (projectId: string) => request<any[]>(`/files/project/${projectId}`),
  },

  // Image Assets
  assets: {
    uploadImage: (formData: FormData) => request<any>("/assets/images/upload", { method: "POST", body: formData }),
    listProjectImages: (projectId: string, reportId?: string) => {
      const suffix = reportId ? `?report_id=${encodeURIComponent(reportId)}` : "";
      return request<any[]>(`/assets/images/project/${projectId}${suffix}`);
    },
    searchImages: (data: { query: string; license_mode?: string; max_results?: number }) =>
      request<any>("/assets/images/search", { method: "POST", body: JSON.stringify(data) }),
    importWebImage: (data: any) => request<any>("/assets/images/import-web", { method: "POST", body: JSON.stringify(data) }),
    suggestImageQueries: (data: { section_title?: string; section_text?: string; report_title?: string; max_queries?: number }) =>
      request<any>("/assets/images/suggest-queries", { method: "POST", body: JSON.stringify(data) }),
    imageUrl: (assetId: string) => `${API_BASE}/assets/images/${assetId}/content`,
  },

  // Templates
  templates: {
    list: (params?: { scope?: string; category?: string; search?: string }) => {
      const query = new URLSearchParams();
      if (params?.scope) query.set("scope", params.scope);
      if (params?.category && params.category !== "all") query.set("category", params.category);
      if (params?.search?.trim()) query.set("search", params.search.trim());
      const suffix = query.toString() ? `?${query.toString()}` : "";
      return request<any[]>(`/templates${suffix}`);
    },
    use: (templateId: string) => request<any>(`/templates/${templateId}/use`, { method: "POST" }),
    previewDocx: (formData: FormData) => request<any>("/templates/preview-docx", { method: "POST", body: formData }),
    uploadDocx: (formData: FormData) => request<any>("/templates/upload-docx", { method: "POST", body: formData }),
  },

  // AI Generation, Drafting & Review
  ai: {
    analyzeIntent: (data: any) => request<any>("/ai/analyze-intent", { method: "POST", body: JSON.stringify(data) }),
    generateOutline: (data: any) => request<any>("/ai/generate-outline", { method: "POST", body: JSON.stringify(data) }),
    draftSection: (data: any, options: RequestInit = {}) =>
      request<any>("/ai/draft-section", { ...options, method: "POST", body: JSON.stringify(data) }),
    editSelection: (data: any) => request<any>("/ai/edit-selection", { method: "POST", body: JSON.stringify(data) }),
    copilot: (data: any) => request<any>("/ai/copilot", { method: "POST", body: JSON.stringify(data) }),
    checkReport: (reportId: string) => request<any>(`/ai/check-report/${reportId}`, { method: "POST" }),
    humanize: (data: { text: string; style?: string; custom_instructions?: string }) =>
      request<any>("/ai/humanize", { method: "POST", body: JSON.stringify(data) }),
    generateDiagram: (data: { context_text: string; diagram_type?: string; diagram_title?: string; detail_level?: string }) =>
      request<any>("/ai/diagram/generate", { method: "POST", body: JSON.stringify(data) }),
  },

  // Research
  research: {
    searchWeb: (query: string, maxResults: number = 10, mode: string = "deep") =>
      request<any>(`/research/direct-search?query=${encodeURIComponent(query)}&max_results=${maxResults}&mode=${mode}`, { method: "POST" }),
    search: (projectId: string, query: string, mode: string = "deep") =>
      request<any>(`/research/search?project_id=${projectId}&query=${encodeURIComponent(query)}&mode=${mode}`, { method: "POST" }),
    listSources: (projectId: string) => request<any[]>(`/research/sources/project/${projectId}`),
    addSource: (data: any) => request<any>("/research/sources", { method: "POST", body: JSON.stringify(data) }),
    traceCitation: (citationId: string) => request<any>(`/research/citations/trace/${citationId}`),
    resolveIdentifier: (inputStr: string) =>
      request<any>(`/research/resolve-identifier?input_str=${encodeURIComponent(inputStr)}`, { method: "POST" }),
    exportCitations: (sources: any[], style: string = "IEEE") =>
      request<any>("/research/export", { method: "POST", body: JSON.stringify({ sources, style }) }),
  },

  // Data
  data: {
    profile: (fileId: string) => request<any>(`/data/profile/${fileId}`),
    previewUpload: (formData: FormData) => request<any>("/data/preview-upload", { method: "POST", body: formData }),
    analyzeSheet: (formData: FormData) => request<any>("/data/analyze-sheet", { method: "POST", body: formData }),
    workbookChat: (formData: FormData) => request<any>("/data/workbook-chat", { method: "POST", body: formData }),
    workbookAnalysisAction: (formData: FormData) => request<any>("/data/workbook-analysis-action", { method: "POST", body: formData }),
    applyModifications: (formData: FormData) => request<any>("/data/apply-modifications", { method: "POST", body: formData }),
    actionUndo: (formData: FormData) => request<any>("/data/action-undo", { method: "POST", body: formData }),
    retryGoogleSync: (formData: FormData) => request<any>("/data/google-sync-retry", { method: "POST", body: formData }),
    clearGoogleHighlights: (formData: FormData) => request<any>("/data/clear-google-highlights", { method: "POST", body: formData }),
    crossFileCompare: (formData: FormData) => request<any>("/data/cross-file-compare", { method: "POST", body: formData }),
    aggregate: (data: any) => request<any>("/data/aggregate", { method: "POST", body: JSON.stringify(data) }),
    chartSpec: (data: any) => request<any>("/data/chart-spec", { method: "POST", body: JSON.stringify(data) }),
  },

  // Reports & One-Click Auto Create
  reports: {
    list: () => request<any[]>("/reports"),
    create: (data: any) => request<any>("/reports", { method: "POST", body: JSON.stringify(data) }),
    autoCreate: (formData: FormData) => request<any>("/reports/auto-create", { method: "POST", body: formData }),
    get: (id: string) => request<any>(`/reports/${id}`),
    thumbnail: (id: string) => request<any>(`/reports/${id}/thumbnail`),
    qualityAudit: (id: string) => request<any>(`/reports/${id}/quality-audit`),
    groundingDebug: (id: string) => request<any>(`/reports/${id}/grounding-debug`),
    qualityRepair: (id: string) => request<any>(`/reports/${id}/quality-repair`, { method: "POST" }),
    qualityRepairSection: (reportId: string, sectionId: string) =>
      request<any>(`/reports/${reportId}/sections/${sectionId}/quality-repair`, { method: "POST" }),
    updateSection: (sectionId: string, data: any) => request<any>(`/reports/sections/${sectionId}`, { method: "PUT", body: JSON.stringify(data) }),
    insertAnalysisFinding: (reportId: string, formData: FormData) =>
      request<any>(`/reports/${reportId}/insert-analysis-finding`, { method: "POST", body: formData }),
    getJob: (jobId: string) => request<any>(`/reports/jobs/${jobId}`),
    pauseJob: (jobId: string) => request<any>(`/reports/jobs/${jobId}/pause`, { method: "POST" }),
    resumeJob: (jobId: string) => request<any>(`/reports/jobs/${jobId}/resume`, { method: "POST" }),
    cancelJob: (jobId: string) => request<any>(`/reports/jobs/${jobId}/cancel`, { method: "POST" }),
    retryJob: (jobId: string) => request<any>(`/reports/jobs/${jobId}/retry`, { method: "POST" }),
    bulkPreview: (formData: FormData) => request<any>("/reports/bulk-preview", { method: "POST", body: formData }),
    bulkCreate: (formData: FormData) => request<any>("/reports/bulk-create", { method: "POST", body: formData }),
  },

  // Admin
  admin: {
    dashboard: () => request<any>("/admin/dashboard"),
    users: (search?: string) => {
      const suffix = search?.trim() ? `?search=${encodeURIComponent(search.trim())}` : "";
      return request<any[]>(`/admin/users${suffix}`);
    },
  },

  // Billing & VietQR
  billing: {
    getPlans: () => request<any[]>("/billing/plans"),
    getEntitlements: () => request<any>("/billing/my-entitlements"),
    checkout: (data: { plan_tier: string; success_url?: string; cancel_url?: string }) =>
      request<any>("/billing/checkout", { method: "POST", body: JSON.stringify(data) }),
    confirmPayment: (data: { session_id: string; target_plan: string }) =>
      request<any>("/billing/confirm-payment", { method: "POST", body: JSON.stringify(data) }),
  },

  // Exports
  exports: {
    exportDocx: (data: any) => request<any>("/exports/docx", { method: "POST", body: JSON.stringify(data) }),
    exportPdf: (data: any) => request<any>("/exports/pdf", { method: "POST", body: JSON.stringify(data) }),
    previewReportHtml: (reportId: string) => request<any>(`/exports/report/${reportId}/preview-html`),
    getDownloadUrl: (filename: string) => `${API_BASE}/exports/download/${filename}`,
  },

  // Sources & Verification
  sources: {
    list: (projectId: string, params?: { source_type?: string; verification_status?: string; search?: string }) => {
      const sp = new URLSearchParams();
      if (params?.source_type) sp.append("source_type", params.source_type);
      if (params?.verification_status) sp.append("verification_status", params.verification_status);
      if (params?.search) sp.append("search", params.search);
      const q = sp.toString() ? `?${sp.toString()}` : "";
      return request<{ sources: any[]; stats: any }>(`/projects/${projectId}/sources${q}`);
    },
    get: (sourceId: string) => request<any>(`/sources/${sourceId}`),
    delete: (sourceId: string, force: boolean = false) =>
      request<any>(`/sources/${sourceId}?force=${force}`, { method: "DELETE" }),
    search: (data: { query: string; projectId?: string; providers?: string[]; sort_by?: string; limit?: number }) => {
      const endpoint = data.projectId ? `/projects/${data.projectId}/sources/search` : "/sources/search";
      return request<{ query: string; total: number; results: any[] }>(endpoint, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    importSearch: (projectId: string, sources: any[]) =>
      request<any>(`/projects/${projectId}/sources/search/import`, {
        method: "POST",
        body: JSON.stringify({ sources }),
      }),
    addUrl: (projectId: string, data: { url: string; title?: string; notes?: string }) =>
      request<any>(`/projects/${projectId}/sources/url`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    uploadFile: (projectId: string, formData: FormData) =>
      request<any>(`/projects/${projectId}/sources/upload`, {
        method: "POST",
        body: formData,
      }),
    verify: (sourceId: string) =>
      request<any>(`/sources/${sourceId}/verify`, { method: "POST" }),
    getEvidences: (sourceId: string) =>
      request<{ source_id: string; total: number; evidences: any[] }>(`/sources/${sourceId}/evidences`),
    addEvidence: (sourceId: string, data: any) =>
      request<any>(`/sources/${sourceId}/evidences`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    deleteEvidence: (evidenceId: string) =>
      request<any>(`/evidences/${evidenceId}`, { method: "DELETE" }),
  },

  // Citations
  citations: {
    listByReport: (reportId: string) =>
      request<{ report_id: string; total: number; citations: any[] }>(`/reports/${reportId}/citations`),
    create: (reportId: string, data: any) =>
      request<any>(`/reports/${reportId}/citations`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    reindex: (reportId: string, style: string = "IEEE") =>
      request<any>(`/reports/${reportId}/citations/reindex?style=${style}`, { method: "POST" }),
    coverage: (reportId: string) =>
      request<any>(`/reports/${reportId}/citations/coverage`),
    bibliography: (reportId: string, style: string = "IEEE") =>
      request<any>(`/reports/${reportId}/bibliography?style=${style}`),
    verifySupport: (data: { claim_text: string; evidence_text: string }) =>
      request<any>("/citations/verify-support", {
        method: "POST",
        body: JSON.stringify(data),
      }),
  },

  // Health
  health: () => request<any>("/health"),
};
