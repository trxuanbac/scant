"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "@/lib/api";
import { useAuthStore } from "@/stores/useAuthStore";
import { SpreadsheetActionCard } from "./SpreadsheetActionCard";

type Layer = { id: string; type: "HIGHLIGHT_CELLS" | "CLEAR_HIGHLIGHTS"; sheet: string; cells: string[]; color: string; label?: string };
type Entry = { id: string; status: string; action: Layer; source_hash: string; preview: { cell: string; value: unknown; after_color: string }[]; applied_at: string | null };
type History = { items: Entry[]; layers: Layer[]; revision: string; has_state: boolean; undo_id: string | null };
type Ledger = { enabled: boolean; prepare: (action: Omit<Layer, "id">) => Promise<Entry>; confirm: (id: string) => Promise<void>; cancel: (id: string) => Promise<void>; refresh: () => Promise<void> };
const Context = createContext<Ledger | null>(null);

export function WorkbookLedger({ file, fileId, dataSourceUrl, locale, onRestore, children }: {
  file?: File | null; fileId?: string | null; dataSourceUrl?: string | null; locale: string;
  onRestore: (layers: Layer[]) => void; children: ReactNode;
}) {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);
  const supported = !file || /\.(xlsx|xlsm)$/i.test(file.name);
  const enabled = !!userId && supported && !!(file || fileId || dataSourceUrl);
  const sourceKey = fileId || dataSourceUrl || file?.name || "";
  const [error, setError] = useState("");
  const [undoing, setUndoing] = useState(false);
  const restore = useRef(onRestore);
  useEffect(() => { restore.current = onRestore; }, [onRestore]);
  function sourceForm() {
    const form = new FormData();
    if (fileId) form.append("file_id", fileId);
    else if (file) form.append("file", file);
    else if (dataSourceUrl) form.append("data_source_url", dataSourceUrl);
    return form;
  }
  const version = useQuery({
    queryKey: ["workbook-version", userId, sourceKey, file?.size, file?.lastModified],
    queryFn: () => request<{ source_hash: string }>("/data/workbook-actions/source", { method: "POST", body: sourceForm() }),
    enabled, retry: false, staleTime: 0,
  });
  const history = useQuery({
    queryKey: ["workbook-ledger", userId, sourceKey, version.data?.source_hash],
    queryFn: () => request<History>(`/data/workbook-actions/history?${new URLSearchParams({ source_key: sourceKey, source_hash: version.data!.source_hash })}`),
    enabled: enabled && !!version.data, retry: false, staleTime: 0,
  });
  useEffect(() => {
    if (history.data?.has_state) restore.current(history.data.layers);
  }, [history.data]);
  const value: Ledger = {
    enabled,
    async prepare(action) {
      const form = sourceForm(); form.append("source_key", sourceKey); form.append("action", JSON.stringify(action));
      const entry = await request<Entry>("/data/workbook-actions/preview", { method: "POST", body: form });
      queryClient.setQueryData(["workbook-version", userId, sourceKey, file?.size, file?.lastModified], { source_hash: entry.source_hash });
      return entry;
    },
    async confirm(id) {
      await request(`/data/workbook-actions/${id}/confirm`, { method: "POST", body: sourceForm() });
    },
    async refresh() {
      const refreshed = await history.refetch();
      if (refreshed.error) throw refreshed.error;
      if (refreshed.data) restore.current(refreshed.data.layers);
    },
    async cancel(id) {
      await request(`/data/workbook-actions/${id}/cancel`, { method: "POST" });
      await history.refetch();
    },
  };
  async function undo() {
    const actionId = history.data?.undo_id;
    if (!actionId || undoing) return;
    setUndoing(true); setError("");
    try {
      await request(`/data/workbook-actions/${actionId}/undo`, { method: "POST" });
      const refreshed = await history.refetch();
      if (refreshed.error) throw refreshed.error;
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể hoàn tác."); }
    finally { setUndoing(false); }
  }
  return <Context.Provider value={value}>
    {enabled && <div className="mb-2 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600" aria-live="polite">
      <span className="inline-flex items-center gap-1.5 font-medium text-slate-700"><span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true" />{locale === "vi" ? "Lớp màu đã lưu" : "Saved highlight layers"}<strong className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-900">{history.data?.items.length ?? 0}</strong></span>
      <details className="relative">
        <summary className="cursor-pointer list-none rounded-md border border-slate-200 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500">{locale === "vi" ? "Lịch sử thao tác" : "Action history"}</summary>
        <div className="absolute left-0 top-9 z-30 max-h-80 w-[min(32rem,85vw)] space-y-2 overflow-auto rounded-lg border border-slate-200 bg-white p-3 shadow-lg">
          {history.data?.items.map((item) => item.status === "pending" ? <PersistentSpreadsheetActionCard key={item.id} savedEntry={item} label={item.action.label || item.action.type} sheet={item.action.sheet} cells={item.action.cells} color={item.action.color} clear={item.action.type === "CLEAR_HIGHLIGHTS"} locale={locale} onConfirm={() => {}} /> : <p key={item.id} className="break-words">{item.action.sheet} · {item.action.label || item.action.type} · {locale === "vi" ? ({ applied: "Đã áp dụng", cancelled: "Đã hủy", undone: "Đã hoàn tác" }[item.status] || item.status) : item.status}</p>)}
          {!history.data?.items.length && <p>{locale === "vi" ? "Chưa có hành động đã lưu cho phiên bản workbook này." : "No saved actions for this workbook version."}</p>}
        </div>
      </details>
      <button type="button" onClick={undo} disabled={undoing || !history.data?.undo_id} className="rounded-md border border-slate-200 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:cursor-not-allowed disabled:opacity-40">{undoing ? (locale === "vi" ? "Đang hoàn tác…" : "Undoing…") : (locale === "vi" ? "Hoàn tác lớp gần nhất" : "Undo latest layer")}</button>
      {(error || version.error || history.error) && <span role="alert" className="text-red-700">{error || "Chưa tải được lịch sử đã lưu. Hãy thử lại."}</span>}
      {(version.error || history.error) && <button type="button" onClick={() => { void version.refetch(); void history.refetch(); }} className="underline">{locale === "vi" ? "Thử lại" : "Retry"}</button>}
    </div>}
    {children}
  </Context.Provider>;
}

