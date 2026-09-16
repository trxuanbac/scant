"use client";

import { useRef, useState } from "react";
import { createLocalActionConfirmation } from "@/lib/localActionConfirmation";

interface SpreadsheetActionCardProps {
  label: string;
  sheet: string;
  cells: string[];
  rows?: number[];
  color: string;
  clear?: boolean;
  unavailable?: string;
  locale: string;
  onConfirm: () => void;
}

/** Preview is descriptive only. The callback runs solely after explicit confirmation. */
export function SpreadsheetActionCard({ label, sheet, cells, rows, color, clear, unavailable, locale, onConfirm }: SpreadsheetActionCardProps) {
  const vi = locale === "vi";
  const [status, setStatus] = useState<"proposed" | "preview" | "applied" | "cancelled" | "error" | "failed">("proposed");
  const [error, setError] = useState("");
  const confirmation = useRef(createLocalActionConfirmation());
  // Freeze exactly what the user reviewed; never confirm a silently changed target.
  const target = JSON.stringify({ sheet, cells, color, clear });
  const terminal = status === "applied" || status === "cancelled" || status === "failed";
  const buttonClass = "rounded-md border border-slate-200 px-2.5 py-1.5 text-xs font-medium hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:cursor-not-allowed disabled:opacity-50";

  function confirm() {
    if (confirmation.current.isConsumed() || status !== "preview" || unavailable) return;
    try {
      if (!confirmation.current.confirm(target, onConfirm)) {
        setError(vi ? "Phạm vi đã thay đổi. Hãy xem trước lại." : "The target changed. Review the preview again.");
        setStatus("error");
        return;
      }
      setStatus("applied");
    } catch (cause) {
      // Do not retry an ambiguous callback; it may already have changed local state.
      setError(cause instanceof Error ? cause.message : (vi ? "Không thể áp dụng hành động." : "Could not apply the action."));
      setStatus("failed");
    }
  }

  return (
    <section className="min-w-0 rounded-md border border-slate-200 bg-white p-3 text-xs">
      <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate font-semibold text-slate-900" title={label}>{label}</p><p className="mt-1 break-words text-slate-500">{sheet || "—"} · {clear ? (vi ? "Toàn bộ lớp màu" : "All highlight layers") : `${cells.length} ${vi ? "ô" : "cells"}${rows?.length ? ` · ${rows.length} ${vi ? "hàng" : "rows"}` : ""}`}</p></div>{!clear && <span className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[10px] text-slate-600"><span className="h-3 w-3 rounded-sm border border-black/10" style={{ backgroundColor: color }} aria-hidden="true" />{color}</span>}</div>
      <p className="mt-2 text-[11px] leading-4 text-slate-500">{vi ? "Lưu lớp hiển thị trong SCANT; file gốc không thay đổi." : "Save a SCANT display layer; the original file stays unchanged."}</p>
      {status === "preview" && (
        <div className="mt-2 space-y-2 border-t border-slate-100 pt-2">
          {!clear && <p className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm border border-slate-300" style={{ backgroundColor: color }} aria-hidden="true" />{vi ? "Màu tô" : "Highlight color"}: {color}</p>}
          {rows?.length ? <p className="max-h-20 overflow-auto break-words">{vi ? "Hàng" : "Rows"}: {rows.join(", ")}</p> : null}
          {!clear && <p className="max-h-32 overflow-auto break-words font-mono" aria-label={vi ? "Các ô sẽ tô màu" : "Cells to highlight"}>{cells.join(", ")}</p>}
          <p>{vi ? "Xác nhận áp dụng thay đổi cục bộ này?" : "Confirm this local change?"}</p>
        </div>
      )}
      <div aria-live="polite" className="mt-2 text-slate-600">
        {status === "applied" && (vi ? "Đã áp dụng cục bộ. Chưa đồng bộ Google Sheets." : "Applied locally. Google Sheets has not been synced.")}
        {status === "cancelled" && (vi ? "Đã hủy. Không áp dụng thay đổi." : "Cancelled. No change applied.")}
        {unavailable && <p>{unavailable}</p>}
        {(status === "error" || status === "failed") && <p role="alert" className="break-words text-red-700">{error}</p>}
      </div>
      {!terminal && <div className="mt-2 flex flex-wrap gap-2">
        {status === "preview" ? <button type="button" className={`${buttonClass} bg-slate-900 text-white hover:bg-slate-700`} disabled={!!unavailable} onClick={confirm}>{vi ? "Xác nhận áp dụng cục bộ" : "Confirm local change"}</button> : <button type="button" className={buttonClass} disabled={!!unavailable} onClick={() => { confirmation.current.preview(target); setError(""); setStatus("preview"); }}>{vi ? "Xem trước" : "Preview"}</button>}
        <button type="button" className={buttonClass} onClick={() => { confirmation.current.cancel(); setStatus("cancelled"); }}>{vi ? "Hủy" : "Cancel"}</button>
      </div>}
    </section>
  );
}
