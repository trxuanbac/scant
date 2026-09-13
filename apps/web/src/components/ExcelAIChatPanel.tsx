"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  Sparkles,
  Send,
  Trash2,
  Maximize2,
  Minimize2,
  RefreshCw,
  Table,
  Check,
  AlertCircle,
  Download,
  Plus,
  Eye,
  CornerDownLeft,
  X,
  Mic,
  MicOff,
} from "lucide-react";
import { api, resolveApiDownloadUrl } from "@/lib/api";
import { PersistentSpreadsheetActionCard as SpreadsheetActionCard } from "./WorkbookLedger";

export interface ChatMessage {
  id: string;
  sender: "user" | "ai";
  text: string;
  timestamp: string;
  highlightColor?: string;
  highlightColorName?: string;
  context?: {
    sheet?: string;
    ranges?: string[];
  };
  blocks?: Array<{
    type: "kpi" | "cellList" | "text" | "source";
    title?: string;
    value?: number | string;
    subtext?: string;
    items?: Array<{
      value: string;
      count?: number;
      cells: string[];
    }>;
  }>;
  result?: any;
  actions?: Array<{
    type: "HIGHLIGHT_CELLS" | "CLEAR_HIGHLIGHTS" | "SCROLL_TO_CELL";
    sheet?: string;
    cells?: string[];
    style?: string;
    color?: string;
    autoScrollTo?: string;
  }>;
  evidence?: {
    sheet?: string;
    ranges?: string[];
    operation?: string;
    rowCount?: number;
  };
  pending_actions?: Array<{
    id?: string;
    type: "CLEAR_HIGHLIGHTS" | "HIGHLIGHT_ROWS" | "HIGHLIGHT_CELLS" | "FILTER_ROWS" | "SORT" | "CREATE_CHART";
    sheet?: string;
    rows?: number[];
    cells?: string[];
    color?: string;
    label?: string;
    requires_confirmation?: boolean;
  }>;
}

interface ExcelAIChatPanelProps {
  fileName?: string;
  file?: File | null;
  fileId?: string;
  dataSourceUrl?: string;
  activeSheetName: string;
  chatScope?: { type: "sheet" | "sheets" | "workbook"; sheet?: string; sheets?: string[] };
  totalRows?: number;
  totalCols?: number;
  selectedRange?: string | null;
  hasHighlights?: boolean;
  onHighlightCells: (sheetName: string, cells: string[], color?: string, reason?: string) => void;
  onClearHighlights: (sheetName: string) => void;
  onScrollToCell: (address: string) => void;
  onSwitchSheet?: (sheetName: string) => void;
  onClose?: () => void;
  onToggleExpand?: () => void;
  isExpanded?: boolean;
  activeHighlightColor?: string;
  onHighlightColorChange?: (color: string) => void;
  locale?: string;
}

const CHAT_HIGHLIGHT_COLORS = [
  {
    color: "#FEF08A",
    name: "vàng",
    patterns: ["màu vàng", "mau vang", "tô vàng", "to vang", "bôi vàng", "boi vang", "vàng"],
  },
  {
    color: "#FECDD3",
    name: "đỏ",
    patterns: ["màu đỏ", "mau do", "tô đỏ", "to do", "bôi đỏ", "boi do", "đỏ"],
  },
  {
    color: "#BAE6FD",
    name: "xanh nhạt",
    patterns: ["màu xanh nhạt", "mau xanh nhat", "tô xanh nhạt", "to xanh nhat", "bôi xanh nhạt", "boi xanh nhat", "xanh nhạt", "xanh nhat"],
  },
  {
    color: "#BBF7D0",
    name: "xanh lá",
    patterns: ["màu xanh lá", "mau xanh la", "tô xanh lá", "to xanh la", "bôi xanh lá", "boi xanh la", "xanh lá", "xanh la", "xanh"],
  },
  {
    color: "#E9D5FF",
    name: "tím",
    patterns: ["màu tím", "mau tim", "tô tím", "to tim", "bôi tím", "boi tim", "tím"],
  },
  {
    color: "#FED7AA",
    name: "cam",
    patterns: ["màu cam", "mau cam", "tô cam", "to cam", "bôi cam", "boi cam", "cam"],
  },
];

