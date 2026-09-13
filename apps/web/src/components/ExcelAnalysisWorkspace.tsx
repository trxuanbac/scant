"use client";

import { GoogleDataConnection } from "@/components/GoogleDataConnection";

import { buildWorkbookScope } from "@/lib/workbookScope";

import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import {
  FileSpreadsheet,
  BarChart3,
  PieChart,
  LineChart,
  Sparkles,
  ShieldCheck,
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle2,
  RefreshCw,
  FileText,
  TrendingUp,
  Table as TableIcon,
  Layers,
  ChevronDown,
  Zap,
  Download,
  Filter,
  Check,
  ArrowUpDown,
  Search,
  Trash2,
  PanelRightClose,
  Eye,
  EyeOff,
  Palette,
  X,
} from "lucide-react";
import SpreadsheetPreview, { VisualWorkbook, CellHighlightInfo } from "@/components/SpreadsheetPreview";
import { WorkbookLedger, PersistentSpreadsheetActionCard as SpreadsheetActionCard } from "@/components/WorkbookLedger";
import ExcelAIChatPanel from "@/components/ExcelAIChatPanel";
import { api, resolveApiDownloadUrl } from "@/lib/api";
import {
  buildExcelAnalysisSessionKey,
  createExcelAnalysisSnapshot,
  parseExcelAnalysisSnapshot,
} from "@/lib/excelAnalysisSession";

export interface AnalysisLayer {
  id: string;
  sheet: string;
  prompt: string;
  color: string;
  colorName: string;
  borderColor: string;
  cells: string[];
  matchedDetails?: Array<{ address: string; value: any; reason?: string }>;
  googleSync?: {
    isGoogleSheet: boolean;
    spreadsheetId?: string;
    sheetId?: number;
    synced: boolean;
    verified: boolean;
    error?: string | null;
  };
  createdAt: Date;
  visible: boolean;
}

export const COLOR_ROTATION_PRESETS = [
  { color: "#FEF08A", colorName: "Vàng", borderColor: "#CA8A04", textColor: "#713F12" },
  { color: "#FED7AA", colorName: "Cam", borderColor: "#EA580C", textColor: "#7C2D12" },
  { color: "#E9D5FF", colorName: "Tím", borderColor: "#9333EA", textColor: "#581C87" },
  { color: "#BAE6FD", colorName: "Xanh", borderColor: "#0284C7", textColor: "#075985" },
  { color: "#FECDD3", colorName: "Đỏ", borderColor: "#E11D48", textColor: "#881337" },
  { color: "#BBF7D0", colorName: "Xanh lá", borderColor: "#16A34A", textColor: "#14532D" },
];

function normalizePromptColorText(text: string) {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d");
}

function resolvePromptHighlightColor(prompt: string, fallbackColor: string) {
  const normalized = normalizePromptColorText(prompt);
  const colorRules = [
    { color: "#FECDD3", patterns: ["màu đỏ", "mau do", "tô đỏ", "to do", "boi do"] },
    { color: "#FEF08A", patterns: ["màu vàng", "mau vang", "tô vàng", "to vang", "boi vang"] },
    { color: "#BBF7D0", patterns: ["màu xanh lá", "mau xanh la", "tô xanh lá", "to xanh la", "boi xanh la"] },
    { color: "#BAE6FD", patterns: ["màu xanh", "mau xanh", "tô xanh", "to xanh", "boi xanh"] },
    { color: "#E9D5FF", patterns: ["màu tím", "mau tim", "tô tím", "to tim", "boi tim"] },
    { color: "#FED7AA", patterns: ["màu cam", "mau cam", "tô cam", "to cam", "boi cam"] },
  ];
  return colorRules.find((rule) => rule.patterns.some((pattern) => normalized.includes(normalizePromptColorText(pattern))))?.color || fallbackColor;
}

function renderInlineMarkdown(text?: string | null): React.ReactNode {
  if (!text) return null;
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={idx} className="font-bold">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <React.Fragment key={idx}>{part}</React.Fragment>;
  });
}

function shouldUseSelectedRangeForAnalysis(prompt: string, selectedRange: string | null): boolean {
  if (!selectedRange) return false;
  if (selectedRange.includes(":")) return true;
  const normalized = normalizePromptColorText(prompt);
  const selectionPhrases = ["vùng chọn", "vung chon", "ô đang chọn", "o dang chon", "ô này", "o nay", "selected cell"];
  return selectionPhrases.some((phrase) => normalized.includes(normalizePromptColorText(phrase)));
}

function getMatchedCellAddress(cell: any): string {
  if (!cell) return "";
  if (typeof cell === "string") return cell.trim();
  return String(cell.address || cell.cell || "").trim();
}

export interface SheetAnalysisData {
  sheet_name: string;
  all_sheets: string[];
  overview: {
    sheet_name: string;
    total_rows: number;
    total_columns: number;
    total_cells: number;
    populated_cells: number;
    empty_cells: number;
    empty_pct: number;
    duplicate_rows: number;
    duplicate_pct: number;
    numeric_columns_count: number;
    text_columns_count: number;
    category_columns_count: number;
    date_columns_count: number;
    id_columns_count: number;
  };
  columns: Array<{
    name: string;
    type: string;
    total_count: number;
    non_null_count: number;
    missing_count: number;
    missing_pct: number;
    unique_count: number;
    unique_pct: number;
    sample_values: string[];
    min?: number;
    max?: number;
    mean?: number;
    median?: number;
    sum?: number;
    std?: number;
    q1?: number;
    q3?: number;
    outliers_count?: number;
    top_values?: Array<{ value: string; count: number; pct: number }>;
    min_date?: string;
    max_date?: string;
    duration_days?: number;
  }>;
  data_quality_issues: Array<{
    id: string;
    type: string;
    severity: "high" | "medium" | "low";
    title: string;
    message: string;
    affected_rows_count: number;
    affected_columns: string[];
    suggestion: string;
  }>;
  charts: Array<{
    id: string;
    title: string;
    type: "bar" | "horizontal_bar" | "pie" | "line";
    x_axis?: string;
    y_axis?: string;
    data: Array<{ label: string; value: number; mean?: number; count?: number; pct?: number }>;
    description?: string;
  }>;
  ai_insights: {
    summary: string;
    key_findings: Array<{
      title: string;
      description: string;
      evidence?: string;
      importance?: "high" | "medium" | "low";
    }>;
    trends: string[];
    anomalies: string[];
    recommendations: string[];
    business_meaning: string;
  };
  sample_rows: Array<Record<string, any>>;
}

interface ExcelAnalysisWorkspaceProps {
  fileName?: string;
  file?: File | null;
  fileId?: string;
  dataSourceUrl?: string;
  visualWorkbook?: VisualWorkbook | null;
  initialAnalysis?: SheetAnalysisData | null;
  initialAnalysisResult?: any | null;
  legacyData?: any;
  onGenerateDocx?: (analysisResult?: any) => void;
  onSwitchToReportMode?: () => void;
  onBackToSetup?: () => void;
  isGeneratingDocx?: boolean;
  initialAnalysisPrompt?: string | null;
  preferredSheet?: string | null;
  locale?: string;
}

