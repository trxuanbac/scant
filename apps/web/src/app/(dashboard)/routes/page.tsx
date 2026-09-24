"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Download,
  ExternalLink,
  FileSpreadsheet,
  Info,
  Loader2,
  MapPinned,
  Route,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";

import { api } from "@/lib/api";
import { formatUnknownError } from "@/lib/apiErrors";

type Result = {
  url: string; filename: string; total: number; completed: number; missingWaypoint: number;
  mapsFailed: number; roundTrips: number; largeDifference: number; missingLinks: number; validationFailed: number;
};

function isLookerReport(value: string) {
  try {
    const host = new URL(value).hostname.toLowerCase();
    return host === "datastudio.google.com" || host === "lookerstudio.google.com";
  } catch {
    return false;
  }
}

function formatSize(size: number) {
  return size >= 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`;
}

export default function RouteEnrichmentPage() {
  const [file, setFile] = useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [mapsConfigured, setMapsConfigured] = useState<boolean | null>(null);
  const [supportedLookerReportId, setSupportedLookerReportId] = useState("");
  const [statusError, setStatusError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const resultUrlRef = useRef<string | null>(null);
  const looker = useMemo(() => isLookerReport(sourceUrl), [sourceUrl]);
  const mappedLooker = useMemo(() => {
    if (!looker || !supportedLookerReportId) return false;
    try {
      const parts = new URL(sourceUrl).pathname.split("/").filter(Boolean);
      const reportPosition = parts.indexOf("reporting");
      return reportPosition >= 0 && parts[reportPosition + 1] === supportedLookerReportId;
    } catch {
      return false;
    }
  }, [looker, sourceUrl, supportedLookerReportId]);

  useEffect(() => {
    let active = true;
    void api.routes.status().then((status) => {
      if (active) {
        setMapsConfigured(status.maps_configured);
        setSupportedLookerReportId(status.supported_looker_report_id || "");
      }
    }).catch((caught) => {
      if (active) setStatusError(formatUnknownError(caught, "Không thể kiểm tra dịch vụ đo km."));
    });
    return () => {
      active = false;
      if (resultUrlRef.current) URL.revokeObjectURL(resultUrlRef.current);
    };
  }, []);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!file || !file.name.toLowerCase().endsWith(".xlsx")) {
      setError("Hãy chọn file Excel .xlsx chứa cột Kho đi và Lộ trình.");
      return;
    }
    try {
      if (new URL(sourceUrl).protocol !== "https:") throw new Error();
    } catch {
      setError("Hãy dán link nguồn HTTPS hợp lệ.");
      return;
    }
    if (looker && !mappedLooker && !referenceFile) {
      setError("Link Looker cần thêm bảng tọa độ HUB xuất ra CSV/XLSX, hoặc dùng link Google Sheet gốc.");
      return;
    }
    if (mapsConfigured === false) {
      setError("Máy chủ chưa cấu hình Google Maps Routes API. Cần bật dịch vụ trước khi đo km.");
      return;
    }
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("source_url", sourceUrl.trim());
      if (looker && !mappedLooker && referenceFile) formData.append("reference_file", referenceFile);
      const exported = await api.routes.export(formData);
      if (resultUrlRef.current) URL.revokeObjectURL(resultUrlRef.current);
      const url = URL.createObjectURL(exported.blob);
      resultUrlRef.current = url;
      const filename = "Lo_trinh_Google_Maps_da_kiem_tra.xlsx";
      setResult({ url, filename, ...exported });
      const download = document.createElement("a");
      download.href = url;
      download.download = filename;
      document.body.append(download);
      download.click();
      download.remove();
    } catch (caught) {
      setError(formatUnknownError(caught, "Không thể tạo bản sao lộ trình."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 pb-10">
      <header className="flex flex-col justify-between gap-5 border-b border-slate-200 pb-6 lg:flex-row lg:items-end dark:border-slate-800">
        <div className="max-w-3xl">
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600 dark:text-indigo-300">DỮ LIỆU / LỘ TRÌNH</p>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-950 dark:text-white sm:text-4xl">Đo lộ trình từ Excel</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-400">
            Ghép Kho đi với toàn bộ Lộ trình theo đúng thứ tự, kể cả điểm quay về kho. Google Routes đo tổng km của mọi chặng và tạo bản sao Excel có bảng đối chiếu chi tiết.
          </p>
        </div>
        <Link href="/data" className="inline-flex h-9 shrink-0 items-center gap-2 self-start rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800">
          <FileSpreadsheet className="h-4 w-4" /> Thư viện dữ liệu <ArrowRight className="h-4 w-4" />
        </Link>
      </header>

      {mapsConfigured === false && (
        <div role="alert" className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>Máy chủ chưa bật Google Maps Routes API. Quản trị viên cần cấu hình <code className="rounded bg-amber-100 px-1 dark:bg-amber-900">GOOGLE_MAPS_ROUTES_API_KEY</code> để hệ thống đo km tự động.</p>
        </div>
      )}
      {statusError && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{statusError}</div>}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.55fr)_minmax(290px,0.9fr)]">
        <form onSubmit={handleSubmit} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-800 sm:px-7">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300"><Route className="h-5 w-5" /></span>
              <div><h2 className="text-base font-semibold text-slate-950 dark:text-white">Tạo bản sao đã đo</h2><p className="text-xs text-slate-500 dark:text-slate-400">File gốc của bạn được giữ nguyên.</p></div>
            </div>
            <span className="hidden rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-500 sm:block dark:border-slate-700">Excel .xlsx</span>
          </div>

          <div className="space-y-6 p-5 sm:p-7">
            <div>
              <label htmlFor="route-workbook" className="mb-2 block text-sm font-semibold text-slate-900 dark:text-slate-100">1. File Excel lộ trình</label>
              <label htmlFor="route-workbook" className="flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50/70 p-5 text-center transition hover:border-indigo-400 hover:bg-indigo-50/40 dark:border-slate-700 dark:bg-slate-950/40 dark:hover:border-indigo-500">
                {file ? <FileSpreadsheet className="h-7 w-7 text-emerald-600" /> : <UploadCloud className="h-7 w-7 text-slate-400" />}
                <span className="mt-2 max-w-full truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{file ? file.name : "Chọn file .xlsx từ máy"}</span>
                <span className="mt-1 text-xs text-slate-500">{file ? formatSize(file.size) : "Tối đa 20 MB · giữ nguyên định dạng và các sheet khác"}</span>
              </label>
              <input id="route-workbook" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="sr-only" onChange={(event) => { setFile(event.target.files?.[0] || null); setResult(null); }} />
            </div>

            <div>
              <label htmlFor="route-source" className="mb-2 block text-sm font-semibold text-slate-900 dark:text-slate-100">2. Link nguồn HUB / báo cáo Looker</label>
              <div className="relative">
                <MapPinned className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-slate-400" />
                <input id="route-source" type="url" required value={sourceUrl} onChange={(event) => { setSourceUrl(event.target.value); setResult(null); }} placeholder="https://docs.google.com/spreadsheets/... hoặc link Looker Studio" className="h-11 w-full rounded-lg border border-slate-300 bg-white pl-10 pr-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 dark:border-slate-700 dark:bg-slate-950 dark:text-white dark:focus:ring-indigo-900" />
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">Link Google Sheet/CSV công khai cần Tên HUB + vĩ độ/kinh độ, hoặc Hub seller + Định vị Google Maps. Link Looker cần thêm bảng HUB xuất từ báo cáo.</p>
            </div>

            {looker && mappedLooker && (
              <div className="flex items-start gap-2.5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> Báo cáo Looker này đã được kết nối với bảng tọa độ HUB. Bạn chỉ cần Excel và link báo cáo.</div>
            )}

            {looker && !mappedLooker && (
              <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 p-4 dark:border-indigo-900 dark:bg-indigo-950/30">
                <div className="flex items-start gap-2.5"><Info className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600 dark:text-indigo-300" /><div><h3 className="text-sm font-semibold text-indigo-950 dark:text-indigo-100">Bổ sung bảng HUB từ Looker</h3><p className="mt-1 text-xs leading-5 text-indigo-800 dark:text-indigo-200">Trong báo cáo, xuất biểu đồ “TỈNH ⇒ Tra cứu địa chỉ các HUB” ra CSV (Microsoft Excel). Hệ thống đọc cột “Hub seller” và “Định vị” có link ghim tọa độ Google Maps.</p></div></div>
                <label htmlFor="route-reference" className="mt-3 flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-indigo-200 bg-white px-3 py-2.5 text-sm font-medium text-indigo-900 hover:bg-indigo-50 dark:border-indigo-800 dark:bg-slate-900 dark:text-indigo-100">
                  <span className="min-w-0 truncate">{referenceFile ? referenceFile.name : "Chọn CSV/XLSX xuất từ bảng HUB"}</span><UploadCloud className="h-4 w-4 shrink-0" />
                </label>
                <input id="route-reference" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="sr-only" onChange={(event) => setReferenceFile(event.target.files?.[0] || null)} />
              </div>
            )}

            {error && <div role="alert" className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
            <button type="submit" disabled={submitting || mapsConfigured === false} className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50">
              {submitting ? <><Loader2 className="h-4 w-4 animate-spin" /> Đang kiểm tra và đo lộ trình...</> : <><Route className="h-4 w-4" /> Tạo bản sao Excel <ArrowRight className="h-4 w-4" /></>}
            </button>
          </div>
        </form>

        <aside className="space-y-5">
          <section className="rounded-2xl border border-slate-200 bg-slate-950 p-5 text-white shadow-sm dark:border-slate-800 sm:p-6">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10"><ShieldCheck className="h-5 w-5 text-indigo-200" /></div>
            <h2 className="mt-4 text-lg font-semibold">Đo đúng, có thể đối chiếu</h2>
            <p className="mt-2 text-sm leading-6 text-slate-300">Mỗi điểm dừng phải có tọa độ trong nguồn HUB. Số km lấy từ tuyến ô tô Google Routes; link trong Excel mở đúng thứ tự điểm dừng.</p>
            <div className="mt-5 space-y-3 border-t border-white/10 pt-5 text-sm text-slate-200">
              <p className="flex gap-2.5"><span className="font-semibold text-indigo-300">01</span> Giữ nguyên điểm cuối, kể cả khi xe quay về kho đi.</p>
              <p className="flex gap-2.5"><span className="font-semibold text-indigo-300">02</span> Chỉ bỏ điểm trùng liền kề; không đổi thứ tự.</p>
              <p className="flex gap-2.5"><span className="font-semibold text-indigo-300">03</span> Đo lại mọi dòng; km và link cũ nằm trong sheet đối chiếu.</p>
            </div>
          </section>

          {result ? (
            <section aria-live="polite" className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5 dark:border-emerald-900 dark:bg-emerald-950/30 sm:p-6">
              <div className="flex items-center gap-2 text-emerald-800 dark:text-emerald-200"><CheckCircle2 className="h-5 w-5" /><h2 className="text-base font-semibold">Đã tạo bản sao Excel</h2></div>
              <div className="mt-4 grid grid-cols-2 gap-2 text-center sm:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4">
                <Metric value={result.total} label="Tổng tuyến" /><Metric value={result.completed} label="Đã đo đủ" />
                <Metric value={result.missingWaypoint} label="Lỗi waypoint" /><Metric value={result.mapsFailed} label="Lỗi Maps" />
                <Metric value={result.roundTrips} label="Khứ hồi" /><Metric value={result.largeDifference} label="Chênh ≥10%" />
                <Metric value={result.missingLinks} label="Thiếu link" /><Metric value={result.validationFailed} label="Sai validation" />
              </div>
              {(result.missingWaypoint > 0 || result.mapsFailed > 0) && <p className="mt-3 text-xs leading-5 text-emerald-900 dark:text-emerald-200">Mở sheet “Doi chieu lo trinh” để xem từng dòng lỗi và waypoint cần xác minh. Dòng chưa đo đủ không có km Google mới.</p>}
              <a href={result.url} download={result.filename} className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800"><Download className="h-4 w-4" /> Tải lại bản sao</a>
            </section>
          ) : (
            <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900 sm:p-6">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Bảng nguồn cần có gì?</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-400">Chấp nhận <strong>Tên HUB + Vĩ độ + Kinh độ</strong> hoặc <strong>Hub seller + Định vị</strong> có link Google Maps ghim tọa độ. Tên HUB cần khớp với “Kho đi” và từng điểm trong “Lộ trình”.</p>
              <a href="https://cloud.google.com/looker/docs/studio/export-data-from-a-chart" target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">Cách xuất dữ liệu từ Looker <ExternalLink className="h-3.5 w-3.5" /></a>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}

function Metric({ value, label }: { value: number; label: string }) {
  return <div className="rounded-lg border border-emerald-200 bg-white/70 px-2 py-2.5 dark:border-emerald-900 dark:bg-slate-900/50"><strong className="block text-lg tabular-nums text-emerald-950 dark:text-emerald-100">{value}</strong><span className="text-[11px] text-emerald-800 dark:text-emerald-300">{label}</span></div>;
}