export function PersistentSpreadsheetActionCard(props: React.ComponentProps<typeof SpreadsheetActionCard> & { savedEntry?: Entry }) {
  const ledger = useContext(Context);
  const [entry, setEntry] = useState<Entry | null>(props.savedEntry || null);
  const [status, setStatus] = useState<"idle" | "loading" | "preview" | "applied" | "cancelled">(props.savedEntry ? "preview" : "idle");
  const [error, setError] = useState("");
  const target = JSON.stringify({ sheet: props.sheet, cells: props.cells, color: props.color, clear: props.clear });
  const reviewed = useRef(props.savedEntry ? target : "");
  const busy = useRef(false);
  if (!ledger?.enabled) return <SpreadsheetActionCard {...props} />;
  const vi = props.locale === "vi";
  async function perform(action: "preview" | "confirm" | "cancel") {
    if (busy.current) return;
    busy.current = true; setError("");
    try {
      if (action === "preview") {
        setStatus("loading");
        const item = await ledger!.prepare({ type: props.clear ? "CLEAR_HIGHLIGHTS" : "HIGHLIGHT_CELLS", sheet: props.sheet, cells: props.clear ? [] : props.cells, color: props.color, label: props.label.slice(0, 250) });
        setEntry(item); reviewed.current = target; setStatus("preview");
      } else if (action === "confirm" && entry) {
        if (reviewed.current !== target) throw new Error(vi ? "Phạm vi đã đổi. Hãy xem trước lại." : "Target changed. Preview again.");
        setStatus("loading");
        await ledger!.confirm(entry.id);
        props.onConfirm();
        await ledger!.refresh();
        setStatus("applied");
      } else if (action === "cancel") {
        if (entry) await ledger!.cancel(entry.id);
        setStatus("cancelled");
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể lưu hành động."); setStatus(entry ? "preview" : "idle"); }
    finally { busy.current = false; }
  }
  return <section className="min-w-0 rounded-md border border-slate-200 bg-white p-3 text-xs">
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0"><p className="truncate font-semibold text-slate-900" title={props.label}>{props.label}</p><p className="mt-1 text-slate-500">{props.sheet} · {props.cells.length} {vi ? "ô" : "cells"}</p></div>
      {!props.clear && <span className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[10px] text-slate-600"><span className="h-3 w-3 rounded-sm border border-black/10" style={{ backgroundColor: props.color }} aria-hidden="true" />{props.color}</span>}
    </div>
    <p className="mt-2 text-[11px] leading-4 text-slate-500">{vi ? "Lưu lớp hiển thị trong SCANT; file gốc không thay đổi." : "Save a SCANT display layer; the original file stays unchanged."}</p>
    {status === "preview" && entry && <div className="mt-2 max-h-32 overflow-auto rounded-md bg-slate-50 p-2 text-[11px] text-slate-600">
      <p className="mb-1 font-medium text-slate-700">{vi ? "Các ô sẽ thay đổi:" : "Cells to change:"}</p>
      {entry.preview.map((cell) => <p key={cell.cell} className="break-words font-mono">{cell.cell}: {String(cell.value ?? "∅")} → {cell.after_color}</p>)}
      {props.clear && <p>{vi ? "Xóa các lớp màu SCANT trên sheet này." : "Clear SCANT layers on this sheet."}</p>}
    </div>}
    <p aria-live="polite" className="mt-2 text-slate-600">{status === "applied" ? (vi ? "Đã lưu và áp dụng trong SCANT." : "Saved and applied in SCANT.") : status === "cancelled" ? (vi ? "Đã hủy." : "Cancelled.") : status === "loading" ? (vi ? "Đang lưu…" : "Saving…") : ""}</p>
    {(error || props.unavailable) && <p role="alert" className="text-red-700">{error || props.unavailable}</p>}
    {status !== "applied" && status !== "cancelled" && <div className="mt-2 flex flex-wrap gap-2">
      <button type="button" disabled={status === "loading" || !!props.unavailable} onClick={() => perform("preview")} className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:opacity-50">{status === "loading" ? (vi ? "Đang tải…" : "Loading…") : (vi ? "Xem ô" : "Review cells")}</button>
      {status === "preview" && <button type="button" disabled={!!props.unavailable} onClick={() => perform("confirm")} className="rounded-md bg-emerald-600 px-2.5 py-1.5 font-semibold text-white hover:bg-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:opacity-50">{vi ? "Xác nhận tô màu" : "Confirm highlight"}</button>}
      <button type="button" disabled={status === "loading"} onClick={() => perform("cancel")} className="rounded-md px-2.5 py-1.5 font-medium text-slate-500 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:opacity-50">{vi ? "Bỏ qua" : "Dismiss"}</button>
    </div>}
  </section>;
}