function normalizeChatPromptColorText(text: string): string {
  return (text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d");
}

function hasChatColorPhrase(prompt: string, phrase: string): boolean {
  const normalizedPhrase = normalizeChatPromptColorText(phrase).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^a-z0-9])${normalizedPhrase}([^a-z0-9]|$)`).test(prompt);
}

function resolveChatPromptHighlightColor(prompt: string, fallbackColor = "#FEF08A") {
  const normalizedPrompt = normalizeChatPromptColorText(prompt);
  const matched = CHAT_HIGHLIGHT_COLORS.find((rule) =>
    rule.patterns.some((pattern) => hasChatColorPhrase(normalizedPrompt, pattern))
  );
  const fallback = CHAT_HIGHLIGHT_COLORS.find((rule) => rule.color.toLowerCase() === fallbackColor.toLowerCase());
  return matched
    ? { color: matched.color, name: matched.name, isExplicit: true }
    : { color: fallbackColor || "#FEF08A", name: fallback?.name || "màu đã chọn", isExplicit: false };
}

function describeChatHighlightColor(color?: string): string {
  const match = CHAT_HIGHLIGHT_COLORS.find((rule) => rule.color.toLowerCase() === (color || "").toLowerCase());
  return match?.name || "màu đã chọn";
}

function toXlsxColorHex(color?: string): string {
  const cleaned = (color || "#FEF08A").replace("#", "").trim();
  return cleaned.length === 6 ? cleaned.toUpperCase() : "FEF08A";
}

function getMatchedCellAddress(cell: any): string {
  if (!cell) return "";
  if (typeof cell === "string") return cell.trim();
  return String(cell.address || cell.cell || "").trim();
}

function getMatchedCellAddresses(cells: any[] = []): string[] {
  return cells.map(getMatchedCellAddress).filter(Boolean);
}

function shouldUseSelectedRangeForChat(prompt: string, selectedRange: string | null): boolean {
  if (!selectedRange) return false;
  if (selectedRange.includes(":")) return true;
  const normalized = normalizeChatPromptColorText(prompt);
  const selectionPhrases = ["vùng chọn", "vung chon", "ô đang chọn", "o dang chon", "ô này", "o nay", "selected cell"];
  return selectionPhrases.some((phrase) => normalized.includes(normalizeChatPromptColorText(phrase)));
}

function normalizeVoiceTranscript(raw: string): string {
  if (!raw) return "";
  let text = raw.trim();
  // Normalize "h 6" -> "H6", "I 6" -> "I6"
  text = text.replace(/\b([A-Za-z])\s+(\d+)\b/g, "$1$2");
  // Normalize "H6 đến H137" -> "H6:H137", "H6 tới H137" -> "H6:H137"
  text = text.replace(/([A-Za-z]\d+)\s*(?:đến|tới|sang|to|-)\s*([A-Za-z]\d+)/gi, "$1:$2");
  return text;
}

function getColumnLetter(colIndex: number): string {
  let temp = colIndex;
  let letter = "";
  while (temp > 0) {
    const mod = (temp - 1) % 26;
    letter = String.fromCharCode(65 + mod) + letter;
    temp = Math.floor((temp - mod) / 26);
  }
  return letter || "A";
}

function formatChatMessage(text: string) {
  if (!text) return null;
  const lines = text.split("\n");
  return (
    <div className="space-y-1.5 leading-relaxed font-sans text-xs">
      {lines.map((line, idx) => {
        if (!line.trim()) return <div key={idx} className="h-1.5" />;
        // Split by bold **text**
        const parts = line.split(/(\*\*[^*]+\*\*)/g);
        const renderedLine = parts.map((part, pIdx) => {
          if (part.startsWith("**") && part.endsWith("**")) {
            return (
              <strong key={pIdx} className="font-bold text-slate-900">
                {part.slice(2, -2)}
              </strong>
            );
          }
          return <span key={pIdx}>{part}</span>;
        });

        if (line.trim().startsWith("•") || line.trim().startsWith("-")) {
          return (
            <div key={idx} className="flex items-start gap-1.5 pl-2">
              <span className="text-emerald-600 font-bold shrink-0">•</span>
              <span className="flex-1">{renderedLine}</span>
            </div>
          );
        }

        return <div key={idx}>{renderedLine}</div>;
      })}
    </div>
  );
}

export default function ExcelAIChatPanel({
  fileName = "Bảng tính dữ liệu",
  file,
  fileId,
  dataSourceUrl,
  activeSheetName,
  chatScope = { type: "sheet" },
  totalRows = 0,
  totalCols = 0,
  selectedRange = null,
  hasHighlights = false,
  onHighlightCells,
  onClearHighlights,
  onScrollToCell,
  onSwitchSheet,
  onClose,
  onToggleExpand,
  isExpanded = false,
  activeHighlightColor = "#FEF08A",
  onHighlightColorChange,
  locale = "vi",
}: ExcelAIChatPanelProps) {
  const isWorkbookScope = chatScope.type === "workbook" || chatScope.type === "sheets";
  const scopeLabel = chatScope.type === "sheets" ? (chatScope.sheets || []).join(", ") : isWorkbookScope ? (locale === "vi" ? "Toàn bộ workbook" : "Entire workbook") : (chatScope.sheet || activeSheetName);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "initial-ai",
      sender: "ai",
      text:
        locale === "vi"
          ? `Xin chào! Tôi có thể giúp bạn đọc, giải thích và hỏi đáp về workbook hiện tại. Phạm vi chat hiện tại: **${scopeLabel}**.`
          : `Hello! I can help you read, explain, and answer questions about the current workbook. Current chat scope: **${scopeLabel}**.`,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [inputText, setInputText] = useState("");
  const conversationKey = useRef<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isApplyingToXlsx, setIsApplyingToXlsx] = useState(false);
  const [downloadSuccessUrl, setDownloadSuccessUrl] = useState<string | null>(null);

  // Sync greeting when active sheet or workbook scope changes
  useEffect(() => {
    setMessages((prev) => {
      if (prev.length === 1 && prev[0].id === "initial-ai") {
        return [
          {
            id: "initial-ai",
            sender: "ai",
            text:
              locale === "vi"
                ? `Xin chào! Tôi có thể giúp bạn đọc, giải thích và hỏi đáp về workbook hiện tại. Phạm vi chat hiện tại: **${scopeLabel}**.`
                : `Hello! I can help you read, explain, and answer questions about the current workbook. Current chat scope: **${scopeLabel}**.`,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          },
        ];
      }
      return prev;
    });
  }, [activeSheetName, locale, scopeLabel]);

  // Speech Recognition state
  const [isSpeechSupported, setIsSpeechSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const recognitionRef = useRef<any>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Check speech recognition capability on client mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const SpeechClass = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      setIsSpeechSupported(Boolean(SpeechClass));
    }
  }, []);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const quickPrompts = [
    {
      label: locale === "vi" ? "📋 Có bao nhiêu sheet?" : "📋 How many sheets?",
      prompt: locale === "vi" ? "File này có bao nhiêu sheet?" : "How many sheets are in this workbook?",
    },
    {
      label: isWorkbookScope
        ? locale === "vi"
          ? "📊 Workbook có bao nhiêu dòng?"
          : "📊 Workbook rows?"
        : locale === "vi"
        ? "📊 Sheet này có bao nhiêu dòng?"
        : "📊 How many rows?",
      prompt: isWorkbookScope
        ? locale === "vi"
          ? "Toàn bộ workbook có bao nhiêu dòng dữ liệu?"
          : "How many data rows are in the whole workbook?"
        : locale === "vi"
        ? `Sheet ${activeSheetName} có bao nhiêu dòng dữ liệu?`
        : `How many rows on sheet ${activeSheetName}?`,
    },
    {
      label: locale === "vi" ? "🏆 Ai có giá trị cao nhất?" : "🏆 Highest value?",
      prompt: locale === "vi" ? "Ai có giá trị cao nhất trong cột quan trọng?" : "Who has the highest value?",
    },
    {
      label: locale === "vi" ? "ℹ️ File này nói về gì?" : "ℹ️ What is this file about?",
      prompt: locale === "vi" ? "File này nói về gì?" : "What is this file about?",
    },
  ];

  // Toggle Speech Recognition Voice Input
  const toggleListening = useCallback(() => {
    if (isListening) {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      setIsListening(false);
      return;
    }

    setMicError(null);
    const SpeechClass = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechClass) {
      setMicError("Trình duyệt này chưa hỗ trợ nhập bằng giọng nói Web Speech API.");
      return;
    }

    try {
      const recognition = new SpeechClass();
      recognition.lang = "vi-VN";
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onresult = (event: any) => {
        let interim = "";
        let final = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            final += event.results[i][0].transcript;
          } else {
            interim += event.results[i][0].transcript;
          }
        }
        const transcriptText = final || interim;
        if (transcriptText) {
          const normalized = normalizeVoiceTranscript(transcriptText);
          setInputText((prev) => {
            if (!prev.trim()) return normalized;
            // Prevent duplicate appending
            if (prev.endsWith(normalized)) return prev;
            return `${prev} ${normalized}`;
          });
        }
      };

      recognition.onerror = (event: any) => {
        console.warn("Speech recognition error:", event.error);
        if (event.error === "not-allowed" || event.error === "permission-denied") {
          setMicError("Không thể truy cập microphone. Hãy cấp quyền microphone cho trình duyệt hoặc nhập yêu cầu bằng bàn phím.");
        } else if (event.error !== "no-speech") {
          setMicError(`Lỗi microphone (${event.error}). Bạn có thể nhập yêu cầu bằng bàn phím.`);
        }
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err: any) {
      setMicError("Không thể kích hoạt microphone. Vui lòng kiểm tra quyền thiết bị.");
      setIsListening(false);
    }
  }, [isListening]);

  const handleSendMessage = async (textToSend?: string, event?: React.SyntheticEvent) => {
    event?.preventDefault();
    event?.stopPropagation();

    const query = (textToSend || inputText).trim();
    if (!query || isLoading || (chatScope.type === "sheets" && !chatScope.sheets?.length)) return;
    const requestedHighlightColor = resolveChatPromptHighlightColor(query, activeHighlightColor);
    if (requestedHighlightColor.isExplicit) {
      onHighlightColorChange?.(requestedHighlightColor.color);
    }

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: query,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      highlightColor: requestedHighlightColor.color,
      highlightColorName: requestedHighlightColor.name,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText("");
    setIsLoading(true);
    setDownloadSuccessUrl(null);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const formData = new FormData();
      if (file) {
        formData.append("file", file);
      }
      if (fileId) {
        formData.append("file_id", fileId);
      }
      if (dataSourceUrl) {
        formData.append("data_source_url", dataSourceUrl);
      }
      formData.append("sheet_name", chatScope.type === "sheet" ? (chatScope.sheet || activeSheetName) : activeSheetName);
      formData.append("scope", JSON.stringify(chatScope));
      formData.append("message", query);
      formData.append("highlight_color", requestedHighlightColor.color);
      const shouldUseSelectedRange = !isWorkbookScope && (!chatScope.sheet || chatScope.sheet === activeSheetName) && shouldUseSelectedRangeForChat(query, selectedRange);
      if (shouldUseSelectedRange) {
        formData.append("selected_range", selectedRange as string);
      }
      conversationKey.current ||= crypto.randomUUID();
      formData.append("conversation_id", conversationKey.current);

      const res = await api.data.workbookChat(formData);

      // Sync active sheet in workspace if backend resolved a specific sheet (e.g. from user saying "(HN Chính T8)")
      if (res.context?.sheet && res.context.sheet !== activeSheetName && res.context.sheet !== "workbook") {
        onSwitchSheet?.(res.context.sheet);
      }

      const aiMsg: ChatMessage = {
        id: `ai-${Date.now()}`,
        sender: "ai",
        text: res.answer || "Đã phân tích xong dữ liệu.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        context: res.context,
        blocks: res.blocks || [],
        result: res.result || {},
        actions: res.actions || [],
        evidence: res.evidence,
        pending_actions: [
          ...(res.pending_actions || []),
          ...(res.actions || []).filter((action: { type: string }) => action.type === "HIGHLIGHT_CELLS" || action.type === "CLEAR_HIGHLIGHTS"),
          ...(getMatchedCellAddresses(res.result?.matched_cells || []).length ? [{
            type: "HIGHLIGHT_CELLS" as const,
            sheet: res.context?.sheet || activeSheetName,
            cells: getMatchedCellAddresses(res.result.matched_cells),
          }] : []),
        ].map((action) => ({ ...action, sheet: action.sheet || res.context?.sheet || activeSheetName })),
        highlightColor: requestedHighlightColor.color,
        highlightColorName: requestedHighlightColor.name,
      };

      setMessages((prev) => [...prev, aiMsg]);

      // Navigation is read-only. Highlight and clear actions require preview/confirmation.
      for (const action of res.actions || []) {
        if (action.type === "SCROLL_TO_CELL" && action.cells?.[0]) {
          onScrollToCell(action.cells[0]);
        }
      }
    } catch (err: any) {
      if (err.name === "AbortError") {
        setMessages((prev) => [
          ...prev,
          {
            id: `ai-abort-${Date.now()}`,
            sender: "ai",
            text: locale === "vi" ? "Đã hủy yêu cầu xử lý." : "Request cancelled.",
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            id: `ai-err-${Date.now()}`,
            sender: "ai",
            text:
              locale === "vi"
                ? `❌ Lỗi xử lý câu hỏi: ${err.message || "Vui lòng thử lại với tên vùng cụ thể như H6:H137."}`
                : `❌ Error processing query: ${err.message || "Please retry."}`,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          },
        ]);
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  const handleCancelQuery = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  const handleClearConversation = () => {
    setMessages([
      {
        id: "initial-ai-reset",
        sender: "ai",
        text:
          locale === "vi"
            ? `Cuộc trò chuyện đã được làm mới cho sheet **${activeSheetName}**.`
            : `Conversation refreshed for sheet **${activeSheetName}**.`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
    onClearHighlights(activeSheetName);
    setDownloadSuccessUrl(null);
  };

  const handleApplyToXlsxFile = async (sheet: string, cells: string[], color?: string) => {
    if (!sheet || !cells || cells.length === 0) return;
    if (!window.confirm(locale === "vi" ? `Tạo bản XLSX tô màu ${color || activeHighlightColor} cho ${cells.length} ô trên sheet ${sheet}: ${cells.slice(0, 12).join(", ")}${cells.length > 12 ? "…" : ""}? File gốc và Google Sheets sẽ không thay đổi.` : `Create an XLSX copy highlighting ${cells.length} cells on ${sheet}? The original file and Google Sheets will not change.`)) return;
    setIsApplyingToXlsx(true);
    setDownloadSuccessUrl(null);

    try {
      const formData = new FormData();
      if (file) formData.append("file", file);
      if (fileId) formData.append("file_id", fileId);
      if (dataSourceUrl) formData.append("data_source_url", dataSourceUrl);
      formData.append("sheet_name", sheet);
      formData.append("cells", JSON.stringify(cells));
      formData.append("color_hex", toXlsxColorHex(color));

      const res = await api.data.applyModifications(formData);
      if (res.ok && res.download_url) {
        setDownloadSuccessUrl(resolveApiDownloadUrl(res.download_url));
      }
    } catch (err: any) {
      alert(`Lỗi khi lưu chỉnh sửa vào XLSX: ${err.message || "Vui lòng thử lại"}`);
    } finally {
      setIsApplyingToXlsx(false);
    }
  };

  const insertSelectedRange = () => {
    if (!selectedRange) return;
    setInputText((prev) => (prev ? `${prev} ${selectedRange}` : `Kiểm tra ${selectedRange} xem có bị trùng lặp`));
  };

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col bg-slate-50 font-sans text-slate-800 overflow-hidden">
      {/* 1. Header Toolbar */}
      <div className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-3.5 py-2.5 shadow-2xs">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-600 text-white shadow-xs">
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-bold text-slate-900 truncate">
                {locale === "vi" ? "✨ AI Copilot" : "✨ AI Copilot"}
              </span>
              <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800 ring-1 ring-emerald-200">
                {scopeLabel}
              </span>
            </div>
            <p className="text-[10px] text-slate-400">
              {isWorkbookScope
                ? `${locale === "vi" ? (chatScope.type === "sheets" ? "Hỏi đáp các bảng đã chọn" : "Hỏi đáp toàn bộ workbook") : (chatScope.type === "sheets" ? "Selected sheets Q&A" : "Whole-workbook Q&A")} · ${chatScope.sheets?.length || 0} ${locale === "vi" ? "sheet" : "sheets"}`
                : `${locale === "vi" ? "Hỏi đáp tự nhiên về bảng tính" : "Natural language workbook assistant"} · ${totalRows.toLocaleString()} ${locale === "vi" ? "dòng" : "rows"} · ${totalCols} ${locale === "vi" ? "cột" : "cols"}`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {hasHighlights && (
            <button
              type="button"
              onClick={() => onClearHighlights(activeSheetName)}
              className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-1 text-[11px] font-bold text-amber-700 hover:bg-amber-100 ring-1 ring-amber-200 transition"
              title={locale === "vi" ? "Xóa màu đánh dấu trên bảng" : "Clear highlights"}
            >
              <Trash2 className="h-3 w-3" />
              <span>{locale === "vi" ? "Xóa màu" : "Clear"}</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleClearConversation}
            className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            title={locale === "vi" ? "Làm mới cuộc trò chuyện" : "New conversation"}
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>

          {onToggleExpand && (
            <button
              type="button"
              onClick={onToggleExpand}
              className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              title={isExpanded ? (locale === "vi" ? "Thu nhỏ panel" : "Collapse panel") : (locale === "vi" ? "Mở rộng panel" : "Expand panel")}
            >
              {isExpanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            </button>
          )}

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition ml-0.5"
              title={locale === "vi" ? "Đóng AI Copilot" : "Close AI Copilot"}
              aria-label="Đóng AI Copilot"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* 2. Messages List (Bounded vertical scrolling inside chat panel) */}
      <div className="flex-1 min-h-0 min-w-0 overflow-y-auto p-3.5 space-y-3.5">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
          >
            {/* Context Badge */}
            {msg.context?.ranges && msg.context.ranges.length > 0 && (
              <div className="mb-1 flex items-center gap-1 text-[10px] text-slate-400">
                <Table className="h-3 w-3" />
                <span>{locale === "vi" ? "Đang hỏi về" : "Asking about"} {msg.context.sheet} • {msg.context.ranges.join(", ")}</span>
              </div>
            )}

            {/* Bubble */}
            <div
              className={`max-w-[90%] rounded-2xl p-3 text-xs leading-relaxed shadow-2xs ${
                msg.sender === "user"
                  ? "bg-emerald-600 text-white rounded-br-xs"
                  : "bg-white text-slate-800 border border-slate-200/90 rounded-bl-xs"
              }`}
            >
              {msg.sender === "user" ? (
                <div className="whitespace-pre-wrap font-sans">{msg.text}</div>
              ) : (
                formatChatMessage(msg.text)
              )}

              {msg.sender === "ai" && msg.evidence?.ranges?.length ? (
                <div className="mt-2 flex flex-wrap gap-1.5 border-t border-slate-100 pt-2">
                  {msg.evidence.ranges.map((range) => {
                    const firstCell = range.split(":")[0];
                    return (
                      <button
                        key={`${msg.id}-${range}`}
                        type="button"
                        onClick={() => firstCell && onScrollToCell(firstCell)}
                        className="rounded-md bg-blue-50 px-2 py-0.5 font-mono text-[10px] font-bold text-blue-800 ring-1 ring-blue-200 hover:bg-blue-100"
                      >
                        Nguồn: {msg.evidence?.sheet} · {range}
                      </button>
                    );
                  })}
                </div>
              ) : null}

              {/* Render KPI Blocks */}
              {msg.blocks && msg.blocks.length > 0 && (
                <div className="mt-2.5 space-y-2">
                  {msg.blocks
                    .filter((b) => b.type === "kpi")
                    .map((kpi, kIdx) => (
                      <div
                        key={kIdx}
                        className="flex items-center justify-between rounded-xl bg-slate-50 border border-slate-200 p-2.5"
                      >
                        <div>
                          <p className="text-[10px] font-bold uppercase text-slate-500">{kpi.title}</p>
                          <p className="text-base font-extrabold text-slate-900">{kpi.value}</p>
                        </div>
                        {kpi.subtext && (
                          <span className="text-[11px] font-medium text-emerald-700">{kpi.subtext}</span>
                        )}
                      </div>
                    ))}

                  {/* Render Cell List Block */}
                  {msg.blocks
                    .filter((b) => b.type === "cellList")
                    .map((cellBlock, bIdx) => (
                      <div
                        key={bIdx}
                        className="rounded-xl border border-slate-200 bg-slate-50/70 p-2.5 space-y-1.5"
                      >
                        <p className="text-[11px] font-bold text-slate-700 flex items-center justify-between">
                          <span>{cellBlock.title || "Chi tiết các ô"}</span>
                          <span className="text-[10px] text-slate-400 font-normal">
                            {locale === "vi" ? "Click vào ô để cuộn tới" : "Click to scroll"}
                          </span>
                        </p>
                        <div className="max-h-40 overflow-y-auto space-y-1 pr-1 text-[11px]">
                          {(cellBlock.items || []).map((item, iIdx) => (
                            <div
                              key={iIdx}
                              className="flex items-center justify-between rounded-lg bg-white p-1.5 border border-slate-200/60"
                            >
                              <span className="font-semibold text-slate-800 truncate max-w-[140px]" title={item.value}>
                                {item.value}
                              </span>
                              <div className="flex flex-wrap gap-1 justify-end">
                                {item.cells.map((addr) => (
                                  <button
                                    key={addr}
                                    type="button"
                                    onClick={() => onScrollToCell(addr)}
                                    className="rounded bg-yellow-100 px-1.5 py-0.5 text-[10px] font-bold text-yellow-900 hover:bg-yellow-200 active:scale-95 transition"
                                  >
                                    {addr}
                                  </button>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  {/* Expandable Dev / Execution Details Box */}
                  {msg.result?.execution && (
                    <details className="mt-2.5 rounded-xl border border-slate-200 bg-slate-50/90 p-2 text-[11px] text-slate-600">
                      <summary className="cursor-pointer font-bold text-slate-700 select-none hover:text-emerald-700">
                        📊 {locale === "vi" ? "Xem dữ liệu đã kiểm tra (Data Inspection)" : "View Inspected Data Details"}
                      </summary>
                      <div className="mt-2 space-y-1.5 pt-1.5 border-t border-slate-200 font-mono text-[10px] text-slate-600">
                        <p>• <strong>Sheet:</strong> {msg.context?.sheet || activeSheetName}</p>
                        {msg.result.first_range && (
                          <p>
                            • <strong>{msg.result.first_range}:</strong> {msg.result.execution.range_a_total_cells || msg.result.execution.range_total_cells || 0} ô ({msg.result.execution.range_a_non_empty || msg.result.execution.range_non_empty || 0} ô có dữ liệu) — {msg.result.within_first_range_count || 0} giá trị lặp nội bộ
                          </p>
                        )}
                        {msg.result.second_range && (
                          <p>
                            • <strong>{msg.result.second_range}:</strong> {msg.result.execution.range_b_total_cells || 0} ô ({msg.result.execution.range_b_non_empty || 0} ô có dữ liệu) — {msg.result.within_second_range_count || 0} giá trị lặp nội bộ
                          </p>
                        )}
                        {msg.result.cross_range_count !== undefined && (
                          <p>• <strong>Trùng giữa 2 vùng:</strong> {msg.result.cross_range_count} giá trị</p>
                        )}
                      </div>
                    </details>
                  )}

                </div>
              )}

              {msg.sender === "ai" && msg.pending_actions && msg.pending_actions.length > 0 && (
                <div className="mt-3 space-y-2 border-t border-slate-100 pt-2.5">
                  {msg.pending_actions.filter((action, index, actions) => {
                    const signature = (item: NonNullable<ChatMessage["pending_actions"]>[number]) => JSON.stringify([
                      item.type, item.sheet, [...new Set(item.cells || [])].sort(), [...new Set(item.rows || [])].sort(),
                      msg.highlightColor || item.color || activeHighlightColor,
                    ]);
                    return actions.findIndex((item) => signature(item) === signature(action)) === index;
                  }).map((action, actionIdx) => {
                    const sheet = action.sheet || msg.context?.sheet || "";
                    const color = msg.highlightColor || action.color || activeHighlightColor || "#FEF08A";
                    const rows = [...new Set(action.rows || [])];
                    const rowAction = action.type === "HIGHLIGHT_ROWS";
                    const clear = action.type === "CLEAR_HIGHLIGHTS";
                    const validRows = rows.length > 0 && rows.every((row) => Number.isInteger(row) && row > 0 && row <= totalRows);
                    const canExpandRows = rowAction && sheet === activeSheetName && validRows && totalCols > 0 && rows.length * totalCols <= 50000;
                    const cells = [...new Set(canExpandRows ? rows.flatMap((row) => Array.from({ length: totalCols }, (_, idx) => `${getColumnLetter(idx + 1)}${row}`)) : action.cells || [])];
                    const supported = clear || action.type === "HIGHLIGHT_CELLS" || rowAction;
                    const unavailable = !supported
                      ? (locale === "vi" ? "Hành động này chưa được hỗ trợ trong giao diện." : "This action is not supported in this view.")
                      : !sheet || sheet === "workbook"
                        ? (locale === "vi" ? "Cần xác định sheet cụ thể trước khi áp dụng." : "A specific sheet is required before applying.")
                        : rowAction && !canExpandRows
                          ? (locale === "vi" ? "Mở sheet đích và kiểm tra phạm vi hàng (tối đa 50.000 ô)." : "Open the target sheet and check the row range (maximum 50,000 cells).")
                          : !clear && (!cells.length || cells.length > 50000 || cells.some((cell) => !/^[A-Z]+[1-9][0-9]*$/.test(cell)))
                            ? (locale === "vi" ? "Phạm vi ô không hợp lệ hoặc vượt quá 50.000 ô." : "The cell range is invalid or exceeds 50,000 cells.") : undefined;
                    return <SpreadsheetActionCard
                      key={`${msg.id}-pending-${actionIdx}`}
                      label={action.label || (!supported ? action.type : clear ? (locale === "vi" ? "Xóa lớp tô màu" : "Clear highlights") : (locale === "vi" ? "Tô màu trong bảng" : "Highlight in table"))}
                      sheet={sheet}
                      cells={cells}
                      rows={rowAction ? rows : undefined}
                      color={color}
                      clear={clear}
                      unavailable={unavailable}
                      locale={locale}
                      onConfirm={() => {
                        if (clear) onClearHighlights(sheet);
                        else onHighlightCells(sheet, cells, color, "AI confirmed local action");
                      }}
                    />;
                  })}
                </div>
              )}

              {/* Action Buttons inside AI message */}
              {msg.sender === "ai" && msg.result?.matched_cells && msg.result.matched_cells.length > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-slate-100 pt-2.5">
                  {(() => {
                    const matchedAddresses = getMatchedCellAddresses(msg.result.matched_cells);
                    const firstAddress = matchedAddresses[0];
                    if (!firstAddress) return null;
                    return (
                      <>
                        <button
                          type="button"
                          onClick={() => onScrollToCell(firstAddress)}
                          className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-700 hover:bg-slate-200 active:scale-95 transition"
                        >
                          <Eye className="h-3 w-3" />
                          <span>{locale === "vi" ? `Đi tới ô đầu (${firstAddress})` : `Go to ${firstAddress}`}</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => handleApplyToXlsxFile(msg.context?.sheet || "", matchedAddresses, msg.highlightColor || activeHighlightColor)}
                          disabled={isApplyingToXlsx}
                          className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-2.5 py-1 text-[11px] font-bold text-emerald-800 hover:bg-emerald-100 active:scale-95 disabled:opacity-50 transition"
                        >
                          <Download className={`h-3 w-3 ${isApplyingToXlsx ? "animate-spin" : ""}`} />
                          <span>{isApplyingToXlsx ? (locale === "vi" ? "Đang lưu..." : "Saving...") : (locale === "vi" ? "Lưu vào XLSX" : "Save to XLSX")}</span>
                        </button>
                      </>
                    );
                  })()}
                </div>
              )}

              <span
                className={`mt-1 block text-[9px] ${
                  msg.sender === "user" ? "text-emerald-100 text-right" : "text-slate-400"
                }`}
              >
                {msg.timestamp}
              </span>
            </div>
          </div>
        ))}

        {/* Download file success notice */}
        {downloadSuccessUrl && (
          <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-3 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2 text-emerald-900 font-bold">
              <Check className="h-4 w-4 text-emerald-600" />
              <span>{locale === "vi" ? "Đã áp dụng màu vào file XLSX!" : "Applied highlights to XLSX!"}</span>
            </div>
            <a
              href={downloadSuccessUrl}
              download
              className="inline-flex items-center gap-1 rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-emerald-800 transition"
            >
              <Download className="h-3 w-3" />
              <span>{locale === "vi" ? "Tải file XLSX" : "Download XLSX"}</span>
            </a>
          </div>
        )}

        {/* Loading Indicator */}
        {isLoading && (
          <div className="flex items-center gap-2 rounded-xl bg-white border border-slate-200 p-3 text-xs text-slate-600 shadow-2xs">
            <RefreshCw className="h-3.5 w-3.5 animate-spin text-emerald-600" />
            <span>{locale === "vi" ? "AI đang đọc và tính toán trên bảng tính..." : "AI is reading and computing spreadsheet..."}</span>
            <button
              type="button"
              onClick={handleCancelQuery}
              className="ml-auto rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600 hover:bg-slate-200"
            >
              {locale === "vi" ? "Hủy" : "Cancel"}
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 3. Quick Prompts Bar */}
      {messages.length <= 3 && (
        <div className="border-t border-slate-200 bg-white/70 px-3 py-2">
          <p className="text-[10px] font-bold uppercase text-slate-400 mb-1.5">
            {locale === "vi" ? "Gợi ý câu hỏi nhanh:" : "Suggested queries:"}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {quickPrompts.map((qp, idx) => (
              <button
                key={idx}
                type="button"
                onClick={(e) => handleSendMessage(qp.prompt, e)}
                disabled={isLoading}
                className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-900 transition disabled:opacity-50"
              >
                {qp.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 4. Bottom Input Box (Fixed at bottom of chat panel) */}
      <div className="shrink-0 border-t border-slate-200 bg-white p-3 space-y-2 shadow-xs">
        {/* Microphone Error Alert */}
        {micError && (
          <div className="flex items-center justify-between rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900 border border-amber-200">
            <div className="flex items-center gap-1.5">
              <AlertCircle className="h-3.5 w-3.5 text-amber-600 shrink-0" />
              <span>{micError}</span>
            </div>
            <button type="button" onClick={() => setMicError(null)} className="text-amber-500 hover:text-amber-800">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {/* Listening Active Banner */}
        {isListening && (
          <div className="flex items-center justify-between rounded-lg bg-rose-50 px-3 py-1.5 text-xs text-rose-800 font-bold border border-rose-200 animate-pulse">
            <div className="flex items-center gap-2">
              <span className="flex h-2.5 w-2.5 rounded-full bg-rose-600 animate-ping" />
              <span>{locale === "vi" ? "🔴 Đang nghe giọng nói... Nói xong văn bản sẽ vào khung nhập." : "🔴 Listening to voice..."}</span>
            </div>
            <button
              type="button"
              onClick={toggleListening}
              className="rounded bg-rose-600 px-2 py-0.5 text-[10px] font-bold text-white hover:bg-rose-700 active:scale-95"
            >
              {locale === "vi" ? "Dừng nói" : "Stop"}
            </button>
          </div>
        )}

        {/* Selected Range Indicator */}
        {selectedRange && (
          <div className="flex items-center justify-between rounded-lg bg-blue-50 px-2.5 py-1 text-[11px] text-blue-900 font-medium border border-blue-200">
            <span className="truncate">
              {locale === "vi" ? "Đang chọn vùng:" : "Selected range:"} <strong className="font-mono">{selectedRange}</strong>
            </span>
            <button
              type="button"
              onClick={insertSelectedRange}
              className="inline-flex items-center gap-1 rounded bg-blue-600 px-2 py-0.5 text-[10px] font-bold text-white hover:bg-blue-700 transition"
            >
              <Plus className="h-3 w-3" />
              <span>{locale === "vi" ? "+ Vùng chọn" : "+ Add"}</span>
            </button>
          </div>
        )}

        {/* Input Textarea & Voice Button & Send Button */}
        <div className="relative flex items-end gap-2">
          {/* Microphone Voice Button */}
          <button
            type="button"
            onClick={toggleListening}
            disabled={isLoading || !isSpeechSupported}
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition shadow-xs ${
              isListening
                ? "bg-rose-600 text-white ring-4 ring-rose-200 animate-bounce"
                : isSpeechSupported
                ? "bg-slate-100 text-slate-700 hover:bg-emerald-50 hover:text-emerald-700 active:scale-95 border border-slate-200"
                : "bg-slate-100 text-slate-400 cursor-not-allowed opacity-60 border border-slate-200"
            }`}
            title={
              !isSpeechSupported
                ? (locale === "vi" ? "Trình duyệt này chưa hỗ trợ nhập bằng giọng nói." : "Browser does not support Speech Recognition.")
                : isListening
                ? (locale === "vi" ? "Đang nghe... Click để dừng" : "Listening... Click to stop")
                : (locale === "vi" ? "Nói bằng Microphone (Tiếng Việt)" : "Speak via Microphone (vi-VN)")
            }
          >
            {isListening ? <Mic className="h-5 w-5 animate-pulse" /> : <Mic className="h-4 w-4" />}
          </button>

          {/* Textarea */}
          <textarea
            rows={2}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                e.stopPropagation();
                handleSendMessage(undefined, e);
              }
            }}
            placeholder={
              locale === "vi"
                ? "Hỏi về dữ liệu..."
                : "Ask about the data..."
            }
            className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-xs text-slate-900 placeholder-slate-400 outline-none focus:border-emerald-500 focus:bg-white focus:ring-1 focus:ring-emerald-500"
          />

          {/* Send Button */}
          <button
            type="button"
            onClick={(e) => handleSendMessage(undefined, e)}
            disabled={!inputText.trim() || isLoading || (chatScope.type === "sheets" && !chatScope.sheets?.length)}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-xs transition hover:bg-emerald-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
            title={locale === "vi" ? "Gửi câu hỏi" : "Send message"}
          >
            {isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}
