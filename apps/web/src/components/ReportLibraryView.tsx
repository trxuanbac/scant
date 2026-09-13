"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, Clock, Edit3, FileText, Plus, Search } from "lucide-react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { PreviewModal } from "@/components/PreviewModal";
import { buildDocumentPreview } from "@/lib/documentCards";
import { buildReportPreviewFrameSrcDoc } from "@/lib/reportPreviewFrame";

export function ReportLibraryView({ embedded = false }: { embedded?: boolean }) {
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [previewReport, setPreviewReport] = useState<any | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewFrames, setPreviewFrames] = useState<Record<string, string>>({});

  useEffect(() => {
    async function loadReports() {
      try {
        setReports(await api.reports.list());
      } catch {
        // user might not have reports yet
      } finally {
        setLoading(false);
      }
    }
    loadReports();
  }, []);

  const filtered = useMemo(
    () => reports.filter((r) => r.title?.toLowerCase().includes(search.toLowerCase())),
    [reports, search],
  );
  const filteredIdsKey = filtered.map((r) => r.id).join("|");

  useEffect(() => {
    if (!filteredIdsKey) return;
    let cancelled = false;
    const missingReports = filtered.filter((report) => report.id && !previewFrames[report.id]);
    if (missingReports.length === 0) return;

    async function loadPreviewFrames() {
      const loaded = await Promise.all(
        missingReports.slice(0, 24).map(async (report) => {
          try {
            const preview = await api.exports.previewReportHtml(report.id);
            return [report.id, buildReportPreviewFrameSrcDoc(preview.html_document)] as const;
          } catch {
            return [report.id, ""] as const;
          }
        })
      );
      if (!cancelled) {
        setPreviewFrames((prev) => ({
          ...prev,
          ...Object.fromEntries(loaded.filter(([, url]) => url)),
        }));
      }
    }

    loadPreviewFrames();
    return () => {
      cancelled = true;
    };
  }, [filtered, filteredIdsKey, previewFrames]);

  const openReportPreview = async (report: any) => {
    setPreviewReport(report);
    setPreviewLoading(true);
    try {
      setPreviewReport(await api.reports.get(report.id));
    } catch {
      setPreviewReport(report);
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {!embedded && <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Quản lý Tài liệu & Báo cáo</h1>
          <p className="text-xs text-slate-500">Tất cả tài liệu được tạo và quản lý trong hệ thống</p>
        </div>
        <Link
          href="/projects/new"
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors"
        >
          <Plus className="h-4 w-4" />
          <span>Tạo tài liệu mới</span>
        </Link>
      </div>}

      <div className="flex items-center gap-3 bg-white p-3 rounded-xl border border-slate-200">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Tìm kiếm tài liệu..."
            className="w-full h-9 pl-9 pr-3 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:border-indigo-500 outline-none"
          />
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-36 rounded-xl bg-slate-100 animate-pulse border border-slate-200" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center space-y-3">
          <FileText className="mx-auto h-10 w-10 text-slate-400" />
          <h3 className="text-sm font-bold text-slate-800">Chưa có tài liệu nào</h3>
          <p className="text-xs text-slate-500">Bắt đầu bằng việc tạo một báo cáo hoặc tài liệu mới.</p>
          <Link
            href="/projects/new"
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            <span>Tạo mới ngay</span>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {filtered.map((rep) => {
            const preview = buildDocumentPreview(rep);
            const previewFrame = previewFrames[rep.id];
            return (
              <article
                key={rep.id}
                className="group overflow-hidden rounded-xl border border-slate-200 bg-white transition-all hover:border-indigo-300 hover:shadow-sm"
              >
                <button
                  type="button"
                  onClick={() => openReportPreview(rep)}
                  className="block w-full bg-slate-100/70 px-4 py-4 text-left"
                >
                  <div className="mx-auto aspect-[3/4] w-28 overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm transition-transform group-hover:-translate-y-0.5">
                    {previewFrame ? (
                      <iframe
                        title={`Ảnh xem trước ${rep.title}`}
                        srcDoc={previewFrame}
                        className="h-full w-full border-0 bg-white"
                        tabIndex={-1}
                      />
                    ) : (
                      <div className="h-full p-3">
                        <div className="mb-2 h-1.5 w-12 rounded-full bg-slate-900" />
                        <div className="mb-2 h-1 w-16 rounded-full bg-indigo-200" />
                        <div className="space-y-1.5">
                          {preview.lines.map((line, index) => (
                            <div
                              key={`${line}-${index}`}
                              className={`h-1 rounded-full ${index === 0 ? "bg-slate-500" : "bg-slate-200"}`}
                              style={{ width: `${Math.max(38, Math.min(94, line.length * 3))}%` }}
                            />
                          ))}
                        </div>
                        <div className="mt-3 grid grid-cols-3 gap-1">
                          <div className="h-5 rounded-sm bg-indigo-50" />
                          <div className="h-5 rounded-sm bg-emerald-50" />
                          <div className="h-5 rounded-sm bg-slate-100" />
                        </div>
                      </div>
                    )}
                  </div>
                </button>

                <div className="space-y-3 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="rounded-md bg-indigo-50 px-2 py-1 text-[10px] font-bold uppercase text-indigo-700">
                      {rep.report_type || "DOCUMENT"}
                    </span>
                    <span className="flex shrink-0 items-center gap-1 text-[10px] text-slate-400">
                      <Clock className="h-3 w-3" />
                      {formatDate(rep.created_at)}
                    </span>
                  </div>

                  <button type="button" onClick={() => openReportPreview(rep)} className="block w-full text-left">
                    <h4 className="line-clamp-2 min-h-9 text-xs font-bold leading-relaxed text-slate-900">{preview.title}</h4>
                    <p className="mt-1 text-[11px] text-slate-500">
                      {preview.sectionCount || 0} mục · {preview.wordCount || 0} từ
                    </p>
                  </button>

                  <div className="flex items-center justify-between border-t border-slate-100 pt-3">
                    <button
                      type="button"
                      onClick={() => openReportPreview(rep)}
                      className="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-600 hover:text-indigo-700"
                    >
                      <span>Xem trước</span>
                      <ArrowRight className="h-3 w-3" />
                    </button>
                    <Link
                      href={`/reports/${rep.id}/editor`}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-bold text-slate-700 hover:border-indigo-200 hover:text-indigo-700"
                    >
                      <Edit3 className="h-3 w-3" />
                      <span>Sửa</span>
                    </Link>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <PreviewModal
        isOpen={!!previewReport}
        onClose={() => setPreviewReport(null)}
        title={previewReport?.title || "Xem trước tài liệu"}
        subtitle={previewReport?.report_type}
        footer={
          <>
            <button
              type="button"
              onClick={() => setPreviewReport(null)}
              className="rounded-lg px-3 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100"
            >
              Đóng
            </button>
            {previewReport && (
              <Link
                href={`/reports/${previewReport.id}/editor`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-bold text-white hover:bg-indigo-700"
              >
                <ArrowRight className="h-3.5 w-3.5" />
                <span>Mở trong Studio</span>
              </Link>
            )}
          </>
        }
      >
        {previewLoading ? (
          <div className="h-52 rounded-xl bg-slate-100 animate-pulse" />
        ) : (
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-xl border border-slate-200 p-3">
                <div className="text-slate-400">Số từ</div>
                <div className="mt-1 font-bold text-slate-900">{previewReport?.total_words || 0}</div>
              </div>
              <div className="rounded-xl border border-slate-200 p-3">
                <div className="text-slate-400">Nguồn</div>
                <div className="mt-1 font-bold text-slate-900">{previewReport?.sources_count || 0}</div>
              </div>
              <div className="rounded-xl border border-slate-200 p-3">
                <div className="text-slate-400">Cập nhật</div>
                <div className="mt-1 font-bold text-slate-900">{previewReport?.updated_at ? formatDate(previewReport.updated_at) : "-"}</div>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200">
              <div className="border-b border-slate-100 px-4 py-3 font-bold text-slate-900">Nội dung bên trong</div>
              <div className="max-h-[46vh] overflow-y-auto p-4 space-y-4">
                {(previewReport?.sections || []).length === 0 ? (
                  <p className="text-slate-500">Tài liệu này chưa có nội dung chi tiết.</p>
                ) : (
                  previewReport.sections.map((section: any) => (
                    <section key={section.id} className="space-y-1">
                      <h3 className="font-bold text-slate-900">{section.title}</h3>
                      <p className="whitespace-pre-wrap leading-relaxed text-slate-600">
                        {section.plain_text || "Mục này chưa có nội dung."}
                      </p>
                    </section>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </PreviewModal>
    </div>
  );
}