export default function ExcelAnalysisWorkspace({
  fileName = "Bảng tính dữ liệu",
  file,
  fileId,
  dataSourceUrl,
  visualWorkbook,
  initialAnalysis,
  initialAnalysisResult = null,
  legacyData,
  onGenerateDocx,
  onSwitchToReportMode,
  onBackToSetup,
  isGeneratingDocx = false,
  initialAnalysisPrompt = null,
  preferredSheet = null,
  locale = "vi",
}: ExcelAnalysisWorkspaceProps) {
  // All available sheet names
  const sheetNames = useMemo<string[]>(() => {
    if (visualWorkbook?.sheets && visualWorkbook.sheets.length > 0) {
      return visualWorkbook.sheets.map((s) => s.name);
    }
    if (initialAnalysis?.all_sheets && initialAnalysis.all_sheets.length > 0) {
      return initialAnalysis.all_sheets;
    }
    if (legacyData?.sheets && legacyData.sheets.length > 0) {
      return legacyData.sheets.map((s: any) => s.name);
    }
    return ["Sheet1"];
  }, [visualWorkbook, initialAnalysis, legacyData]);
  const sessionStorageKey = useMemo(
    () => buildExcelAnalysisSessionKey({ fileName, fileId, dataSourceUrl }),
    [dataSourceUrl, fileId, fileName]
  );
  const restoredSession = useMemo(() => {
    if (typeof window === "undefined") return null;
    return parseExcelAnalysisSnapshot(window.localStorage.getItem(sessionStorageKey));
  }, [sessionStorageKey]);

  const [activeSheetName, setActiveSheetName] = useState<string>(
    (restoredSession?.activeSheetName && sheetNames.includes(restoredSession.activeSheetName)
      ? restoredSession.activeSheetName
      : null) ||
      preferredSheet ||
      initialAnalysis?.sheet_name ||
      sheetNames[0] ||
      "Sheet1"
  );
  const [activeTab, setActiveTab] = useState<"overview" | "stats" | "charts" | "quality" | "ai">("overview");
  const [isChatOpen, setIsChatOpen] = useState<boolean>(false);
  const [hasOpenedChat, setHasOpenedChat] = useState<boolean>(false);
  const chatPanelRef = useRef<HTMLDivElement | null>(null);
  const [analysisBySheet, setAnalysisBySheet] = useState<Record<string, SheetAnalysisData>>(() => {
    if (restoredSession?.analysisBySheet && Object.keys(restoredSession.analysisBySheet).length > 0) {
      return restoredSession.analysisBySheet as Record<string, SheetAnalysisData>;
    }
    if (initialAnalysis && initialAnalysis.sheet_name) {
      return { [initialAnalysis.sheet_name]: initialAnalysis };
    }
    return {};
  });
  const [isLoadingAnalysis, setIsLoadingAnalysis] = useState(false);
  const [isReadingAllSheets, setIsReadingAllSheets] = useState(false);
  const [selectedAnalysisSheets, setSelectedAnalysisSheets] = useState<string[]>(() => {
    const saved = restoredSession?.selectedAnalysisSheets?.filter((name: string) => sheetNames.includes(name));
    return saved?.length ? saved : [...sheetNames];
  });
  const analysisScope = buildWorkbookScope(sheetNames, selectedAnalysisSheets);
  const chatScopeMode = analysisScope?.type || "sheets";

  const [isAnalysisPanelOpen, setIsAnalysisPanelOpen] = useState(false);
  const [selectedChartIdx, setSelectedChartIdx] = useState(0);
  const [columnSearch, setColumnSearch] = useState("");
  const [selectedColType, setSelectedColType] = useState<string>("all");

  // Analysis Layers state per sheet
  const [analysisLayersBySheet, setAnalysisLayersBySheet] = useState<Record<string, AnalysisLayer[]>>(() => {
    if (restoredSession?.analysisLayersBySheet && Object.keys(restoredSession.analysisLayersBySheet).length > 0) {
      return restoredSession.analysisLayersBySheet as Record<string, AnalysisLayer[]>;
    }
    return {};
  });

  const [selectedRange, setSelectedRange] = useState<string | null>(null);
  const [scrollToCellAddress, setScrollToCellAddress] = useState<string | null>(null);
  const [analysisPrompt, setAnalysisPrompt] = useState(restoredSession?.analysisPrompt || initialAnalysisPrompt || "");
  const [activeHighlightColor, setActiveHighlightColor] = useState<string>(restoredSession?.activeHighlightColor || "#FEF08A");
  const conversationKey = useRef<string | null>(null);
  const [isRunningAnalysisAction, setIsRunningAnalysisAction] = useState(false);
  const [analysisActionStatus, setAnalysisActionStatus] = useState<string | null>(
    restoredSession?.analysisActionStatus ||
      (initialAnalysisResult ? (locale === "vi" ? "Đã chạy phân tích ban đầu." : "Initial analysis completed.") : null)
  );
  const [lastAnalysisResultBySheet, setLastAnalysisResultBySheet] = useState<Record<string, any>>(
    restoredSession?.lastAnalysisResultBySheet && Object.keys(restoredSession.lastAnalysisResultBySheet).length > 0
      ? restoredSession.lastAnalysisResultBySheet
      : initialAnalysisResult && initialAnalysisResult.context?.sheet
      ? { [initialAnalysisResult.context.sheet]: initialAnalysisResult }
      : {}
  );
  const lastAnalysisResult =
    lastAnalysisResultBySheet[activeSheetName] ||
    lastAnalysisResultBySheet["workbook"] ||
    null;
  const [analysisHistory, setAnalysisHistory] = useState<any[]>(
    restoredSession?.analysisHistory?.length
      ? restoredSession.analysisHistory
      : initialAnalysisResult
      ? [initialAnalysisResult.analysis_history_item || initialAnalysisResult]
      : []
  );

  const activeLayers = (analysisLayersBySheet[activeSheetName] || []).filter((l) => l.visible);
  const cellHighlightsForActiveSheet = useMemo(() => {
    const map: Record<string, CellHighlightInfo> = {};
    activeLayers.forEach((layer) => {
      layer.cells.forEach((addr) => {
        map[addr] = {
          color: layer.color,
          colorName: layer.colorName,
          queryPrompt: layer.prompt,
          reason: `Thuộc câu hỏi: "${layer.prompt}"`,
          layerId: layer.id,
        };
      });
    });
    return map;
  }, [activeLayers]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const hasPersistentAnalysis =
      analysisHistory.length > 0 ||
      Object.keys(analysisBySheet).length > 0 ||
      Object.keys(lastAnalysisResultBySheet).length > 0 ||
      Object.values(analysisLayersBySheet).some((layers) => layers.length > 0);
    if (!hasPersistentAnalysis) return;
    const snapshot = createExcelAnalysisSnapshot({
      activeSheetName,
      analysisPrompt,
      activeHighlightColor,
      analysisActionStatus,
      chatScopeMode,
      selectedAnalysisSheets,
      analysisHistory,
      analysisBySheet,
      analysisLayersBySheet,
      lastAnalysisResultBySheet,
    });
    window.localStorage.setItem(sessionStorageKey, JSON.stringify(snapshot));
  }, [
    activeHighlightColor,
    activeSheetName,
    analysisActionStatus,
    analysisBySheet,
    analysisHistory,
    analysisLayersBySheet,
    analysisPrompt,
    chatScopeMode,
    selectedAnalysisSheets,
    lastAnalysisResultBySheet,
    sessionStorageKey,
  ]);

  const handleSelectSheet = useCallback((sheetName: string) => {
    setActiveSheetName(sheetName);
    setSelectedAnalysisSheets([sheetName]);
  }, []);

  const handleToggleLayerVisibility = useCallback((sheetName: string, layerId: string) => {
    setAnalysisLayersBySheet((prev) => {
      const list = prev[sheetName] || [];
      return {
        ...prev,
        [sheetName]: list.map((l) => (l.id === layerId ? { ...l, visible: !l.visible } : l)),
      };
    });
  }, []);

  const handleRemoveLayer = useCallback((sheetName: string, layerId: string) => {
    setAnalysisLayersBySheet((prev) => {
      const list = prev[sheetName] || [];
      return {
        ...prev,
        [sheetName]: list.filter((l) => l.id !== layerId),
      };
    });
  }, []);

  const handleClearAllLayers = useCallback((sheetName: string) => {
    setAnalysisLayersBySheet((prev) => ({
      ...prev,
      [sheetName]: [],
    }));

  }, []);

  // Keyboard shortcut: Cmd+Shift+I or Ctrl+Shift+I toggles analysis panel
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "i") {
        e.preventDefault();
        setIsAnalysisPanelOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleHighlightCells = useCallback(
    (sheetName: string, cells: string[], color = "#FEF08A", reason = "Đánh dấu AI") => {
      const preset = COLOR_ROTATION_PRESETS.find((p) => p.color === color) || COLOR_ROTATION_PRESETS[0];
      const newLayer: AnalysisLayer = {
        id: `layer_${Date.now()}`,
        sheet: sheetName,
        prompt: reason,
        color,
        colorName: preset.colorName,
        borderColor: preset.borderColor,
        cells,
        createdAt: new Date(),
        visible: true,
      };
      setAnalysisLayersBySheet((prev) => ({
        ...prev,
        [sheetName]: [newLayer, ...(prev[sheetName] || [])],
      }));
    },
    []
  );

  const handleClearHighlights = useCallback(
    (sheetName: string) => {
      handleClearAllLayers(sheetName);
    },
    [handleClearAllLayers]
  );

  const handleScrollToCell = useCallback((address: string) => {
    setScrollToCellAddress(address);
    setTimeout(() => setScrollToCellAddress(null), 300);
  }, []);

  // Apply initial analysis result actions on mount or when changed
  useEffect(() => {
    if (initialAnalysisResult) {
      const sheet = initialAnalysisResult.context?.sheet || activeSheetName;
      setLastAnalysisResultBySheet((prev) => ({
        ...prev,
        [sheet]: initialAnalysisResult,
      }));
    }
  }, [initialAnalysisResult, activeSheetName]);

  const [isExportingExcel, setIsExportingExcel] = useState(false);
  const [isInsertingDocx, setIsInsertingDocx] = useState(false);
  const [isRetryingGoogleSync, setIsRetryingGoogleSync] = useState(false);

  const handleRetryGoogleSync = useCallback(
    async (resItem?: any) => {
      const targetRes = resItem || lastAnalysisResultBySheet[activeSheetName];
      if (!targetRes || isRetryingGoogleSync) return;

      const gs = targetRes.google_sync;
      const targetCells = [...new Set((analysisLayersBySheet[activeSheetName] || []).filter((layer) => layer.visible).flatMap((layer) => layer.cells))];
      if (!targetCells.length) {
        setAnalysisActionStatus(locale === "vi" ? "Hãy xem trước và xác nhận lớp tô màu trước khi đồng bộ." : "Preview and confirm a highlight layer before syncing.");
        return;
      }
      if (!window.confirm(locale === "vi" ? `Ghi màu ${activeHighlightColor} vào ${targetCells.length} ô trên sheet ${activeSheetName} của Google Sheets gốc?` : `Write ${activeHighlightColor} to ${targetCells.length} cells in ${activeSheetName} on the original Google Sheet?`)) return;

      setIsRetryingGoogleSync(true);
      try {
        const fd = new FormData();
        fd.append("spreadsheet_id", gs?.spreadsheet_id || dataSourceUrl || "");
        fd.append("sheet_name", activeSheetName || "Sheet1");
        fd.append("cells", JSON.stringify(targetCells));
        fd.append("color_hex", activeHighlightColor || "#FEF08A");

        const out = await api.data.retryGoogleSync(fd);
        if (out?.ok && out.synced_to_google_sheets && out.verified_on_google_sheets) {
          setAnalysisActionStatus(
            locale === "vi"
              ? "✓ Đã đồng bộ và xác minh màu trên Google Sheets gốc thành công!"
              : "✓ Synced and verified on Google Sheets!"
          );
          setLastAnalysisResultBySheet((prev) => ({
            ...prev,
            [activeSheetName]: {
              ...prev[activeSheetName],
              google_sync: {
                ...prev[activeSheetName]?.google_sync,
                synced_to_google_sheets: true,
                verified_on_google_sheets: true,
                google_sync_error: null,
              },
            },
          }));
        } else {
          setAnalysisActionStatus(
            locale === "vi"
              ? `Lỗi đồng bộ Google Sheets: ${out?.error || "Vui lòng cấp quyền chỉnh sửa."}`
              : `Google Sheets sync error: ${out?.error || "Please grant edit permission."}`
          );
        }
      } catch (err: any) {
        setAnalysisActionStatus(
          locale === "vi"
            ? `Lỗi kết nối Google Sheets: ${err.message}`
            : `Google Sheets connection error: ${err.message}`
        );
      } finally {
        setIsRetryingGoogleSync(false);
      }
    },
    [activeHighlightColor, activeSheetName, analysisLayersBySheet, dataSourceUrl, isRetryingGoogleSync, lastAnalysisResultBySheet, locale]
  );

  const handlePushFindingToDocx = useCallback(async () => {
    const currentRes = lastAnalysisResultBySheet[activeSheetName] || lastAnalysisResultBySheet["workbook"];
    if (!currentRes) return;

    if (onGenerateDocx) {
      setAnalysisActionStatus(locale === "vi" ? "Đang đưa kết quả phân tích vào báo cáo Word..." : "Sending this analysis to the Word report...");
      onGenerateDocx(currentRes);
      return;
    }

    setIsInsertingDocx(true);
    try {
      const reports = await api.reports.list();
      if (reports && reports.length > 0) {
        const targetReport = reports[0];
        const fd = new FormData();
        fd.append("title", currentRes.title || `Phân tích: ${currentRes.prompt || activeSheetName}`);
        fd.append("summary", currentRes.answer || "");
        const res = await api.reports.insertAnalysisFinding(targetReport.id, fd);
        if (res?.ok) {
          setAnalysisActionStatus(locale === "vi" ? `Đã chèn kết quả phân tích vào Báo cáo '${targetReport.title || "hiện tại"}'!` : "Inserted finding into report successfully!");
        }
      }
    } catch (err: any) {
      console.error("Push to docx error:", err);
      setAnalysisActionStatus(locale === "vi" ? `Không thể chèn vào DOCX: ${err.message}` : `Insert DOCX error: ${err.message}`);
    } finally {
      setIsInsertingDocx(false);
    }
  }, [activeSheetName, lastAnalysisResultBySheet, locale, onGenerateDocx]);

  const handleExportHighlightedExcel = useCallback(async () => {
    setIsExportingExcel(true);
    try {
      const activeLayers = analysisLayersBySheet[activeSheetName] || [];
      const cellsToHighlight: string[] = [];
      let highlightColor = activeHighlightColor || "#FEF08A";

      activeLayers.forEach((layer) => {
        if (layer.visible && Array.isArray(layer.cells)) {
          cellsToHighlight.push(...layer.cells);
          if (layer.color) highlightColor = layer.color;
        }
      });

      if (!cellsToHighlight.length) throw new Error(locale === "vi" ? "Hãy xác nhận lớp tô màu trước khi xuất XLSX." : "Confirm a highlight layer before exporting XLSX.");
      const colors = new Set(activeLayers.filter((layer) => layer.visible && layer.cells.length).map((layer) => layer.color));
      if (colors.size > 1) throw new Error(locale === "vi" ? "Mỗi lần xuất hiện hỗ trợ một màu. Hãy ẩn các lớp màu khác trước khi xuất." : "Export currently supports one color. Hide other color layers first.");

      const fd = new FormData();
      if (file) {
        fd.append("file", file);
      } else if (fileId) {
        fd.append("file_id", fileId);
      } else if (dataSourceUrl) {
        fd.append("data_source_url", dataSourceUrl);
      }
      fd.append("sheet_name", activeSheetName || "Sheet1");
      fd.append("cells", JSON.stringify(cellsToHighlight));
      fd.append("color_hex", highlightColor.replace("#", ""));

      const res = await api.data.applyModifications(fd);
      if (res?.download_url) {
        const fullUrl = resolveApiDownloadUrl(res.download_url);
        const a = document.createElement("a");
        a.href = fullUrl;
        a.download = res.modified_file_name || "highlighted_workbook.xlsx";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setAnalysisActionStatus(locale === "vi" ? "Đã tải file Excel đã bôi màu thành công!" : "Downloaded highlighted Excel successfully!");
      }
    } catch (err: any) {
      console.error("Export Excel error:", err);
      setAnalysisActionStatus(locale === "vi" ? `Không thể tải Excel: ${err.message}` : `Export error: ${err.message}`);
    } finally {
      setIsExportingExcel(false);
    }
  }, [activeHighlightColor, activeSheetName, analysisLayersBySheet, dataSourceUrl, file, fileId, locale]);

  const handleRunAnalysisAction = useCallback(
    async (promptOverride?: string) => {
      const prompt = (promptOverride || analysisPrompt).trim();
      if (!prompt || isRunningAnalysisAction || !analysisScope) return;

      // 1. Reset old analysis result on current sheet before running
      setLastAnalysisResultBySheet((prev) => ({
        ...prev,
        [activeSheetName]: null,
      }));

      setIsRunningAnalysisAction(true);
      const targetLabel = analysisScope.type === "workbook" ? (locale === "vi" ? "toàn bộ workbook" : "the entire workbook") : analysisScope.type === "sheets" ? analysisScope.sheets.join(", ") : analysisScope.sheet;
      setAnalysisActionStatus(locale === "vi" ? `Đang phân tích "${prompt}" trên ${targetLabel}...` : `Analyzing "${prompt}" on ${targetLabel}...`);
      try {
        const resolvedHighlightColor = resolvePromptHighlightColor(prompt, activeHighlightColor);
        setActiveHighlightColor(resolvedHighlightColor);
        const formData = new FormData();
        if (file) formData.append("file", file);
        if (fileId) formData.append("file_id", fileId);
        if (dataSourceUrl) formData.append("data_source_url", dataSourceUrl);
        formData.append("sheet_name", analysisScope.type === "sheet" ? analysisScope.sheet : activeSheetName);
        formData.append("scope", JSON.stringify(analysisScope));
        formData.append("prompt", prompt);
        const shouldUseSelectedRange = analysisScope.type === "sheet" && analysisScope.sheet === activeSheetName && shouldUseSelectedRangeForAnalysis(prompt, selectedRange);
        if (shouldUseSelectedRange) formData.append("selected_range", selectedRange as string);
        formData.append("highlight_color", resolvedHighlightColor);
        conversationKey.current ||= crypto.randomUUID();
      formData.append("conversation_id", conversationKey.current);

        const res = await api.data.workbookAnalysisAction(formData);
        const resolvedSheet = res.context?.sheet && res.context.sheet !== "workbook" && res.context.sheet !== "multiple_sheets"
          ? res.context.sheet
          : activeSheetName;
        if (resolvedSheet !== activeSheetName) setActiveSheetName(resolvedSheet);
        setLastAnalysisResultBySheet((prev) => ({
          ...prev,
          [resolvedSheet]: res,
        }));
        setAnalysisHistory((prev) => [res.analysis_history_item || { prompt, sheet: resolvedSheet }, ...prev].slice(0, 8));

        setAnalysisActionStatus(res.answer || (locale === "vi" ? "Đã chạy phân tích thành công." : "Analysis complete."));
      } catch (err: any) {
        setAnalysisActionStatus(
          locale === "vi"
            ? `Lỗi chạy phân tích: ${err.message || "Vui lòng thử lại."}`
            : `Analysis error: ${err.message || "Please retry."}`
        );
      } finally {
        setIsRunningAnalysisAction(false);
      }
    },
    [activeHighlightColor, activeSheetName, analysisPrompt, analysisScope, dataSourceUrl, file, fileId, isRunningAnalysisAction, locale, selectedRange]
  );

  useEffect(() => {
    if (initialAnalysisPrompt && initialAnalysisPrompt.trim()) {
      setAnalysisPrompt(initialAnalysisPrompt.trim());
    }
  }, [initialAnalysisPrompt]);

  useEffect(() => {
    if (!isChatOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (!chatPanelRef.current || chatPanelRef.current.contains(event.target as Node)) {
        return;
      }
      setIsChatOpen(false);
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isChatOpen]);

  const floatingChatButtonOffsetClass = "bottom-44 right-6";

  // Keep activeSheetName valid if sheetNames change
  useEffect(() => {
    if (sheetNames.length > 0 && !sheetNames.includes(activeSheetName)) {
      setActiveSheetName(sheetNames[0]);
    }
  }, [sheetNames, activeSheetName]);

  // Fetch sheet analysis if not already cached
  const fetchSheetAnalysis = useCallback(
    async (sheetName: string, forceRefresh = false) => {
      if (!forceRefresh && analysisBySheet[sheetName]) {
        return analysisBySheet[sheetName];
      }

      setIsLoadingAnalysis(true);
      try {
        const formData = new FormData();
        if (file) {
          formData.append("file", file);
        } else if (fileId) {
          formData.append("file_id", fileId);
        } else if (dataSourceUrl) {
          formData.append("data_source_url", dataSourceUrl);
        }
        formData.append("sheet_name", sheetName);
        if (forceRefresh) {
          formData.append("force_refresh", "true");
        }

        const res = await api.data.analyzeSheet(formData);
        if (res?.ok && res.analysis) {
          setAnalysisBySheet((prev) => ({
            ...prev,
            [sheetName]: res.analysis,
          }));
          return res.analysis as SheetAnalysisData;
        }
        return null;
      } catch (err) {
        console.error("Failed to analyze sheet:", err);
        return null;
      } finally {
        setIsLoadingAnalysis(false);
      }
    },
    [file, fileId, dataSourceUrl, analysisBySheet]
  );

  const handleReadAllSheets = useCallback(async () => {
    if (isReadingAllSheets || sheetNames.length === 0) return;
    setIsReadingAllSheets(true);
    setAnalysisActionStatus(
      locale === "vi"
        ? `Đang đọc toàn bộ ${sheetNames.length} sheet...`
        : `Reading all ${sheetNames.length} sheets...`
    );

    let readCount = 0;
    let dataCount = 0;
    const sheetNamesWithData: string[] = [];

    try {
      for (const sheetName of sheetNames) {
        const analysis = await fetchSheetAnalysis(sheetName);
        if (analysis) {
          readCount += 1;
          const populatedCells = Number(analysis.overview?.populated_cells || 0);
          const totalRows = Number(analysis.overview?.total_rows || 0);
          const totalColumns = Number(analysis.overview?.total_columns || 0);
          if (populatedCells > 0 || totalRows > 0 || totalColumns > 0) {
            dataCount += 1;
            sheetNamesWithData.push(sheetName);
          }
        }
      }
      const sheetList = sheetNamesWithData.slice(0, 4).join(", ");
      const moreCount = Math.max(sheetNamesWithData.length - 4, 0);
      setSelectedAnalysisSheets([...sheetNames]);
      setAnalysisActionStatus(
        locale === "vi"
          ? `Đã đọc ${readCount}/${sheetNames.length} sheet. Có thông tin trong ${dataCount} sheet${sheetList ? `: ${sheetList}${moreCount ? ` +${moreCount}` : ""}` : "."}`
          : `Read ${readCount}/${sheetNames.length} sheets. Found data in ${dataCount} sheets${sheetList ? `: ${sheetList}${moreCount ? ` +${moreCount}` : ""}` : "."}`
      );
    } finally {
      setIsReadingAllSheets(false);
    }
  }, [fetchSheetAnalysis, isReadingAllSheets, locale, sheetNames]);

  // Trigger fetch when active sheet changes
  useEffect(() => {
    if (activeSheetName && !analysisBySheet[activeSheetName]) {
      fetchSheetAnalysis(activeSheetName);
    }
  }, [activeSheetName, analysisBySheet, fetchSheetAnalysis]);

  const currentAnalysis: SheetAnalysisData | undefined = analysisBySheet[activeSheetName];

  // Active sheet index for VisualWorkbook
  const activeVisualSheetIndex = useMemo(() => {
    if (!visualWorkbook?.sheets) return 0;
    const idx = visualWorkbook.sheets.findIndex((s) => s.name === activeSheetName);
    return idx >= 0 ? idx : 0;
  }, [visualWorkbook, activeSheetName]);

  // Filtered columns in Stats tab
  const filteredColumns = useMemo(() => {
    if (!currentAnalysis?.columns) return [];
    return currentAnalysis.columns.filter((c) => {
      const colName = String(c?.name || "").toLowerCase();
      const matchSearch = colName.includes(columnSearch.toLowerCase());
      const matchType = selectedColType === "all" || c.type === selectedColType;
      return matchSearch && matchType;
    });
  }, [currentAnalysis, columnSearch, selectedColType]);

  // Data Quality Score (0-100)
  const qualityScore = useMemo(() => {
    if (!currentAnalysis?.overview) return 100;
    let score = 100;
    const emptyPct = currentAnalysis.overview.empty_pct || 0;
    const dupPct = currentAnalysis.overview.duplicate_pct || 0;
    const issues = currentAnalysis.data_quality_issues || [];

    score -= Math.min(emptyPct * 0.8, 30);
    score -= Math.min(dupPct * 1.2, 25);
    score -= issues.filter((i) => i.severity === "high").length * 10;
    score -= issues.filter((i) => i.severity === "medium").length * 5;
    return Math.max(Math.round(score), 10);
  }, [currentAnalysis]);

  return (
    <WorkbookLedger file={file} fileId={fileId} dataSourceUrl={dataSourceUrl} locale={locale} onRestore={(layers) => {
      const restored: Record<string, AnalysisLayer[]> = {};
      for (const layer of layers) {
        (restored[layer.sheet] ||= []).push({ id: layer.id, sheet: layer.sheet, cells: layer.cells, color: layer.color, colorName: layer.color, borderColor: layer.color, prompt: layer.label || "Saved action", visible: true, createdAt: new Date() });
      }
      setAnalysisLayersBySheet((previous) => {
        // Keep older local-only layers; normalize newly saved matching layers to ledger IDs.
        for (const [sheet, entries] of Object.entries(previous)) {
          const saved = restored[sheet] || [];
          const legacy = entries.filter((layer) => layer.id.startsWith("layer_") && !saved.some((item) => item.color === layer.color && JSON.stringify(item.cells) === JSON.stringify(layer.cells)));
          if (legacy.length) restored[sheet] = [...legacy, ...saved];
        }
        return restored;
      });
    }}>
    <div className="flex flex-col rounded-xl border border-slate-200 bg-white shadow-xs font-sans overflow-hidden">
      {dataSourceUrl?.includes("docs.google.com/spreadsheets") && <div className="px-4"><GoogleDataConnection /></div>}
      {/* 1. Header Workspace (2 Tầng rõ ràng theo phong cách SaaS tối giản) */}
      <div className="border-b border-slate-200 bg-white px-4 py-3 shrink-0 space-y-2.5">
        {/* Tầng 1: Tên file & Workspace Badge */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            {onBackToSetup && (
              <button
                type="button"
                onClick={onBackToSetup}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-xs font-semibold text-slate-600 shadow-2xs hover:bg-slate-50 hover:text-slate-900 transition shrink-0"
                title={locale === "vi" ? "Quay lại bước cấu hình dữ liệu" : "Back to setup"}
              >
                <span>←</span>
              </button>
            )}
            <div className="min-w-0">
              <h2 className="font-semibold text-slate-900 text-sm truncate" title={fileName}>
                {fileName}
              </h2>
              <p className="text-xs text-slate-500 mt-0.5 truncate">
                {sheetNames.length} {locale === "vi" ? "trang tính" : "sheets"} • {locale === "vi" ? "Sheet hiện tại:" : "Active:"}{" "}
                <span className="font-semibold text-slate-700">{activeSheetName}</span>
              </p>
            </div>
          </div>

          <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-800 shrink-0">
            Workspace Phân tích dữ liệu
          </span>
        </div>

        {/* Tầng 2: Controls & Actions */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-slate-100">
          {/* Left: Sheet selector, Thống kê, Phân tích lại */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <select
                value={activeSheetName}
                onChange={(e) => handleSelectSheet(e.target.value)}
                className="h-8 appearance-none rounded-lg border border-slate-200 bg-white pl-2.5 pr-7 text-xs font-medium text-slate-700 shadow-2xs hover:border-slate-300 focus:border-emerald-500 focus:outline-none"
              >
                {sheetNames.map((name: string) => (
                  <option key={name} value={name}>
                    Sheet: {name}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-3 w-3 text-slate-400" />
            </div>

            {/* Toggle Thống kê Button (Secondary) */}
            <button
              type="button"
              onClick={() => setIsAnalysisPanelOpen((prev) => !prev)}
              className={`inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium transition shadow-2xs ${
                isAnalysisPanelOpen
                  ? "border-slate-300 bg-slate-100 text-slate-900"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50 hover:text-slate-900"
              }`}
              title={
                isAnalysisPanelOpen
                  ? (locale === "vi" ? "Đóng bảng thống kê (Ctrl+Shift+I)" : "Close statistics panel (Ctrl+Shift+I)")
                  : (locale === "vi" ? "Mở bảng thống kê (Ctrl+Shift+I)" : "Open statistics panel (Ctrl+Shift+I)")
              }
            >
              <TrendingUp className={`h-3.5 w-3.5 ${isAnalysisPanelOpen ? "text-slate-500" : "text-emerald-600"}`} />
              <span>
                {isAnalysisPanelOpen
                  ? (locale === "vi" ? "Đóng thống kê" : "Close Stats")
                  : (locale === "vi" ? "Thống kê" : "Statistics")}
              </span>
            </button>

            {/* Phân tích lại Button (Secondary) */}
            <button
              type="button"
              onClick={() => fetchSheetAnalysis(activeSheetName, true)}
              disabled={isLoadingAnalysis || isReadingAllSheets}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-700 shadow-2xs hover:bg-slate-50 hover:text-slate-900 disabled:opacity-50 transition"
              title={locale === "vi" ? "Phân tích lại sheet hiện tại" : "Re-analyze active sheet"}
            >
              <RefreshCw className={`h-3.5 w-3.5 text-slate-500 ${isLoadingAnalysis ? "animate-spin text-emerald-600" : ""}`} />
              <span className="hidden sm:inline">{locale === "vi" ? "Phân tích lại" : "Re-analyze"}</span>
            </button>
          </div>

          {/* Right: Tải Excel (Secondary) & Sinh báo cáo (Primary CTA) */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Tải Excel (Secondary) */}
            <button
              type="button"
              onClick={handleExportHighlightedExcel}
              disabled={isExportingExcel}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 shadow-2xs hover:bg-slate-50 hover:text-slate-900 disabled:opacity-50 transition"
              title={locale === "vi" ? "Tải xuống file Excel (.xlsx) đã được bôi màu các ô kết quả" : "Download Excel with highlighted cells"}
            >
              <Download className={`h-3.5 w-3.5 text-slate-500 ${isExportingExcel ? "animate-bounce" : ""}`} />
              <span>{isExportingExcel ? (locale === "vi" ? "Đang xuất..." : "Exporting...") : (locale === "vi" ? "Tải Excel" : "Export Excel")}</span>
            </button>

            {/* Sinh báo cáo (Primary CTA) */}
            {onGenerateDocx && (
              <button
                type="button"
                onClick={() => onGenerateDocx(lastAnalysisResult || undefined)}
                disabled={isGeneratingDocx}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 text-xs font-semibold text-white shadow-xs hover:bg-emerald-700 active:scale-[0.98] disabled:opacity-50 transition"
              >
                <FileText className="h-3.5 w-3.5" />
                <span>{isGeneratingDocx ? (locale === "vi" ? "Đang tạo DOCX..." : "Generating...") : (locale === "vi" ? "Sinh báo cáo" : "Generate Report")}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 2. Main Body Split Layout (Spreadsheet ~65% | Analysis Panel ~35%) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-0 min-h-0 h-[clamp(650px,84vh,900px)] overflow-hidden">
        {/* Left: Spreadsheet Preview Viewport (100% width when AI panel hidden) */}
        <div
          className={`${
            !isAnalysisPanelOpen
              ? "lg:col-span-12 xl:col-span-12"
              : "lg:col-span-8 xl:col-span-8 border-r border-slate-200"
          } bg-white p-3 flex flex-col h-full min-h-0 min-w-0 overflow-hidden transition-all duration-200`}
        >
          {/* Top Bar above Spreadsheet: Sheet name, counts, search, highlights */}
          <div className="flex shrink-0 items-center justify-between pb-2.5 mb-2 border-b border-slate-200">
            <div className="flex items-center gap-2 min-w-0">
              <div className="flex h-6 w-6 items-center justify-center rounded-md bg-emerald-100 text-emerald-800 shrink-0">
                <TableIcon className="h-3.5 w-3.5" />
              </div>
              <span className="text-xs font-bold text-slate-900 truncate">
                {activeSheetName}
              </span>
              <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600 shrink-0">
                {currentAnalysis?.overview?.total_rows?.toLocaleString() ?? 0} {locale === "vi" ? "dòng" : "rows"} × {currentAnalysis?.overview?.total_columns ?? 0} {locale === "vi" ? "cột" : "cols"}
              </span>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {selectedRange && (
                <span className="rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-800 ring-1 ring-emerald-200">
                  {selectedRange}
                </span>
              )}

              {/* Layers / Highlights count with clear button */}
              {(analysisLayersBySheet[activeSheetName] || []).length > 0 && (
                <button
                  type="button"
                  onClick={() => handleClearAllLayers(activeSheetName)}
                  className="inline-flex items-center gap-1 rounded-md bg-rose-50 px-2 py-0.5 text-[10px] font-bold text-rose-800 hover:bg-rose-100 ring-1 ring-rose-200 transition"
                  title={locale === "vi" ? "Xóa toàn bộ các lớp màu đánh dấu trên sheet này" : "Clear all color layers"}
                >
                  <Trash2 className="h-3 w-3 text-rose-600" />
                  <span>
                    {(analysisLayersBySheet[activeSheetName] || []).length} {locale === "vi" ? "lớp màu (Xóa hết)" : "layers (Clear)"}
                  </span>
                </button>
              )}
            </div>
          </div>

          {/* Multi-Query Color Legend & Layers Bar */}
          {(analysisLayersBySheet[activeSheetName] || []).length > 0 && (
            <div className="mb-2 shrink-0 rounded-xl border border-slate-200 bg-gradient-to-r from-slate-50 via-white to-slate-50 p-2 shadow-2xs space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <Palette className="h-3.5 w-3.5 text-emerald-600" />
                  <span className="text-[11px] font-bold text-slate-900">
                    {locale === "vi" ? "Chú thích màu theo câu hỏi:" : "Query Color Legend:"}
                  </span>
                </div>
                <span className="text-[10px] text-slate-400">
                  {locale === "vi" ? "Rê chuột vào ô để xem câu hỏi gốc" : "Hover cell to view query"}
                </span>
              </div>

              {/* Layer Badges */}
              <div className="flex flex-wrap gap-1.5">
                {(analysisLayersBySheet[activeSheetName] || []).map((layer) => (
                  <div
                    key={layer.id}
                    style={{
                      backgroundColor: layer.visible ? layer.color : "#F1F5F9",
                      borderColor: layer.borderColor,
                    }}
                    className={`inline-flex items-center gap-1.5 rounded-lg border px-2 py-0.5 text-xs transition-all shadow-2xs ${
                      layer.visible ? "opacity-100" : "opacity-50 line-through"
                    }`}
                  >
                    <span
                      style={{ backgroundColor: layer.borderColor }}
                      className="h-2 w-2 rounded-full shrink-0"
                    />
                    <span className="font-bold text-slate-900 truncate max-w-[180px]" title={layer.prompt}>
                      {layer.prompt}
                    </span>
                    <span className="rounded bg-white/80 px-1 font-mono text-[10px] font-bold text-slate-800">
                      {layer.cells.length} ô
                    </span>

                    {/* Focus first cell */}
                    {layer.cells[0] && (
                      <button
                        type="button"
                        onClick={() => handleScrollToCell(layer.cells[0])}
                        className="rounded bg-white/90 hover:bg-white px-1 font-mono text-[9px] font-bold text-slate-800 shadow-2xs transition"
                        title={`Cuộn đến ô ${layer.cells[0]}`}
                      >
                        🎯 {layer.cells[0]}
                      </button>
                    )}

                    {/* Toggle show/hide */}
                    <button
                      type="button"
                      onClick={() => handleToggleLayerVisibility(activeSheetName, layer.id)}
                      className="text-slate-600 hover:text-slate-900 transition p-0.5"
                      title={layer.visible ? "Ẩn màu câu hỏi này" : "Hiện màu câu hỏi này"}
                    >
                      {layer.visible ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
                    </button>

                    {/* Remove layer */}
                    <button
                      type="button"
                      onClick={() => handleRemoveLayer(activeSheetName, layer.id)}
                      className="text-slate-400 hover:text-rose-600 transition p-0.5"
                      title="Xóa màu câu hỏi này"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Analysis Findings Banner directly above Spreadsheet (Insight banner nhỏ ~56-72px) */}
          {lastAnalysisResult && <div className="space-y-2 px-4 py-2">
            {(lastAnalysisResult.pending_actions || []).map((action: any, index: number) => {
              const sheet = action.sheet || activeSheetName;
              const columns = visualWorkbook?.sheets.find((item) => item.name === sheet)?.max_column || 0;
              const rows: number[] = action.rows || [];
              const supported = ["HIGHLIGHT_CELLS", "HIGHLIGHT_ROWS", "CLEAR_HIGHLIGHTS"].includes(action.type);
              const bounded = rows.length * columns <= 50000;
              const cells: string[] = action.type === "HIGHLIGHT_ROWS" && columns && bounded
                ? rows.flatMap((row) => Array.from({ length: columns }, (_, column) => {
                    let n = column + 1; let letter = "";
                    while (n > 0) { n--; letter = String.fromCharCode(65 + n % 26) + letter; n = Math.floor(n / 26); }
                    return `${letter}${row}`;
                  })) : action.cells || [];
              const clear = action.type === "CLEAR_HIGHLIGHTS";
              const unavailable = !supported || !bounded || (action.type === "HIGHLIGHT_ROWS" && !columns) || (!clear && !cells.length)
                ? (locale === "vi" ? "Chưa xác định được phạm vi an toàn để áp dụng." : "A safe target is unavailable.") : undefined;
              return <SpreadsheetActionCard key={action.id || `${sheet}-${index}`} label={action.label || action.type} sheet={sheet} cells={cells} rows={rows} color={action.color || activeHighlightColor} clear={clear} locale={locale} unavailable={unavailable} onConfirm={() => {
                if (clear) handleClearHighlights(sheet);
                else handleHighlightCells(sheet, cells, action.color || activeHighlightColor, lastAnalysisResult.prompt || action.label || "AI Analysis");
                setLastAnalysisResultBySheet((previous) => Object.fromEntries(Object.entries(previous).map(([key, value]) => [key, value === lastAnalysisResult ? { ...value, pending_actions: value.pending_actions.filter((item: any) => item !== action) } : value])));
              }} />;
            })}
          </div>}
          {lastAnalysisResult && (
            <div className="mb-2 shrink-0 rounded-xl border border-amber-200/80 bg-amber-50/40 px-3 py-2 shadow-2xs">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 min-h-[44px]">
                <div className="flex items-start gap-2.5 min-w-0">
                  <Sparkles className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-xs font-semibold text-amber-950">
                        ✨ {lastAnalysisResult.title || (locale === "vi" ? `Tổng quan ${activeSheetName}` : "Analysis Findings")}
                      </span>
                      {lastAnalysisResult.result?.duplicate_count !== undefined && (
                        <span className="rounded bg-amber-100/90 px-1.5 py-0.2 text-[10px] font-semibold text-amber-800">
                          {lastAnalysisResult.result.duplicate_count} {locale === "vi" ? "nhóm trùng" : "duplicates"}
                        </span>
                      )}
                      {lastAnalysisResult.result?.missing_count !== undefined && (
                        <span className="rounded bg-orange-100/90 px-1.5 py-0.2 text-[10px] font-semibold text-orange-800">
                          {lastAnalysisResult.result.missing_count} {locale === "vi" ? "ô thiếu" : "missing"}
                        </span>
                      )}
                      {/* Evidence Source Chip */}
                      {lastAnalysisResult.evidence?.sheet && (
                        <span className="text-[11px] text-slate-500 font-normal">
                          · 📍 {locale === "vi" ? "Nguồn:" : "Source:"} {lastAnalysisResult.evidence.sheet}
                          {lastAnalysisResult.evidence.ranges?.length ? ` · ${lastAnalysisResult.evidence.ranges.join(", ")}` : ""}
                        </span>
                      )}
                      {/* Google Sheets Sync Status Chip */}
                      {lastAnalysisResult.google_sync?.is_google_sheet && (
                        lastAnalysisResult.google_sync.synced_to_google_sheets && lastAnalysisResult.google_sync.verified_on_google_sheets ? (
                          <span className="inline-flex items-center gap-1 rounded bg-emerald-100/80 px-1.5 py-0.2 text-[10px] font-semibold text-emerald-800">
                            <Check className="h-3 w-3 text-emerald-700" />
                            {locale === "vi" ? "Đã đồng bộ Sheets" : "Synced to Sheets"}
                          </span>
                        ) : (
                          <div className="inline-flex items-center gap-1">
                            <span className="text-[10px] text-amber-800">
                              ⚠️ {locale === "vi" ? "Chưa đồng bộ Sheets" : "Sync pending"}
                            </span>
                            <button
                              type="button"
                              onClick={() => handleRetryGoogleSync(lastAnalysisResult)}
                              disabled={isRetryingGoogleSync}
                              className="rounded bg-blue-600 text-white px-1.5 py-0.2 text-[10px] font-semibold hover:bg-blue-700 transition"
                            >
                              {isRetryingGoogleSync ? "..." : "🔄"}
                            </button>
                          </div>
                        )
                      )}
                    </div>
                    <p className="text-xs text-amber-900 line-clamp-1 font-normal mt-0.5" title={lastAnalysisResult.answer}>
                      {renderInlineMarkdown(lastAnalysisResult.answer)}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">
                  {/* Quick Cell Jump / Focus Buttons */}
                  {Array.isArray(lastAnalysisResult.result?.matched_cells) && lastAnalysisResult.result.matched_cells.length > 0 && (
                    <div className="flex items-center gap-1">
                      <span className="text-[10px] text-amber-800 font-semibold">Focus:</span>
                      {lastAnalysisResult.result.matched_cells.slice(0, 4).map((mc: any, idx: number) => {
                        const addr = getMatchedCellAddress(mc);
                        return (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => handleScrollToCell(addr)}
                            className="rounded bg-white border border-amber-200 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-amber-900 hover:bg-amber-100/60 transition shadow-2xs"
                            title={locale === "vi" ? `Cuộn đến ô ${addr}` : `Scroll to ${addr}`}
                          >
                            {addr}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* Insert into DOCX Report Button */}
                  <button
                    type="button"
                    onClick={handlePushFindingToDocx}
                    disabled={isInsertingDocx}
                    className="inline-flex h-7 items-center gap-1 rounded-lg bg-emerald-600 px-2.5 text-xs font-semibold text-white hover:bg-emerald-700 transition shadow-2xs active:scale-95 disabled:opacity-50"
                    title={locale === "vi" ? "Chèn bảng phân tích và nhận xét này vào báo cáo Word DOCX" : "Insert this analysis finding into DOCX report"}
                  >
                    <FileText className="h-3 w-3" />
                    <span>{isInsertingDocx ? (locale === "vi" ? "Đang chèn..." : "Inserting...") : (locale === "vi" ? "Chèn vào báo cáo" : "Push to Word")}</span>
                  </button>



                  {/* Dismiss Banner Button */}
                  <button
                    type="button"
                    onClick={() => {
                      setLastAnalysisResultBySheet((prev) => {
                        const next = { ...prev };
                        delete next[activeSheetName];
                        delete next["workbook"];
                        return next;
                      });
                    }}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 hover:bg-amber-100/70 hover:text-slate-700 transition active:scale-95 cursor-pointer"
                    title={locale === "vi" ? "Đóng thông báo này" : "Dismiss finding"}
                    aria-label={locale === "vi" ? "Đóng thông báo này" : "Dismiss finding"}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Center: Full-height Spreadsheet Grid */}
          <div className="flex-1 min-h-0 min-w-0 h-full overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
            <SpreadsheetPreview
              workbook={
                visualWorkbook
                  ? {
                      ...visualWorkbook,
                      active_sheet_index: activeVisualSheetIndex,
                      sheets: visualWorkbook.sheets,
                    }
                  : null
              }
              legacyData={legacyData}
              height="100%"
              locale={locale}
              activeSheetName={activeSheetName}
              onActiveSheetChange={handleSelectSheet}
              cellHighlights={cellHighlightsForActiveSheet}
              selectedRange={selectedRange}
              onRangeSelect={setSelectedRange}
              scrollToCellAddress={scrollToCellAddress}
              allSheetsActive={chatScopeMode === "workbook"}

            />
          </div>

          {/* Bottom: Docked AI Prompt & Quick Action Bar */}
          <div className="mt-2.5 shrink-0 rounded-xl border border-emerald-200 bg-gradient-to-r from-emerald-50/90 via-teal-50/50 to-emerald-50/80 p-2.5 shadow-2xs space-y-2">
            <fieldset className="min-w-0 space-y-2">
              <legend className="text-xs font-semibold text-slate-700">{locale === "vi" ? "Bảng cần phân tích" : "Sheets to analyze"}</legend>
              <div className="flex max-h-28 flex-wrap items-center gap-2 overflow-y-auto">
                <button type="button" onClick={() => setSelectedAnalysisSheets([...sheetNames])} className="rounded-md border border-emerald-300 bg-white px-2 py-1 text-xs font-medium text-emerald-800 hover:bg-emerald-50 focus-visible:ring-2 focus-visible:ring-emerald-500">{locale === "vi" ? "Chọn tất cả" : "Select all"}</button>
                {sheetNames.map((name) => <label key={name} className="flex max-w-full cursor-pointer items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700">
                  <input type="checkbox" checked={selectedAnalysisSheets.includes(name)} onChange={(event) => setSelectedAnalysisSheets((current) => event.target.checked ? [...current, name] : current.filter((sheet) => sheet !== name))} className="h-4 w-4 accent-emerald-600" />
                  <span className="truncate">{name}</span>
                </label>)}
              </div>
              <p className="text-[11px] text-slate-600">{analysisScope ? (locale === "vi" ? `Đã chọn ${selectedAnalysisSheets.length}/${sheetNames.length} bảng. Yêu cầu phân tích và chat AI dùng các bảng này.` : `${selectedAnalysisSheets.length}/${sheetNames.length} sheets selected for analysis and AI chat.`) : (locale === "vi" ? "Chọn ít nhất một bảng để phân tích." : "Select at least one sheet to analyze.")}</p>
            </fieldset>
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-600 text-white shrink-0 shadow-2xs">
                <Sparkles className="h-4 w-4" />
              </div>
              <input
                type="text"
                value={analysisPrompt}
                onChange={(e) => setAnalysisPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    if (analysisPrompt.trim() && !isRunningAnalysisAction) {
                      handleRunAnalysisAction();
                    }
                  }
                }}
                placeholder={
                  locale === "vi"
                    ? "Nhập yêu cầu phân tích (VD: Tìm xe trùng biển số, tìm ô trống, lọc theo trạm)..."
                    : "Enter analysis prompt (e.g., find duplicate license plates, blank cells)..."
                }
                className="flex-1 bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-900 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 placeholder:text-slate-400 transition"
              />
              <button
                type="button"
                onClick={() => handleRunAnalysisAction()}
                disabled={isRunningAnalysisAction || !analysisPrompt.trim() || !analysisScope}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 active:scale-95 disabled:opacity-50 transition shrink-0"
              >
                {isRunningAnalysisAction ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
                <span>{locale === "vi" ? "Phân tích" : "Analyze"}</span>
              </button>
            </div>

            {/* Quick Action Prompt Chips & Highlight Color Palette */}
            <div className="flex items-center justify-between gap-2 flex-wrap pt-0.5">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                  {locale === "vi" ? "Gợi ý nhanh:" : "Quick Actions:"}
                </span>
                {[
                  { label: locale === "vi" ? "👑 Giá trị cao nhất" : "👑 Max Value", prompt: "Tìm dòng có giá trị cao nhất" },
                  { label: locale === "vi" ? "💰 Tổng số liệu" : "💰 Total Sum", prompt: "Tính tổng số liệu" },
                  { label: locale === "vi" ? "🔍 Tìm dữ liệu trùng" : "🔍 Find Duplicates", prompt: "Tìm toàn bộ dữ liệu trùng lặp" },
                  { label: locale === "vi" ? "⚠️ Tìm ô trống / thiếu" : "⚠️ Find Missing", prompt: "Tìm các ô trống hoặc thiếu dữ liệu" },
                  { label: locale === "vi" ? "📊 Phân tích bất thường" : "📊 Outliers", prompt: "Phân tích các giá trị bất thường" },
                  { label: locale === "vi" ? "📐 Viết công thức Excel" : "📐 Formula", prompt: "Viết công thức Excel cho sheet này" },
                  { label: locale === "vi" ? "📝 Tóm tắt sheet" : "📝 Summarize Sheet", prompt: "Tóm tắt dữ liệu sheet này" },
                ].map((chip, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => {
                      setAnalysisPrompt(chip.prompt);
                      handleRunAnalysisAction(chip.prompt);
                    }}
                    disabled={isRunningAnalysisAction}
                    className="rounded-md bg-white border border-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-700 hover:bg-emerald-50 hover:border-emerald-300 hover:text-emerald-800 active:scale-95 transition shadow-2xs"
                  >
                    {chip.label}
                  </button>
                ))}
              </div>

              {/* Color Picker for Highlighting */}
              <div className="flex items-center gap-1 shrink-0 bg-white/90 rounded-md px-2 py-0.5 border border-slate-200 shadow-2xs">
                <span className="text-[10px] font-bold text-slate-500">
                  {locale === "vi" ? "Màu bôi:" : "Color:"}
                </span>
                {[
                  { color: "#FEF08A", title: "Vàng sáng (Mặc định)" },
                  { color: "#FED7AA", title: "Cam san hô (Dùng khi ô đã có màu vàng)" },
                  { color: "#E9D5FF", title: "Tím thạch anh" },
                  { color: "#BAE6FD", title: "Xanh ngọc" },
                  { color: "#FECDD3", title: "Đỏ hồng" },
                ].map((c) => (
                  <button
                    key={c.color}
                    type="button"
                    onClick={() => setActiveHighlightColor(c.color)}
                    style={{ backgroundColor: c.color }}
                    className={`h-4 w-4 rounded-full border transition-transform ${
                      activeHighlightColor === c.color ? "ring-2 ring-emerald-600 scale-110 border-slate-700" : "border-slate-300 hover:scale-105"
                    }`}
                    title={c.title}
                  />
                ))}
              </div>
            </div>

            {analysisActionStatus && (
              <div className="pt-1 border-t border-emerald-100/80 flex items-center justify-between text-[11px]">
                <span className="font-semibold text-emerald-950 truncate">
                  ⚡ {renderInlineMarkdown(analysisActionStatus)}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Right: Interactive Multi-tab Analysis Panel (Preserves DOM state when hidden) */}
        <div
          className={`${
            !isAnalysisPanelOpen
              ? "hidden"
              : "lg:col-span-4 xl:col-span-4"
          } bg-slate-50 flex flex-col h-full min-h-0 min-w-0 p-3.5 transition-all duration-200 overflow-hidden`}
        >
          {/* Analysis Tabs Header */}
          <div className="flex items-center justify-between gap-1.5 pb-2 border-b border-slate-200 shrink-0">
            <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar">
              <button
                type="button"
                onClick={() => setActiveTab("overview")}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-bold transition-colors shrink-0 whitespace-nowrap ${
                  activeTab === "overview"
                    ? "bg-emerald-600 text-white shadow-sm"
                    : "bg-white text-slate-600 hover:bg-slate-100 ring-1 ring-slate-200"
                }`}
              >
                <Layers className="h-3.5 w-3.5" />
                <span>{locale === "vi" ? "Tổng quan" : "Overview"}</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("stats")}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-bold transition-colors shrink-0 whitespace-nowrap ${
                  activeTab === "stats"
                    ? "bg-emerald-600 text-white shadow-sm"
                    : "bg-white text-slate-600 hover:bg-slate-100 ring-1 ring-slate-200"
                }`}
              >
                <TrendingUp className="h-3.5 w-3.5" />
                <span>{locale === "vi" ? "Thống kê" : "Statistics"}</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("charts")}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-bold transition-colors shrink-0 whitespace-nowrap ${
                  activeTab === "charts"
                    ? "bg-emerald-600 text-white shadow-sm"
                    : "bg-white text-slate-600 hover:bg-slate-100 ring-1 ring-slate-200"
                }`}
              >
                <BarChart3 className="h-3.5 w-3.5" />
                <span>{locale === "vi" ? "Biểu đồ" : "Charts"}</span>
                {currentAnalysis?.charts?.length ? (
                  <span className="rounded-full bg-emerald-100 px-1 text-[10px] text-emerald-800">
                    {currentAnalysis.charts.length}
                  </span>
                ) : null}
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("quality")}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-bold transition-colors shrink-0 whitespace-nowrap ${
                  activeTab === "quality"
                    ? "bg-emerald-600 text-white shadow-sm"
                    : "bg-white text-slate-600 hover:bg-slate-100 ring-1 ring-slate-200"
                }`}
              >
                <ShieldCheck className="h-3.5 w-3.5" />
                <span>{locale === "vi" ? "Chất lượng" : "Quality"}</span>
                {currentAnalysis?.data_quality_issues?.length ? (
                  <span
                    className={`rounded-full px-1 text-[10px] ${
                      qualityScore >= 80 ? "bg-amber-100 text-amber-800" : "bg-rose-100 text-rose-800 font-bold"
                    }`}
                  >
                    {currentAnalysis.data_quality_issues.length}
                  </span>
                ) : null}
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("ai")}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-bold transition-colors shrink-0 whitespace-nowrap ${
                  activeTab === "ai"
                    ? "bg-emerald-600 text-white shadow-sm"
                    : "bg-white text-slate-600 hover:bg-slate-100 ring-1 ring-slate-200"
                }`}
              >
                <Zap className="h-3.5 w-3.5" />
                <span>{locale === "vi" ? "Đề xuất AI" : "AI Recommendations"}</span>
              </button>
            </div>

            {/* Quick Hide Panel Button */}
            <button
              type="button"
              onClick={() => setIsAnalysisPanelOpen(false)}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition shrink-0 ml-1"
              title={locale === "vi" ? "Ẩn bảng phân tích AI (Ctrl+Shift+I)" : "Hide AI panel (Ctrl+Shift+I)"}
            >
              <PanelRightClose className="h-4 w-4" />
            </button>
          </div>

          {/* Analysis Tab Contents */}
          <div className="flex-1 min-h-0 min-w-0 overflow-y-auto pt-3 pr-1">
            {isLoadingAnalysis && !currentAnalysis ? (
              <div className="flex h-64 flex-col items-center justify-center gap-3 text-slate-500">
                <RefreshCw className="h-7 w-7 animate-spin text-emerald-600" />
                <p className="text-xs font-bold text-slate-700">
                  {locale === "vi" ? `Đang phân tích sheet "${activeSheetName}"...` : `Analyzing sheet "${activeSheetName}"...`}
                </p>
                <p className="text-[11px] text-slate-400">
                  {locale === "vi" ? "Tính toán thống kê 100% dòng & sinh đề xuất AI..." : "Computing full statistics and generating AI insights..."}
                </p>
              </div>
            ) : currentAnalysis ? (
              <>
                {/* TAB 1: TỔNG QUAN (OVERVIEW) */}
                {activeTab === "overview" && (
                  <div className="space-y-3.5">
                    {/* Direct Analysis Result Banner */}
                    {lastAnalysisResult && (
                      <div className="rounded-xl border border-emerald-300 bg-gradient-to-br from-emerald-50/90 via-white to-teal-50/40 p-3.5 shadow-xs space-y-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <Sparkles className="h-4 w-4 text-emerald-600 shrink-0" />
                            <h4 className="font-bold text-xs text-emerald-950">
                              {locale === "vi" ? "Kết quả phân tích trực tiếp" : "Direct Analysis Result"}
                            </h4>
                          </div>
                          {lastAnalysisResult.context?.sheet && (
                            <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800 shrink-0">
                              {lastAnalysisResult.context.sheet === "workbook"
                                ? (locale === "vi" ? "Toàn bộ workbook" : "Entire workbook")
                                : `Sheet: ${lastAnalysisResult.context.sheet}`}
                            </span>
                          )}
                        </div>

                        {lastAnalysisResult.analysis_history_item?.prompt && (
                          <div className="text-[11px] text-slate-600 font-medium">
                            <span className="text-slate-400 font-semibold">{locale === "vi" ? "Yêu cầu: " : "Prompt: "}</span>
                            {lastAnalysisResult.analysis_history_item.prompt}
                          </div>
                        )}

                        <p className="text-xs font-semibold text-slate-800 whitespace-pre-wrap leading-relaxed">
                          {lastAnalysisResult.answer || (locale === "vi" ? "Đã hoàn thành phân tích." : "Analysis complete.")}
                        </p>

                        {/* Metric badges */}
                        <div className="flex flex-wrap gap-1.5 pt-0.5">
                          {lastAnalysisResult.result?.duplicate_count !== undefined && (
                            <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 border border-amber-200 px-2 py-0.5 text-[10px] font-bold text-amber-800">
                              🔍 {lastAnalysisResult.result.duplicate_count} {locale === "vi" ? "nhóm trùng" : "duplicates"}
                            </span>
                          )}
                          {lastAnalysisResult.result?.missing_count !== undefined && (
                            <span className="inline-flex items-center gap-1 rounded-md bg-orange-50 border border-orange-200 px-2 py-0.5 text-[10px] font-bold text-orange-800">
                              ⚠️ {lastAnalysisResult.result.missing_count} {locale === "vi" ? "ô thiếu/trống" : "missing cells"}
                            </span>
                          )}
                          {Array.isArray(lastAnalysisResult.result?.outliers) && (
                            <span className="inline-flex items-center gap-1 rounded-md bg-rose-50 border border-rose-200 px-2 py-0.5 text-[10px] font-bold text-rose-800">
                              📊 {lastAnalysisResult.result.outliers.length} {locale === "vi" ? "bất thường" : "anomalies"}
                            </span>
                          )}
                        </div>

                        {/* Detailed Findings Table with Focus Buttons */}
                        {Array.isArray(lastAnalysisResult.result?.matched_cells) && lastAnalysisResult.result.matched_cells.length > 0 && (
                          <div className="rounded-xl border border-amber-300 bg-white p-3 shadow-2xs space-y-2">
                            <div className="flex items-center justify-between">
                              <h5 className="font-bold text-xs text-amber-950 flex items-center gap-1.5">
                                <Sparkles className="h-3.5 w-3.5 text-amber-600" />
                                <span>{locale === "vi" ? `Chi tiết các ô phát hiện (${lastAnalysisResult.result.matched_cells.length})` : `Detected Cells (${lastAnalysisResult.result.matched_cells.length})`}</span>
                              </h5>
                              <span className="text-[10px] text-slate-400">{locale === "vi" ? "Click Focus để cuộn bảng tính" : "Click Focus to jump"}</span>
                            </div>

                            <div className="max-h-52 overflow-y-auto rounded-lg border border-slate-200">
                              <table className="w-full text-left text-xs border-collapse">
                                <thead className="bg-slate-100 text-slate-600 sticky top-0 text-[10px] font-bold uppercase">
                                  <tr>
                                    <th className="p-1.5">{locale === "vi" ? "Địa chỉ" : "Cell"}</th>
                                    <th className="p-1.5">{locale === "vi" ? "Giá trị" : "Value"}</th>
                                    <th className="p-1.5">{locale === "vi" ? "Lý do" : "Reason"}</th>
                                    <th className="p-1.5 text-right">{locale === "vi" ? "Thao tác" : "Action"}</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 text-[11px]">
                                  {lastAnalysisResult.result.matched_cells.map((cell: any, cIdx: number) => {
                                    const addr = getMatchedCellAddress(cell);
                                    const val = typeof cell === "object" ? (cell.display_value || cell.value || "(trống)") : "";
                                    const reason = typeof cell === "object" ? (cell.reason || "Trùng lặp") : "Trùng lặp";
                                    return (
                                      <tr key={cIdx} className="hover:bg-amber-50/60 transition">
                                        <td className="p-1.5 font-mono font-bold text-amber-900">{addr}</td>
                                        <td className="p-1.5 font-semibold text-slate-800 truncate max-w-[110px]" title={String(val)}>{val}</td>
                                        <td className="p-1.5 text-slate-500 truncate max-w-[90px]">{reason}</td>
                                        <td className="p-1.5 text-right">
                                          <button
                                            type="button"
                                            onClick={() => handleScrollToCell(addr)}
                                            className="rounded bg-amber-100 hover:bg-amber-200 text-amber-900 font-bold px-2 py-0.5 text-[10px] transition"
                                          >
                                            Focus 🎯
                                          </button>
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    {/* KPI Stat Cards */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                      <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-2xs">
                        <span className="text-[11px] font-medium text-slate-500">{locale === "vi" ? "Tổng số dòng" : "Total Rows"}</span>
                        <div className="mt-1 text-lg font-extrabold text-slate-900">
                          {currentAnalysis.overview.total_rows.toLocaleString()}
                        </div>
                      </div>

                      <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-2xs">
                        <span className="text-[11px] font-medium text-slate-500">{locale === "vi" ? "Số cột" : "Total Columns"}</span>
                        <div className="mt-1 text-lg font-extrabold text-slate-900">
                          {currentAnalysis.overview.total_columns}
                        </div>
                      </div>

                      <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-2xs">
                        <span className="text-[11px] font-medium text-slate-500">{locale === "vi" ? "Ô trống" : "Empty Cells"}</span>
                        <div className="mt-1 text-lg font-extrabold text-slate-900">
                          {currentAnalysis.overview.empty_pct}%
                        </div>
                        <span className="text-[10px] text-slate-400">
                          ({currentAnalysis.overview.empty_cells.toLocaleString()} ô)
                        </span>
                      </div>

                      <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-2xs">
                        <span className="text-[11px] font-medium text-slate-500">{locale === "vi" ? "Trùng lặp" : "Duplicates"}</span>
                        <div className="mt-1 text-lg font-extrabold text-slate-900">
                          {currentAnalysis.overview.duplicate_rows}
                        </div>
                        <span className="text-[10px] text-slate-400">
                          ({currentAnalysis.overview.duplicate_pct}%)
                        </span>
                      </div>

                      <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-2xs">
                        <span className="text-[11px] font-medium text-slate-500">{locale === "vi" ? "Cột số / tiền" : "Numeric/Currency"}</span>
                        <div className="mt-1 text-lg font-extrabold text-emerald-700">
                          {currentAnalysis.overview.numeric_columns_count}
                        </div>
                      </div>

                      <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-2xs">
                        <span className="text-[11px] font-medium text-slate-500">{locale === "vi" ? "Điểm chất lượng" : "Quality Score"}</span>
                        <div className={`mt-1 text-lg font-extrabold ${qualityScore >= 80 ? "text-emerald-700" : "text-amber-700"}`}>
                          {qualityScore} / 100
                        </div>
                      </div>
                    </div>

                    {/* AI Executive Summary Card */}
                    {currentAnalysis.ai_insights?.summary && (
                      <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3.5 shadow-2xs">
                        <div className="flex items-center gap-2 font-bold text-emerald-950 text-xs mb-1.5">
                          <Sparkles className="h-4 w-4 text-emerald-600" />
                          <span>{locale === "vi" ? "Tóm tắt dữ liệu nhanh từ AI" : "AI Quick Summary"}</span>
                        </div>
                        <p className="text-xs leading-relaxed text-slate-700 whitespace-pre-wrap">
                          {currentAnalysis.ai_insights.summary}
                        </p>
                      </div>
                    )}

                    {/* Column Types Breakdown */}
                    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-2xs">
                      <h4 className="font-bold text-xs text-slate-900 mb-2">{locale === "vi" ? "Phân bố kiểu dữ liệu các cột" : "Column Data Types"}</h4>
                      <div className="flex flex-wrap gap-1.5">
                        {currentAnalysis.columns.map((c) => (
                          <span
                            key={c.name}
                            className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-700"
                          >
                            <span className="font-semibold text-slate-900">{c.name}</span>
                            <span className="rounded bg-white px-1 text-[10px] text-slate-500 font-mono ring-1 ring-slate-200">
                              {c.type}
                            </span>
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* TAB 2: THỐNG KÊ CHI TIẾT (STATISTICS) */}
                {activeTab === "stats" && (
                  <div className="space-y-3">
                    {/* Search & Filter Bar */}
                    <div className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
                        <input
                          type="text"
                          placeholder={locale === "vi" ? "Tìm kiếm cột..." : "Search column..."}
                          value={columnSearch}
                          onChange={(e) => setColumnSearch(e.target.value)}
                          className="w-full rounded-lg border border-slate-200 bg-white py-1.5 pl-8 pr-3 text-xs text-slate-800 placeholder-slate-400 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                        />
                      </div>
                      <select
                        value={selectedColType}
                        onChange={(e) => setSelectedColType(e.target.value)}
                        className="rounded-lg border border-slate-200 bg-white py-1.5 px-2 text-xs font-medium text-slate-700"
                      >
                        <option value="all">{locale === "vi" ? "Tất cả kiểu" : "All types"}</option>
                        <option value="currency">{locale === "vi" ? "Tiền tệ (Currency)" : "Currency"}</option>
                        <option value="numeric">{locale === "vi" ? "Số liệu (Numeric)" : "Numeric"}</option>
                        <option value="category">{locale === "vi" ? "Danh mục (Category)" : "Category"}</option>
                        <option value="date">{locale === "vi" ? "Ngày tháng (Date)" : "Date"}</option>
                        <option value="text">{locale === "vi" ? "Văn bản (Text)" : "Text"}</option>
                      </select>
                    </div>

                    {/* Columns List */}
                    <div className="space-y-2.5">
                      {filteredColumns.map((col) => (
                        <div
                          key={col.name}
                          className="rounded-xl border border-slate-200 bg-white p-3 shadow-2xs hover:border-slate-300 transition-colors"
                        >
                          <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2 mb-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="font-bold text-xs text-slate-900 truncate" title={col.name}>
                                {col.name}
                              </span>
                              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-600 uppercase">
                                {col.type}
                              </span>
                            </div>
                            <span className="text-[11px] text-slate-500 font-medium">
                              {col.non_null_count} / {col.total_count} {locale === "vi" ? "ô" : "cells"}
                            </span>
                          </div>

                          {/* Numeric / Currency Stats */}
                          {(col.min !== undefined || col.mean !== undefined) && (
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] mb-2 bg-slate-50 rounded-lg p-2">
                              <div>
                                <span className="text-slate-400">Min:</span>{" "}
                                <span className="font-semibold text-slate-800">{col.min?.toLocaleString()}</span>
                              </div>
                              <div>
                                <span className="text-slate-400">Max:</span>{" "}
                                <span className="font-semibold text-slate-800">{col.max?.toLocaleString()}</span>
                              </div>
                              <div>
                                <span className="text-slate-400">Mean:</span>{" "}
                                <span className="font-semibold text-slate-800">{col.mean?.toLocaleString()}</span>
                              </div>
                              <div>
                                <span className="text-slate-400">Sum:</span>{" "}
                                <span className="font-bold text-emerald-700">{col.sum?.toLocaleString()}</span>
                              </div>
                            </div>
                          )}

                          {/* Top Categories Frequency */}
                          {col.top_values && col.top_values.length > 0 && (
                            <div className="space-y-1.5 mt-2">
                              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                                {locale === "vi" ? "Phân bố giá trị hàng đầu" : "Top Values"}
                              </span>
                              <div className="space-y-1">
                                {col.top_values.map((item, i) => (
                                  <div key={i} className="flex items-center justify-between text-[11px]">
                                    <span className="truncate max-w-[180px] text-slate-700" title={item.value}>
                                      {item.value}
                                    </span>
                                    <div className="flex items-center gap-2 shrink-0">
                                      <div className="w-16 h-2 rounded-full bg-slate-100 overflow-hidden">
                                        <div
                                          className="h-full bg-emerald-500 rounded-full"
                                          style={{ width: `${Math.min(item.pct, 100)}%` }}
                                        />
                                      </div>
                                      <span className="w-10 text-right font-mono text-[10px] text-slate-500 font-semibold">
                                        {item.pct}%
                                      </span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* TAB 3: BIỂU ĐỒ (CHARTS) */}
                {activeTab === "charts" && (
                  <div className="space-y-3.5">
                    {currentAnalysis.charts && currentAnalysis.charts.length > 0 ? (
                      <>
                        {/* Chart Switcher */}
                        <div className="flex gap-1.5 overflow-x-auto pb-1 no-scrollbar">
                          {currentAnalysis.charts.map((chart, idx) => (
                            <button
                              key={chart.id}
                              type="button"
                              onClick={() => setSelectedChartIdx(idx)}
                              className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                                selectedChartIdx === idx
                                  ? "bg-emerald-600 text-white shadow-sm ring-1 ring-emerald-600"
                                  : "bg-white text-slate-600 hover:bg-slate-100 ring-1 ring-slate-200"
                              }`}
                            >
                              {chart.title}
                            </button>
                          ))}
                        </div>

                        {/* Selected Chart Card */}
                        {(() => {
                          const chart = currentAnalysis.charts[selectedChartIdx] || currentAnalysis.charts[0];
                          const maxVal = Math.max(...chart.data.map((d) => d.value || 0), 1);

                          return (
                            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs">
                              <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2 mb-3">
                                <div>
                                  <h4 className="font-bold text-xs text-slate-900">{chart.title}</h4>
                                  {chart.description && (
                                    <p className="text-[11px] text-slate-500 mt-0.5">{chart.description}</p>
                                  )}
                                </div>
                                <span className="rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 uppercase">
                                  {chart.type}
                                </span>
                              </div>

                              {/* Interactive Pure SVG/CSS Chart */}
                              <div className="space-y-2.5 pt-2">
                                {chart.data.map((point, pIdx) => {
                                  const pct = Math.round((point.value / maxVal) * 100);
                                  return (
                                    <div key={pIdx} className="space-y-1">
                                      <div className="flex items-center justify-between text-xs font-medium">
                                        <span className="truncate max-w-[220px] text-slate-800 font-semibold" title={point.label}>
                                          {point.label}
                                        </span>
                                        <span className="font-mono font-bold text-emerald-700">
                                          {point.value.toLocaleString()}
                                        </span>
                                      </div>
                                      <div className="h-3 w-full rounded-full bg-slate-100 overflow-hidden">
                                        <div
                                          className="h-full bg-gradient-to-r from-emerald-500 to-teal-500 rounded-full transition-all duration-500"
                                          style={{ width: `${Math.max(pct, 2)}%` }}
                                        />
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          );
                        })()}
                      </>
                    ) : (
                      <div className="flex h-48 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white p-6 text-slate-400">
                        <BarChart3 className="h-8 w-8 text-slate-300 mb-1" />
                        <p className="text-xs font-medium">{locale === "vi" ? "Chưa có biểu đồ phù hợp cho sheet này." : "No charts available for this sheet."}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* TAB 4: CHẤT LƯỢNG DỮ LIỆU (DATA QUALITY) */}
                {activeTab === "quality" && (
                  <div className="space-y-3">
                    {/* Health Score Overview */}
                    <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3.5 shadow-2xs">
                      <div>
                        <span className="text-[11px] font-medium text-slate-500">{locale === "vi" ? "Độ tin cậy dữ liệu" : "Data Health Score"}</span>
                        <div className="flex items-baseline gap-2 mt-0.5">
                          <span className={`text-2xl font-extrabold ${qualityScore >= 80 ? "text-emerald-600" : "text-amber-600"}`}>
                            {qualityScore}
                          </span>
                          <span className="text-xs text-slate-400 font-semibold">/ 100</span>
                        </div>
                      </div>
                      <span
                        className={`rounded-lg px-2.5 py-1 text-xs font-bold ${
                          qualityScore >= 80 ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {qualityScore >= 80 ? (locale === "vi" ? "Dữ liệu Tốt" : "Good") : (locale === "vi" ? "Cần lưu ý" : "Needs Review")}
                      </span>
                    </div>

                    {/* Issues List */}
                    <div className="space-y-2">
                      {currentAnalysis.data_quality_issues && currentAnalysis.data_quality_issues.length > 0 ? (
                        currentAnalysis.data_quality_issues.map((issue) => (
                          <div
                            key={issue.id}
                            className={`rounded-xl border p-3 shadow-2xs ${
                              issue.severity === "high"
                                ? "border-rose-200 bg-rose-50/50"
                                : issue.severity === "medium"
                                ? "border-amber-200 bg-amber-50/50"
                                : "border-slate-200 bg-white"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2 mb-1">
                              <div className="flex items-center gap-1.5">
                                {issue.severity === "high" ? (
                                  <AlertCircle className="h-4 w-4 text-rose-600 shrink-0" />
                                ) : (
                                  <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
                                )}
                                <span className="font-bold text-xs text-slate-900">{issue.title}</span>
                              </div>
                              <span
                                className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                                  issue.severity === "high"
                                    ? "bg-rose-100 text-rose-700"
                                    : issue.severity === "medium"
                                    ? "bg-amber-100 text-amber-700"
                                    : "bg-slate-100 text-slate-600"
                                }`}
                              >
                                {issue.severity}
                              </span>
                            </div>
                            <p className="text-xs text-slate-700 mt-1">{issue.message}</p>
                            {issue.suggestion && (
                              <p className="text-[11px] text-slate-500 mt-1 italic">
                                💡 <span className="font-medium">{locale === "vi" ? "Gợi ý:" : "Suggestion:"}</span> {issue.suggestion}
                              </p>
                            )}
                          </div>
                        ))
                      ) : (
                        <div className="flex h-36 flex-col items-center justify-center rounded-xl border border-slate-200 bg-white p-4 text-center">
                          <CheckCircle2 className="h-8 w-8 text-emerald-500 mb-1" />
                          <p className="text-xs font-bold text-slate-800">{locale === "vi" ? "Không phát hiện lỗi dữ liệu nghiêm trọng." : "No critical data issues found."}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* TAB 5: AI INSIGHTS & ĐỀ XUẤT */}
                {activeTab === "ai" && (
                  <div className="space-y-3.5">
                    {/* AI Executive Summary Card */}
                    <div className="rounded-xl border border-emerald-200 bg-white p-4 shadow-2xs">
                      <div className="flex items-center gap-2 border-b border-slate-100 pb-2 mb-2.5">
                        <Sparkles className="h-4 w-4 text-emerald-600" />
                        <h4 className="font-bold text-xs text-slate-900">
                          {locale === "vi" ? "Tổng quan dữ liệu (AI Analysis)" : "AI Data Overview"}
                        </h4>
                      </div>
                      <p className="text-xs leading-relaxed text-slate-700 whitespace-pre-wrap">
                        {currentAnalysis.ai_insights?.summary || (locale === "vi" ? "Đang xử lý nhận định AI..." : "Processing AI narrative...")}
                      </p>
                    </div>

                    {/* Key Findings with Verified Evidence Badges */}
                    {currentAnalysis.ai_insights?.key_findings && currentAnalysis.ai_insights.key_findings.length > 0 && (
                      <div className="space-y-2">
                        <h4 className="font-bold text-xs text-slate-900">
                          {locale === "vi" ? "Phát hiện nổi bật (Key Findings)" : "Key Findings"}
                        </h4>
                        {currentAnalysis.ai_insights.key_findings.map((item, idx) => (
                          <div key={idx} className="rounded-xl border border-slate-200 bg-white p-3 shadow-2xs">
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-bold text-xs text-slate-900">{item.title}</span>
                              {item.importance && (
                                <span
                                  className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                                    item.importance === "high"
                                      ? "bg-emerald-100 text-emerald-800"
                                      : "bg-slate-100 text-slate-600"
                                  }`}
                                >
                                  {item.importance}
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-slate-700 mt-1">{item.description}</p>
                            {item.evidence && (
                              <div className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-emerald-50 px-2 py-1 text-[11px] font-medium text-emerald-800 ring-1 ring-emerald-200/60">
                                <Check className="h-3 w-3 text-emerald-600 shrink-0" />
                                <span>{locale === "vi" ? "Bằng chứng số liệu:" : "Evidence:"} {item.evidence}</span>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Actionable Recommendations */}
                    {currentAnalysis.ai_insights?.recommendations && currentAnalysis.ai_insights.recommendations.length > 0 && (
                      <div className="rounded-xl border border-teal-200 bg-teal-50/50 p-3.5 shadow-2xs">
                        <div className="flex items-center gap-2 font-bold text-teal-950 text-xs mb-2">
                          <Zap className="h-4 w-4 text-teal-600" />
                          <span>{locale === "vi" ? "Đề xuất hành động đề xuất" : "Actionable Recommendations"}</span>
                        </div>
                        <ul className="space-y-1.5 text-xs text-slate-700">
                          {currentAnalysis.ai_insights.recommendations.map((rec, rIdx) => (
                            <li key={rIdx} className="flex items-start gap-2">
                              <span className="text-teal-600 font-bold">•</span>
                              <span>{rec}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* CTA: Export to DOCX Report */}
                    {(onSwitchToReportMode || onGenerateDocx) && (
                      <div className="rounded-xl border border-emerald-300 bg-gradient-to-r from-emerald-50 to-teal-50 p-3.5 shadow-2xs">
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                          <div>
                            <h5 className="font-bold text-xs text-emerald-950 flex items-center gap-1.5">
                              <FileText className="h-4 w-4 text-emerald-700" />
                              <span>{locale === "vi" ? "Xuất thành Báo cáo Word DOCX?" : "Create DOCX Report?"}</span>
                            </h5>
                            <p className="text-[11px] text-emerald-800 mt-1">
                              {locale === "vi"
                                ? "Tận dụng toàn bộ số liệu đã kiểm chứng để AI sinh văn bản báo cáo chuyên nghiệp."
                                : "Use these verified insights to automatically produce a full Word report."}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={onSwitchToReportMode || onGenerateDocx}
                            disabled={isGeneratingDocx}
                            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-700 px-3.5 py-2 text-xs font-bold text-white shadow-sm hover:bg-emerald-800 active:scale-95 disabled:opacity-50 shrink-0"
                          >
                            <FileText className="h-3.5 w-3.5" />
                            <span>{locale === "vi" ? "Tạo báo cáo DOCX" : "Create DOCX"}</span>
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </>
            ) : null}
          </div>
        </div>
      </div>

      {/* 3. Floating AI Copilot (Isolated from analysis tabs, opens only on explicit click) */}
      {!isChatOpen && (
        <div className={`fixed ${floatingChatButtonOffsetClass} z-40`}>
          <button
            type="button"
            onClick={() => {
              setHasOpenedChat(true);
              setIsChatOpen(true);
            }}
            className="inline-flex h-11 items-center gap-2 rounded-full bg-slate-900 px-4 text-xs font-semibold text-white shadow-md hover:bg-slate-800 active:scale-95 transition-all group"
            title={locale === "vi" ? "Mở trợ lý AI Copilot" : "Open AI Copilot"}
            aria-label="Mở AI Copilot"
          >
            <Sparkles className="h-4 w-4 text-amber-300 group-hover:rotate-12 transition-transform" />
            <span>{locale === "vi" ? "Hỏi AI" : "Ask AI"}</span>
            {Object.keys(cellHighlightsForActiveSheet).length > 0 && (
              <span className="rounded-full bg-emerald-500 text-white px-1.5 py-0.2 text-[9px] font-bold">
                {Object.keys(cellHighlightsForActiveSheet).length}
              </span>
            )}
          </button>
        </div>
      )}

      {hasOpenedChat && (
        <div
          ref={chatPanelRef}
          className={`fixed bottom-6 right-6 z-50 flex flex-col w-[380px] sm:w-[420px] h-[520px] max-h-[82vh] rounded-2xl border border-slate-300 bg-white shadow-2xl overflow-hidden transition-all duration-200 ${
            isChatOpen
              ? "pointer-events-auto translate-y-0 opacity-100"
              : "pointer-events-none translate-y-4 opacity-0"
          }`}
          aria-hidden={!isChatOpen}
        >
          <ExcelAIChatPanel
            key={`${sessionStorageKey}:${file?.size ?? ""}:${file?.lastModified ?? ""}`}
            fileName={fileName}
            file={file}
            fileId={fileId}
            dataSourceUrl={dataSourceUrl}
            activeSheetName={activeSheetName}
            chatScope={analysisScope || { type: "sheets", sheets: [] }}
            totalRows={currentAnalysis?.overview?.total_rows || 0}
            totalCols={currentAnalysis?.overview?.total_columns || 0}
            selectedRange={selectedRange}
            hasHighlights={Object.keys(cellHighlightsForActiveSheet).length > 0}
            onHighlightCells={handleHighlightCells}
            onClearHighlights={handleClearHighlights}
            onScrollToCell={handleScrollToCell}
            onSwitchSheet={(newSheet) => handleSelectSheet(newSheet)}
            onClose={() => setIsChatOpen(false)}
            activeHighlightColor={activeHighlightColor}
            onHighlightColorChange={setActiveHighlightColor}
            locale={locale}
          />
        </div>
      )}
    </div>
    </WorkbookLedger>
  );
}
