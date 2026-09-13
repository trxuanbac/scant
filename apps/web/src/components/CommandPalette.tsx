"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  Sparkles,
  Database,
  Layers,
  Settings,
  ShieldCheck,
  LayoutDashboard,
  FolderKanban,
  Globe,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "@/i18n/I18nContext";
import { useAuthStore } from "@/stores/useAuthStore";
import { getWorkspaceNavigation, type WorkspaceRouteKey } from "@/lib/productFocus";

interface CommandItem {
  id: string;
  title: string;
  category: string;
  icon: LucideIcon;
  action: () => void;
}

export function CommandPalette() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const router = useRouter();
  const { t } = useTranslation();
  const user = useAuthStore((state) => state.user);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      } else if (e.key === "Escape") {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const commandMeta: Record<WorkspaceRouteKey, { title: string; icon: LucideIcon }> = {
    home: { title: t("navigation.home"), icon: LayoutDashboard },
    new: { title: t("commandPalette.commands.autoCreate"), icon: Sparkles },
    projects: { title: t("navigation.projects"), icon: FolderKanban },
    data: { title: t("navigation.data"), icon: Database },
    research: { title: t("navigation.research"), icon: Globe },
    templates: { title: t("navigation.templates"), icon: Layers },
    settings: { title: t("navigation.settings"), icon: Settings },
    admin: { title: t("navigation.admin"), icon: ShieldCheck },
  };
  const commands: CommandItem[] = getWorkspaceNavigation(Boolean(user?.is_superuser || user?.role === "admin"))
    .map((route) => ({
      id: route.key,
      title: commandMeta[route.key].title,
      category: t("navigation.workspace"),
      icon: commandMeta[route.key].icon,
      action: () => {
        router.push(route.href);
        setIsOpen(false);
      },
    }));

  const filteredCommands = commands.filter(
    (c) =>
      c.title.toLowerCase().includes(query.toLowerCase()) ||
      c.category.toLowerCase().includes(query.toLowerCase())
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-slate-900/40 backdrop-blur-xs p-4">
      <div className="w-full max-w-xl bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Search input header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100">
          <Search className="h-5 w-5 text-slate-400" />
          <input
            autoFocus
            type="text"
            placeholder={t("commandPalette.searchPlaceholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-hidden"
          />
          <kbd className="px-2 py-0.5 text-[10px] font-bold text-slate-400 bg-slate-100 rounded-md border border-slate-200">
            ESC
          </kbd>
        </div>

        {/* Command list */}
        <div className="max-h-80 overflow-y-auto p-2 space-y-1">
          {filteredCommands.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-400">
              {t("commandPalette.noResults")}
            </div>
          ) : (
            filteredCommands.map((c) => {
              const Icon = c.icon;
              return (
                <button
                  key={c.id}
                  onClick={c.action}
                  className="w-full flex items-center justify-between p-2.5 rounded-xl hover:bg-indigo-50/70 text-left group transition"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-slate-100 text-slate-600 rounded-lg group-hover:bg-indigo-100 group-hover:text-indigo-700 transition">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-slate-800 group-hover:text-indigo-900">
                        {c.title}
                      </p>
                      <p className="text-[10px] text-slate-400">{c.category}</p>
                    </div>
                  </div>
                  <span className="text-[10px] text-slate-400 opacity-0 group-hover:opacity-100 font-medium">
                    ↵ {t("commandPalette.select")}
                  </span>
                </button>
              );
            })
          )}
        </div>

        {/* Footer hints */}
        <div className="px-4 py-2 bg-slate-50 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
          <span>{t("common.appTagline")}</span>
          <span>{t("commandPalette.keyboardHint")}</span>
        </div>
      </div>
    </div>
  );
}
