"use client";

import { useCallback, useState, useEffect } from "react";
import {
  Search,
  Globe,
  ExternalLink,
  RefreshCw,
  BookOpen,
} from "lucide-react";
import { api } from "@/lib/api";
import { DoiResolverModal } from "@/components/DoiResolverModal";

interface ResearchPanelProps {
  projectId: string;
  onInsertCitation?: (citationKey: string) => void;
}

export function ResearchPanel({ projectId, onInsertCitation }: ResearchPanelProps) {
  const [query, setQuery] = useState("");
  const [sources, setSources] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [mode, setMode] = useState("standard");
  const [sourceFilter, setSourceFilter] = useState<"all" | "cited" | "unused">("all");

  const [isDoiModalOpen, setIsDoiModalOpen] = useState(false);
  const visibleSources = sources
    .map((source, sourceIndex) => ({ source, sourceIndex }))
    .filter(({ source }) => sourceFilter === "all" || (sourceFilter === "cited" ? source.citation_count > 0 : !source.citation_count));

  const loadSources = useCallback(async () => {
    try {
      const list = await api.research.listSources(projectId);
      setSources(list);
    } catch {}
  }, [projectId]);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setIsSearching(true);
    try {
      await api.research.search(projectId, query, mode);
      await loadSources();
    } catch {}
    finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white text-xs">
      {/* Header */}
      <div className="p-3.5 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Globe className="h-4 w-4 text-indigo-600" />
          <span className="font-bold text-slate-800">Kho Nguồn & Research</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <button
            onClick={() => setIsDoiModalOpen(true)}
            className="flex items-center space-x-1 px-2 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-[10px] font-bold transition"
            title="Nhập DOI hoặc ArXiv link"
          >
            <BookOpen className="h-3 w-3" />
            <span>+ DOI / ArXiv</span>
          </button>
          <span className="text-[11px] font-semibold text-slate-500">({sources.length})</span>
        </div>
      </div>

      {/* Search Input */}
      <div className="p-3.5 border-b border-slate-100 bg-slate-50/50">
        <form onSubmit={handleSearch} className="space-y-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Tìm kiếm tài liệu học thuật..."
              className="w-full h-8 pl-8 pr-2.5 bg-white border border-slate-200 rounded-lg text-xs outline-none focus:border-indigo-500"
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1 text-[10px]">
              {["quick", "standard", "deep"].map((m) => (
                <button
                  type="button"
                  key={m}
                  onClick={() => setMode(m)}
                  className={`px-2 py-0.5 rounded capitalize ${
                    mode === m ? "bg-indigo-600 text-white font-bold" : "bg-slate-200 text-slate-600"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>

            <button
              type="submit"
              disabled={isSearching}
              className="px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded text-[11px] font-semibold transition-colors disabled:opacity-50 flex items-center gap-1"
            >
              {isSearching ? <RefreshCw className="h-3 w-3 animate-spin" /> : "Tìm kiếm"}
            </button>
          </div>
        </form>
      </div>

      {/* Sources List */}
      <div className="flex items-center gap-1 border-b border-slate-100 px-3.5 py-2" aria-label="Lọc nguồn theo trạng thái sử dụng">
        {([
          ["all", `Tất cả ${sources.length}`],
          ["cited", `Đã trích dẫn ${sources.filter((source) => source.citation_count > 0).length}`],
          ["unused", `Chưa sử dụng ${sources.filter((source) => !source.citation_count).length}`],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setSourceFilter(value)}
            className={`rounded-md px-2 py-1 text-[10px] font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${sourceFilter === value ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-100 hover:text-slate-800"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {visibleSources.length === 0 ? (
          <div className="p-6 text-center text-slate-400 italic">
            {sources.length === 0 ? "Chưa có nguồn tài liệu. Nhập từ khóa ở trên để tìm kiếm nguồn phù hợp." : "Không có nguồn nào trong bộ lọc này."}
          </div>
        ) : (
          visibleSources.map(({ source: src, sourceIndex }) => (
            <div
              key={src.id}
              className="p-3 bg-white rounded-xl border border-slate-200 hover:border-indigo-300 transition-all space-y-2 shadow-xs"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-1.5 flex-1 min-w-0">
                  <span className="h-5 w-5 rounded bg-indigo-50 text-indigo-700 font-bold text-[10px] flex items-center justify-center shrink-0">
                    [{sourceIndex + 1}]
                  </span>
                  <h4 className="font-bold text-slate-900 truncate">{src.title}</h4>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${
                    src.verification_status === "VERIFIED"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : src.verification_status === "PARTIALLY_VERIFIED"
                        ? "border-amber-200 bg-amber-50 text-amber-700"
                        : "border-slate-200 bg-slate-50 text-slate-600"
                  }`}>
                    {src.verification_status === "VERIFIED" ? "Đã kiểm chứng" : src.verification_status === "PARTIALLY_VERIFIED" ? "Đã đối chiếu" : "Cần kiểm tra"}
                  </span>
                  {(src.canonical_url || src.url) && (
                    <a
                      href={src.canonical_url || src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-1 text-slate-400 hover:text-indigo-600 transition-colors"
                      aria-label={`Mở nguồn ${src.title}`}
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
              </div>

              <p className="text-[11px] text-slate-500 line-clamp-2 leading-relaxed">
                {src.summary || src.content_extracted || "Nguồn chưa có phần tóm tắt."}
              </p>

              <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-400">
                <span className="min-w-0 truncate">
                  {[src.publisher || src.organization, src.published_date || src.publication_year].filter(Boolean).join(" · ") || src.domain_trust || src.source_type}
                  {src.citation_count > 0 ? ` · ${src.citation_count} trích dẫn` : ""}
                </span>
                {onInsertCitation && (
                  <button
                    onClick={() => onInsertCitation(`[${sourceIndex + 1}]`)}
                    className="text-indigo-600 font-bold hover:underline"
                  >
                    + Chèn [{sourceIndex + 1}]
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      <DoiResolverModal
        projectId={projectId}
        isOpen={isDoiModalOpen}
        onClose={() => setIsDoiModalOpen(false)}
        onSourceAdded={loadSources}
      />
    </div>
  );
}
