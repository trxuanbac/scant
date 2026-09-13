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
    {enabled && <div className="flex flex-wrap items-center gap-2 px-4 py-2 text-xs text-slate-600" aria-live="polite">
      <span>{locale === "vi" ? "Lịch sử lớp màu đã lưu" : "Saved highlight history"}: {history.data?.items.length ?? 0}</span>
      <details className="basis-full">
        <summary className="cursor-pointer">{locale === "vi" ? "Xem lịch sử và đề xuất đang chờ" : "View history and pending proposals"}</summary>
        <div className="max-h-80 space-y-2 overflow-auto pt-2">
          {history.data?.items.map((item) => item.status === "pending" ? <PersistentSpreadsheetActionCard key={item.id} savedEntry={item} label={item.action.label || item.action.type} sheet={item.action.sheet} cells={item.action.cells} color={item.action.color} clear={item.action.type === "CLEAR_HIGHLIGHTS"} locale={locale} onConfirm={() => {}} /> : <p key={item.id} className="break-words">{item.action.sheet} · {item.action.label || item.action.type} · {locale === "vi" ? ({ applied: "Đã áp dụng", cancelled: "Đã hủy", undone: "Đã hoàn tác" }[item.status] || item.status) : item.status}</p>)}
          {!history.data?.items.length && <p>{locale === "vi" ? "Chưa có hành động đã lưu cho phiên bản workbook này." : "No saved actions for this workbook version."}</p>}
        </div>
      </details>
      <button type="button" onClick={undo} disabled={undoing || !history.data?.undo_id} className="rounded border border-slate-300 px-2 py-1 disabled:opacity-40">{locale === "vi" ? "Hoàn tác lớp gần nhất" : "Undo latest layer"}</button>
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
  return <section className="space-y-2 rounded-md border border-slate-200 bg-white p-3 text-xs">
    <p className="font-semibold">{props.label}</p>
    <p>Sheet: {props.sheet} · {props.cells.length} {vi ? "ô" : "cells"} · {props.color}</p>
    <p className="text-slate-500">{vi ? "Lưu lớp hiển thị và lịch sử trong SCANT. Không sửa file gốc hoặc Google Sheets." : "Save the SCANT display layer and history. Original files and Google Sheets stay unchanged."}</p>
    {status === "preview" && entry && <div className="max-h-40 overflow-auto">
      <p>{vi ? "Xem trước trên dữ liệu thật (tối đa 200 ô):" : "Source preview (up to 200 cells):"}</p>
      {entry.preview.map((cell) => <p key={cell.cell} className="break-words">{cell.cell}: {String(cell.value ?? "∅")} → {cell.after_color}</p>)}
      {props.clear && <p>{vi ? "Xóa các lớp màu SCANT trên sheet này." : "Clear SCANT layers on this sheet."}</p>}
    </div>}
    <p aria-live="polite">{status === "applied" ? (vi ? "Đã lưu và áp dụng trong SCANT." : "Saved and applied in SCANT.") : status === "cancelled" ? (vi ? "Đã hủy." : "Cancelled.") : status === "loading" ? (vi ? "Đang lưu…" : "Saving…") : ""}</p>
    {(error || props.unavailable) && <p role="alert" className="text-red-700">{error || props.unavailable}</p>}
    {status !== "applied" && status !== "cancelled" && <div className="flex flex-wrap gap-2">
      <button type="button" disabled={status === "loading" || !!props.unavailable} onClick={() => perform("preview")} className="rounded border px-2 py-1">{vi ? "Xem trước" : "Preview"}</button>
      {status === "preview" && <button type="button" disabled={!!props.unavailable} onClick={() => perform("confirm")} className="rounded bg-slate-900 px-2 py-1 text-white">{vi ? "Xác nhận và lưu lớp màu" : "Confirm and save layer"}</button>}
      <button type="button" disabled={status === "loading"} onClick={() => perform("cancel")} className="rounded border px-2 py-1">{vi ? "Hủy" : "Cancel"}</button>
    </div>}
  </section>;
}
