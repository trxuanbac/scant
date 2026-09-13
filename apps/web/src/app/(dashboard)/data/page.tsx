"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowRight, BarChart2, Database, FileSpreadsheet, GitCompare, Layers3, RefreshCw, Search, Table, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { formatUnknownError } from "@/lib/apiErrors";
import { PreviewModal } from "@/components/PreviewModal";
import SpreadsheetPreview, { type VisualWorkbook } from "@/components/SpreadsheetPreview";
import { datasetComparison, filterDatasetGroups, groupDatasetsForDisplay } from "@/lib/datasetGroups";
import { dataAnalysisUrl } from "@/lib/dataAnalysisNavigation";

interface DatasetColumn { name: string; type?: string; unique_count?: number }
interface DatasetSheet {
  name: string;
  columns?: DatasetColumn[];
  statistics?: { missing_values_count?: number; duplicate_rows_count?: number };
}
interface VerifiedFact { id: string; fact: string; value?: unknown }
interface DatasetProfile {
  total_rows?: number;
  total_columns?: number;
  sheet_count?: number;
  columns?: DatasetColumn[];
  sheets?: DatasetSheet[];
  verified_facts?: VerifiedFact[];
  warnings?: string[];
  visual_workbook?: VisualWorkbook;
}
interface DatasetFile {
  id: string;
  original_name: string;
  file_type?: string;
  file_size?: number;
  file_hash?: string;
  created_at?: string;
  metadata_json?: {
    dataset_profile?: DatasetProfile;
    dataset_comparison?: { schema_signature?: string; similarity_score?: number; [key: string]: unknown };
  };
}
interface DatasetGroup { id: string; primary: DatasetFile; variants: DatasetFile[]; hiddenDuplicateCount: number; status: string }

function isDataset(file: DatasetFile) {
  const name = (file.original_name || "").toLowerCase();
  return ["excel", "csv", "xlsx", "xls"].includes(file.file_type || "")
    || [".csv", ".xlsx", ".xls", ".xlsm"].some((extension) => name.endsWith(extension));
}

function fileSize(size?: number) {
  if (!Number.isFinite(size) || !size || size < 0) return "Không rõ dung lượng";
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  return `${(size / 1024).toFixed(1)} KB`;
}

function profileQuality(profile?: DatasetProfile) {
  const sheets = Array.isArray(profile?.sheets) ? profile.sheets : [];
  return {
    missing: sheets.reduce((sum, sheet) => sum + Number(sheet.statistics?.missing_values_count || 0), 0),
    duplicates: sheets.reduce((sum, sheet) => sum + Number(sheet.statistics?.duplicate_rows_count || 0), 0),
    warnings: Array.isArray(profile?.warnings) ? profile.warnings.length : 0,
  };
}

function analysisHref(datasetId: string) {
  return dataAnalysisUrl("mode=auto&type=data_analysis&workflow=data", { analysis: "direct-analysis", dataset: datasetId });
}

