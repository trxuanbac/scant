"use client";

import { useState } from "react";
import {
  Sparkles,
  Send,
  RefreshCw,
  PlusCircle,
  ShieldCheck,
  Bot,
  ArrowDownToLine,
} from "lucide-react";
import { api } from "@/lib/api";

interface AiAssistantPanelProps {
  projectId: string;
  reportId: string;
  activeSection: any;
  onApplyDraft: (text: string, tiptapJson: any) => void | Promise<void>;
}

interface ChatMessage {
  role: "user" | "copilot";
  content: string;
  actionType?: string | null;
  actionPayload?: any;
}

export function AiAssistantPanel({
  projectId,
  reportId,
  activeSection,
  onApplyDraft,
}: AiAssistantPanelProps) {
  const [panelMode, setPanelMode] = useState<"writer" | "copilot">("writer");

  // Writer Mode State
  const [instruction, setInstruction] = useState("");
  const [tone, setTone] = useState("professional");
  const [isDrafting, setIsDrafting] = useState(false);
  const [lastDraft, setLastDraft] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // Copilot Chat Mode State
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      role: "copilot",
      content:
        "Xin chào! Tôi là AI Project Copilot. Bạn có thể yêu cầu tôi viết tiếp, tóm tắt điều hành (Executive Summary), rà soát dữ liệu, tạo bảng so sánh hoặc tinh chỉnh văn phong theo chuẩn chuyên nghiệp.",
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [isChatting, setIsChatting] = useState(false);

  const handleDraftSection = async () => {
    if (!activeSection) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 90000);
    setIsDrafting(true);
    setError(null);
    try {
      const res = await api.ai.draftSection({
        project_id: projectId,
        report_id: reportId,
        section_id: activeSection.id,
        instruction: instruction || undefined,
        tone,
      }, { signal: controller.signal });
      setLastDraft(res);
      await onApplyDraft(res.text, res.tiptap_json);
    } catch (err: any) {
      const message =
        err?.name === "AbortError"
          ? "AI phản hồi quá lâu. Vui lòng thử lại hoặc rút ngắn chỉ đạo soạn thảo."
          : err.message || "Lỗi khi sinh nội dung. Vui lòng thử lại.";
      setError(message);
    } finally {
      window.clearTimeout(timeout);
      setIsDrafting(false);
    }
  };

  const handleSendCopilotMessage = async (customMsg?: string) => {
    const msg = customMsg || chatInput;
    if (!msg.trim()) return;

    const userMsg: ChatMessage = { role: "user", content: msg };
    setChatMessages((prev) => [...prev, userMsg]);
    if (!customMsg) setChatInput("");

    if (isLocalSmallTalk(msg)) {
      setChatMessages((prev) => [
        ...prev,
        {
          role: "copilot",
          content:
            "Chào bạn. Mình là Copilot trong Studio. Bạn cứ hỏi bình thường, còn khi muốn mình làm việc trên tài liệu thì hãy nói rõ như: “hãy viết lại phần này”, “tạo bảng”, hoặc “vẽ biểu đồ”.",
          actionType: null,
          actionPayload: null,
        },
      ]);
      return;
    }

    setIsChatting(true);

    try {
      const res = await api.ai.copilot({
        project_id: projectId,
        report_id: reportId,
        section_id: activeSection?.id,
        message: msg,
      });

      setChatMessages((prev) => [
        ...prev,
        {
          role: "copilot",
          content: res.reply,
          actionType: res.action_type,
          actionPayload: res.payload,
        },
      ]);
    } catch {
      setChatMessages((prev) => [
        ...prev,
        {
          role: "copilot",
          content: "Rất tiếc, đã có lỗi xảy ra trong quá trình xử lý yêu cầu.",
        },
      ]);
    } finally {
      setIsChatting(false);
    }
  };

  const quickPrompts = [
    "Soạn thảo nội dung chuyên sâu và đầy đủ luận điểm",
    "Tạo tóm tắt điều hành (Executive Summary)",
    "Tạo bảng số liệu so sánh & đánh giá",
    "Chuyển đổi sang văn phong Executive cao cấp",
  ];

  const normalizeChatMessage = (value: string) =>
    value
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/[!?.。,…,;:]+/g, "")
      .replace(/\s+/g, " ");

  const isLocalSmallTalk = (value: string) => {
    const normalized = normalizeChatMessage(value);
    const greetings = new Set([
      "hi",
      "hello",
      "hey",
      "xin chao",
      "chao",
      "chao ban",
      "alo",
      "test",
    ]);
    return greetings.has(normalized) || (normalized.split(" ").length <= 3 && /(^|\s)(chao|hi|hello|hey)(\s|$)/.test(normalized));
  };

  return (
    <div className="flex h-full flex-col bg-white text-xs">
      {/* Top Mode Bar */}
      <div className="border-b border-slate-100 bg-slate-50 p-2">
        <div className="mb-2 px-1">
          <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">Trợ lý trong Studio</p>
          <p className="mt-0.5 text-xs font-semibold text-slate-700">
            {panelMode === "writer" ? "Sinh nội dung cho mục đang chọn" : "Hỏi đáp như chatbot, chỉ sửa khi bạn yêu cầu rõ"}
          </p>
        </div>
        <div className="flex items-center gap-1">
        <button
          onClick={() => setPanelMode("writer")}
          className={`flex-1 py-1.5 rounded-lg font-bold text-center transition-all ${
            panelMode === "writer"
              ? "bg-white text-indigo-700 shadow-xs border border-slate-200"
              : "text-slate-500 hover:text-slate-900"
          }`}
        >
          Section Writer
        </button>
        <button
          onClick={() => setPanelMode("copilot")}
          className={`flex-1 py-1.5 rounded-lg font-bold text-center transition-all flex items-center justify-center gap-1 ${
            panelMode === "copilot"
              ? "bg-white text-indigo-700 shadow-xs border border-slate-200"
              : "text-slate-500 hover:text-slate-900"
          }`}
        >
          <Bot className="h-3.5 w-3.5" />
          <span>AI Copilot</span>
        </button>
        </div>
      </div>

      {/* WRITER MODE */}
      {panelMode === "writer" && (
        <>
          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            {activeSection ? (
              <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-600 block mb-0.5">
                  Mục đang chọn (Heading {activeSection.level})
                </span>
                <p className="font-bold text-slate-900 line-clamp-2">{activeSection.title}</p>
              </div>
            ) : (
              <div className="rounded-xl bg-slate-50 p-3 text-center text-slate-400 italic">
                Chọn một mục bên trái để bắt đầu soạn thảo.
              </div>
            )}

            {/* Tone Selector */}
            <div>
              <label className="block text-slate-700 font-semibold mb-1.5">Văn phong báo cáo:</label>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {[
                  { id: "professional", label: "Executive & Quản trị" },
                  { id: "technical", label: "Kỹ thuật & Dữ liệu" },
                ].map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setTone(t.id)}
                    className={`min-h-10 whitespace-normal break-words rounded-lg border px-2 py-2 text-center font-medium leading-snug transition-all ${
                      tone === t.id
                        ? "border-indigo-600 bg-indigo-50 text-indigo-700 font-bold"
                        : "border-slate-200 text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Custom Instruction */}
            <div>
              <label className="block text-slate-700 font-semibold mb-1.5">Chỉ đạo chi tiết cho AI:</label>
              <textarea
                rows={3}
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                placeholder="Ví dụ: Phân tích kỹ các rủi ro vận hành và lập bảng ma trận đánh giá..."
                className="w-full rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-xs outline-none focus:border-indigo-500 focus:bg-white"
              />
            </div>

            {/* Quick Prompts */}
            <div className="space-y-1.5">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Gợi ý nhanh:
              </span>
              <div className="space-y-1">
                {quickPrompts.map((p, idx) => (
                  <button
                    key={idx}
                    onClick={() => setInstruction(p)}
                    className="flex w-full items-start gap-2 rounded-lg bg-slate-50 p-2 text-left text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
                  >
                    <PlusCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-indigo-500" />
                    <span className="leading-snug">{p}</span>
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                {error}
              </div>
            )}

            {lastDraft && (
              <div className="space-y-2 rounded-xl border border-emerald-200 bg-emerald-50/80 p-3">
                <div className="flex items-center gap-1.5 text-emerald-800 font-bold">
                  <ShieldCheck className="h-4 w-4" />
                  <span>Soạn thảo & Kiểm chứng thành công</span>
                </div>
                <p className="text-[11px] text-emerald-700">
                  Nội dung đã lưu vào mục đang chọn. Bấm “Dựng lại trang” để áp vào bản mẫu A4.
                </p>
              </div>
            )}
          </div>

          <div className="border-t border-slate-100 bg-slate-50/50 p-3.5">
            <button
              onClick={handleDraftSection}
              disabled={isDrafting || !activeSection}
              className="flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 font-semibold text-white shadow-xs transition-colors hover:bg-indigo-700 disabled:opacity-50"
            >
              {isDrafting ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  <span>AI đang soạn thảo...</span>
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  <span>Soạn thảo mục này với AI</span>
                </>
              )}
            </button>
          </div>
        </>
      )}

      {/* COPILOT CHAT MODE */}
      {panelMode === "copilot" && (
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Chat Messages */}
          <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50/40 p-3">
            {chatMessages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex gap-2 text-xs ${
                  msg.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                {msg.role === "copilot" && (
                  <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
                    <Bot className="h-3.5 w-3.5" />
                  </div>
                )}

                <div
                  className={`max-w-[85%] space-y-2 rounded-xl p-3 ${
                    msg.role === "user"
                      ? "rounded-br-sm bg-indigo-600 text-white"
                      : "rounded-bl-sm border border-slate-200/80 bg-white text-slate-800"
                  }`}
                >
                  <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>

                  {msg.actionType === "text_insert" && msg.actionPayload?.text && (
                    <button
                      onClick={async () => {
                        if (activeSection) {
                          const newText = `${activeSection.plain_text || ""}\n\n${msg.actionPayload.text}`;
                          await onApplyDraft(newText, null);
                        }
                      }}
                      className="flex items-center gap-1 rounded bg-white px-2 py-1 text-[11px] font-bold text-indigo-700 shadow-xs transition-colors hover:text-indigo-900"
                    >
                      <ArrowDownToLine className="h-3 w-3" />
                      <span>Chèn vào vị trí hiện tại</span>
                    </button>
                  )}
                </div>
              </div>
            ))}

            {isChatting && (
              <div className="flex items-center gap-2 p-2 text-xs text-slate-400 italic">
                <Sparkles className="h-3.5 w-3.5 animate-spin text-indigo-600" />
                <span>Copilot đang phân tích và soạn câu trả lời...</span>
              </div>
            )}
          </div>

          {/* Quick Action Chips */}
          <div className="no-scrollbar flex gap-1.5 overflow-x-auto border-t border-slate-100 bg-white px-3 py-2">
            {[
              { label: "Tạo Executive Summary", prompt: "Hãy soạn thảo phần Tóm tắt điều hành (Executive Summary) cho báo cáo này." },
              { label: "Vẽ sơ đồ Mermaid", prompt: "Hãy tạo một sơ đồ Mermaid flowchart trực quan thể hiện quy trình của phần này." },
              { label: "Chèn bảng dữ liệu", prompt: "Hãy tạo một bảng so sánh dữ liệu chi tiết có định lượng." },
              { label: "Viết tiếp", prompt: "Hãy viết tiếp phát triển sâu hơn luận điểm của phần này." },
            ].map((q, i) => (
              <button
                key={i}
                onClick={() => handleSendCopilotMessage(q.prompt)}
                className="shrink-0 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-medium text-slate-600 transition-colors hover:bg-slate-100"
              >
                {q.label}
              </button>
            ))}
          </div>

          {/* Input Box */}
          <div className="border-t border-slate-100 bg-white p-3">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendCopilotMessage();
              }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Hỏi bình thường hoặc yêu cầu sửa tài liệu..."
                className="h-9 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs outline-none focus:border-indigo-500 focus:bg-white"
              />
              <button
                type="submit"
                disabled={isChatting || !chatInput.trim()}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
              >
                <Send className="h-4 w-4" />
              </button>
            </form>
          </div>

        </div>
      )}
    </div>
  );
}
