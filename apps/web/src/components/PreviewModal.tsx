"use client";

import { ReactNode } from "react";
import { X } from "lucide-react";

interface PreviewModalProps {
  title: string;
  subtitle?: string;
  isOpen: boolean;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: "default" | "wide";
}

export function PreviewModal({ title, subtitle, isOpen, onClose, children, footer, size = "default" }: PreviewModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 top-14 z-50 flex items-center justify-center bg-white/65 p-2 backdrop-blur-[2px] sm:p-4">
      <div className={`flex min-h-0 w-full flex-col rounded-2xl border border-slate-200 bg-white shadow-lg ${size === "wide" ? "max-h-[calc(100dvh-5rem)] max-w-[min(96rem,94vw)]" : "max-h-[82vh] max-w-2xl"}`}>
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-slate-100 p-4 sm:p-5">
          <div className="min-w-0">
            <h2 className="text-base font-bold text-slate-950">{title}</h2>
            {subtitle && <p className="mt-1 text-xs text-slate-500">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            aria-label="Đóng"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">{children}</div>

        {footer && (
          <div className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-slate-100 p-4">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