export default function DataWorkspacePage() {
  const [datasets, setDatasets] = useState<DatasetFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [previewDataset, setPreviewDataset] = useState<DatasetFile | null>(null);
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [activeSheet, setActiveSheet] = useState(0);

  const loadData = useCallback(async () => {
    setLoading(true);
    setListError("");
    try {
      const files = await api.files.list();
      setDatasets((Array.isArray(files) ? files : []).filter(isDataset));
    } catch (error) {
      setListError(formatUnknownError(error, "Không thể tải thư viện dữ liệu."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadData(); }, [loadData]);

  const openDatasetPreview = useCallback(async (dataset: DatasetFile) => {
    setPreviewDataset(dataset);
    setProfile(null);
    setPreviewError("");
    setActiveSheet(0);
    setPreviewLoading(true);
    try {
      setProfile(await api.data.profile(dataset.id));
    } catch (error) {
      setPreviewError(formatUnknownError(error, "Không thể đọc bản xem trước dữ liệu."));
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  const datasetGroups = useMemo(() => groupDatasetsForDisplay(datasets) as DatasetGroup[], [datasets]);
  const visibleGroups = useMemo(() => filterDatasetGroups(datasetGroups, searchQuery) as DatasetGroup[], [datasetGroups, searchQuery]);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">Dữ liệu đã lưu</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">Không gian dữ liệu</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">Chọn đúng bảng tính, kiểm tra chất lượng và tiếp tục phân tích mà không cần tải lại.</p>
        </div>
        <Link href="/projects/new?mode=auto&type=data_analysis&workflow=data" className="inline-flex items-center justify-center gap-2 rounded-md bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2">
          <Upload className="h-4 w-4" />Thêm dữ liệu
        </Link>
      </header>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div className="flex flex-col gap-3 border-b border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-indigo-50 text-indigo-700"><Database className="h-4 w-4" /></span>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-slate-900">Thư viện bảng tính</h2>
              <p className="text-xs text-slate-500" aria-live="polite">{datasetGroups.length} nhóm · {datasets.length} tệp</p>
            </div>
          </div>
          <div className="relative w-full sm:max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input aria-label="Tìm tập dữ liệu" type="search" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Tìm theo tên tệp…" className="h-9 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus-visible:ring-2 focus-visible:ring-indigo-500" />
          </div>
        </div>

        <div className="p-3 sm:p-4">
          {loading ? (
            <div className="space-y-2" aria-label="Đang tải tập dữ liệu" aria-live="polite">
              {[0, 1, 2].map((item) => <div key={item} className="flex min-h-20 animate-pulse items-center gap-3 rounded-lg border border-slate-100 px-4 py-3"><div className="h-9 w-9 rounded-md bg-slate-100" /><div className="flex-1 space-y-2"><div className="h-3 w-2/5 rounded bg-slate-100" /><div className="h-3 w-3/5 rounded bg-slate-100" /></div></div>)}
            </div>
          ) : listError ? (
            <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 sm:flex-row sm:items-center">
              <AlertCircle className="h-5 w-5 shrink-0 text-red-600" />
              <div className="min-w-0 flex-1"><h3 className="text-sm font-semibold text-red-900">Không thể tải thư viện dữ liệu</h3><p className="mt-1 break-words text-xs text-red-700">{listError}</p></div>
              <button type="button" onClick={() => void loadData()} className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-2 text-xs font-medium text-red-800 hover:bg-red-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"><RefreshCw className="h-3.5 w-3.5" />Thử lại</button>
            </div>
          ) : datasetGroups.length === 0 ? (
            <div className="flex min-h-56 flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 px-5 py-8 text-center">
              <FileSpreadsheet className="h-7 w-7 text-slate-400" />
              <h3 className="mt-3 text-sm font-semibold text-slate-900">Chưa có tập dữ liệu CSV/Excel nào</h3>
              <p className="mt-1 max-w-md text-xs leading-5 text-slate-500">Tải XLSX, XLSM, XLS hoặc CSV để xem trước và phân tích số liệu.</p>
              <Link href="/projects/new?mode=auto&type=data_analysis&workflow=data" className="mt-4 rounded-md bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">Thêm dữ liệu đầu tiên</Link>
            </div>
          ) : visibleGroups.length === 0 ? (
            <div className="flex min-h-48 flex-col items-center justify-center px-5 py-8 text-center">
              <Search className="h-6 w-6 text-slate-400" />
              <h3 className="mt-3 text-sm font-semibold text-slate-900">Không tìm thấy tập dữ liệu phù hợp</h3>
              <p className="mt-1 text-xs text-slate-500">Không có tên tệp nào khớp “{searchQuery.trim()}”.</p>
              <button type="button" onClick={() => setSearchQuery("")} className="mt-3 rounded-md border border-slate-200 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">Xóa tìm kiếm</button>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {visibleGroups.map((group) => {
                const d = group.primary;
                const comparison = datasetComparison(d);
                const summary = d.metadata_json?.dataset_profile;
                const quality = profileQuality(summary);
                return (
                  <article key={group.id} className="py-3 first:pt-0 last:pb-0">
                    <div className="flex flex-col gap-3 rounded-lg px-2 py-2 transition hover:bg-slate-50 sm:flex-row sm:items-center">
                      <button type="button" onClick={() => void openDatasetPreview(d)} className="flex min-w-0 flex-1 items-start gap-3 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">
                        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-slate-200 bg-white text-indigo-600"><FileSpreadsheet className="h-4 w-4" /></span>
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-1.5">
                            <span className="max-w-full truncate text-sm font-semibold text-slate-900">{d.original_name}</span>
                            {group.hiddenDuplicateCount > 0 && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">Ẩn {group.hiddenDuplicateCount} bản trùng</span>}
                            {!group.hiddenDuplicateCount && group.variants.length > 0 && <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">{group.variants.length} bản tương tự</span>}
                            {(quality.missing > 0 || quality.duplicates > 0 || quality.warnings > 0) ? <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">Cần kiểm tra</span> : summary ? <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">Đã lập hồ sơ</span> : null}
                          </span>
                          <span className="mt-1 block text-xs text-slate-500">{fileSize(d.file_size)}{summary?.total_rows != null ? ` · ${summary.total_rows} dòng` : ""}{summary?.total_columns != null ? ` · ${summary.total_columns} cột` : ""}{summary?.sheet_count != null ? ` · ${summary.sheet_count} sheet` : ""}</span>
                          {(quality.missing > 0 || quality.duplicates > 0) && <span className="mt-1 block text-[11px] text-amber-700">{quality.missing} ô thiếu · {quality.duplicates} dòng trùng</span>}
                        </span>
                      </button>
                      <div className="flex shrink-0 gap-2 pl-12 sm:pl-0">
                        <button type="button" onClick={() => void openDatasetPreview(d)} className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">Xem trước</button>
                        <Link href={dataAnalysisUrl("mode=auto&type=data_analysis&workflow=data", { analysis: "direct-analysis", dataset: d.id })} className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2">Phân tích<ArrowRight className="h-3.5 w-3.5" /></Link>
                      </div>
                    </div>
                    {group.variants.length > 0 && !group.hiddenDuplicateCount && <VariantList variants={group.variants} onPreview={openDatasetPreview} />}
                    {group.hiddenDuplicateCount > 0 && <p className="ml-14 mt-1 flex items-center gap-1.5 text-[11px] text-slate-500"><Layers3 className="h-3.5 w-3.5" />Chỉ dùng bản chính để tránh phân tích lặp.</p>}
                    {comparison?.schema_signature && <span className="sr-only">Đã lập dấu vân tay dữ liệu</span>}
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </section>

      <PreviewModal isOpen={Boolean(previewDataset)} onClose={() => setPreviewDataset(null)} title={previewDataset?.original_name || "Xem trước dữ liệu"} subtitle={previewDataset ? fileSize(previewDataset.file_size) : undefined} footer={<><button type="button" onClick={() => setPreviewDataset(null)} className="rounded-md px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">Đóng</button>{previewDataset && <Link href={analysisHref(previewDataset.id)} className="rounded-md bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">Mở workspace phân tích</Link>}</>}>
        {previewLoading ? <div className="space-y-3" aria-label="Đang tải bản xem trước" aria-live="polite"><div className="h-20 animate-pulse rounded-lg bg-slate-100" /><div className="h-72 animate-pulse rounded-lg bg-slate-100" /></div> : previewError ? (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4"><div className="flex items-start gap-2"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" /><div><h3 className="text-sm font-semibold text-red-900">Không thể tải bản xem trước</h3><p className="mt-1 break-words text-xs text-red-700">{previewError}</p></div></div><button type="button" disabled={!previewDataset} onClick={() => previewDataset && void openDatasetPreview(previewDataset)} className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-2 text-xs font-medium text-red-800 hover:bg-red-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:opacity-50"><RefreshCw className="h-3.5 w-3.5" />Tải lại bản xem trước</button></div>
        ) : profile ? <DatasetPreview profile={profile} activeSheet={activeSheet} onSelectSheet={setActiveSheet} /> : null}
      </PreviewModal>
    </div>
  );
}

function VariantList({ variants, onPreview }: { variants: DatasetFile[]; onPreview: (dataset: DatasetFile) => Promise<void> }) {
  return <details className="ml-14 mt-1 rounded-md border border-slate-200 bg-white text-xs"><summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 font-medium text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"><GitCompare className="h-3.5 w-3.5 text-amber-600" />Xem {variants.length} bản tương tự</summary><div className="divide-y divide-slate-100 border-t border-slate-100">{variants.map((variant) => { const score = Math.round(Number(datasetComparison(variant).similarity_score || 0) * 100); return <div key={variant.id} className="flex items-center justify-between gap-3 px-3 py-2"><button type="button" onClick={() => void onPreview(variant)} className="min-w-0 truncate text-left font-medium text-slate-700 hover:text-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">{variant.original_name}</button><span className="shrink-0 text-[11px] text-slate-500">Giống {score || "—"}%</span></div>; })}</div></details>;
}

function DatasetPreview({ profile, activeSheet, onSelectSheet }: { profile: DatasetProfile; activeSheet: number; onSelectSheet: (index: number) => void }) {
  const sheets = Array.isArray(profile.sheets) ? profile.sheets : [];
  const sheet = sheets[activeSheet] || sheets[0] || {};
  const columns = Array.isArray(sheet.columns) ? sheet.columns : Array.isArray(profile.columns) ? profile.columns : [];
  const facts = Array.isArray(profile.verified_facts) ? profile.verified_facts : [];
  const quality = profileQuality(profile);
  return <div className="space-y-4 text-xs">
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-slate-200 bg-slate-200 sm:grid-cols-4">{[["Số dòng", profile.total_rows ?? "—"], ["Số cột", profile.total_columns ?? "—"], ["Số sheet", profile.sheet_count ?? sheets.length], ["Thiếu / trùng", `${quality.missing} / ${quality.duplicates}`]].map(([label, value]) => <div key={label} className="bg-white p-3"><p className="text-slate-500">{label}</p><p className="mt-1 text-base font-semibold text-slate-900">{value}</p></div>)}</div>
    {sheets.length > 1 && <div className="flex gap-1.5 overflow-x-auto pb-1" aria-label="Chọn sheet">{sheets.map((item, index) => <button key={item.name || index} type="button" onClick={() => onSelectSheet(index)} className={`shrink-0 rounded-md px-3 py-2 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${activeSheet === index ? "bg-indigo-600 text-white" : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"}`}>{item.name || `Sheet ${index + 1}`}</button>)}</div>}
    {facts.length > 0 && <section className="overflow-hidden rounded-lg border border-indigo-100"><h3 className="flex items-center gap-2 border-b border-indigo-100 bg-indigo-50 px-3 py-2.5 font-semibold text-indigo-950"><BarChart2 className="h-4 w-4" />Số liệu đã kiểm chứng</h3><div className="max-h-48 divide-y divide-slate-100 overflow-y-auto">{facts.slice(0, 18).map((fact) => <div key={fact.id} className="grid grid-cols-[64px_minmax(0,1fr)] gap-2 px-3 py-2 sm:grid-cols-[64px_minmax(0,1fr)_minmax(100px,1fr)]"><span className="font-mono font-medium text-indigo-700">{fact.id}</span><span className="font-medium text-slate-800">{fact.fact}</span><span className="col-start-2 break-words text-slate-500 sm:col-start-auto">{typeof fact.value === "object" ? JSON.stringify(fact.value) : String(fact.value ?? "—")}</span></div>)}</div></section>}
    <section className="overflow-hidden rounded-lg border border-slate-200"><h3 className="border-b border-slate-100 px-3 py-2.5 font-semibold text-slate-900">Cột dữ liệu{sheet.name ? ` · ${sheet.name}` : ""}</h3><div className="max-h-40 divide-y divide-slate-100 overflow-y-auto">{columns.length ? columns.map((column) => <div key={column.name} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_100px_100px]"><span className="truncate font-medium text-slate-800">{column.name}</span><span className="text-slate-500">{column.type || "—"}</span><span className="col-start-1 text-slate-400 sm:col-start-auto">{column.unique_count ?? "—"} giá trị</span></div>) : <p className="px-3 py-4 text-slate-500">Chưa có thông tin cột.</p>}</div></section>
    <section className="overflow-hidden rounded-lg border border-slate-200"><h3 className="flex items-center gap-2 border-b border-slate-100 px-3 py-2.5 font-semibold text-slate-900"><Table className="h-4 w-4" />Bản xem trước bảng tính</h3><div className="overflow-x-auto p-2"><SpreadsheetPreview workbook={profile.visual_workbook} legacyData={profile} height={420} /></div></section>
  </div>;
}
