"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  PlusCircle,
  FolderKanban,
  Layers,
  Database,
  Globe,
  Settings,
  ChevronLeft,
  ChevronRight,
  Shield,
  MoreVertical,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { isSidebarItemActive } from "@/lib/sidebarNav";
import { useTranslation } from "@/i18n/I18nContext";
import { useAuthStore } from "@/stores/useAuthStore";
import { getWorkspaceNavigation, type WorkspaceRouteKey } from "@/lib/productFocus";

type SidebarProps = {
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
};

export function Sidebar({ collapsed, onCollapsedChange }: SidebarProps) {
  const pathname = usePathname() || "";
  const router = useRouter();
  const { t } = useTranslation();
  const { user, isAuthenticated, logout } = useAuthStore();
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement>(null);

  const toggleCollapse = () => {
    onCollapsedChange(!collapsed);
  };

  const handleLogout = () => {
    setIsAccountMenuOpen(false);
    logout();
    router.push("/login");
  };

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (accountMenuRef.current && !accountMenuRef.current.contains(event.target as Node)) {
        setIsAccountMenuOpen(false);
      }
    }
    if (isAccountMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isAccountMenuOpen]);

  const routeMeta: Record<WorkspaceRouteKey, { icon: typeof LayoutDashboard; label: string; highlight?: boolean }> = {
    home: { icon: LayoutDashboard, label: t("navigation.home") },
    new: { icon: PlusCircle, label: t("navigation.new"), highlight: true },
    projects: { icon: FolderKanban, label: t("navigation.projects") },
    data: { icon: Database, label: t("navigation.data") },
    research: { icon: Globe, label: t("navigation.research") },
    templates: { icon: Layers, label: t("navigation.templates") },
    settings: { icon: Settings, label: t("navigation.settings") },
    admin: { icon: Shield, label: t("navigation.admin") },
  };
  const navItems = getWorkspaceNavigation(Boolean(user?.is_superuser || user?.role === "admin"))
    .map((route) => ({ ...route, ...routeMeta[route.key] }));

  const displayName = user?.name || "Kỹ sư VIP Pro";
  const displayPlan = user?.plan ? (user.plan === "pro" ? "Enterprise" : user.plan) : "Enterprise";
  const avatarLetter = displayName.charAt(0).toUpperCase() || "K";

  return (
    <aside
      className={cn(
        "fixed left-0 top-14 z-30 flex h-[calc(100vh-3.5rem)] select-none flex-col justify-between border-r border-slate-200 bg-white transition-all duration-200 dark:border-slate-800 dark:bg-slate-950",
        collapsed ? "w-16" : "w-[268px]"
      )}
    >
      <div className="space-y-2 overflow-y-auto p-3">
        {/* Workspace header & collapse trigger */}
        <div className="flex items-center justify-between px-2 pt-1 pb-1">
          {!collapsed && (
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
              {t("navigation.workspace")}
            </span>
          )}
          <button
            onClick={toggleCollapse}
            title={collapsed ? t("common.expand") : t("common.collapse")}
            className="ml-auto rounded-lg p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
        </div>

        {/* Navigation list */}
        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = isSidebarItemActive(pathname, item.href);
            return (
              <Link
                key={item.key}
                href={item.href}
                prefetch={true}
                title={collapsed ? item.label : undefined}
                className={cn(
                  "flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors",
                  item.highlight && isActive
                    ? "bg-slate-900 text-white font-semibold shadow-2xs hover:bg-slate-800 dark:bg-cyan-300 dark:text-slate-950"
                    : isActive
                    ? "bg-slate-900 text-white font-semibold shadow-2xs dark:bg-cyan-400/15 dark:text-cyan-200"
                    : "text-slate-600 hover:bg-slate-100/80 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100",
                  collapsed && "justify-center px-0"
                )}
              >
                <Icon
                  className={cn(
                    "h-[18px] w-[18px] shrink-0",
                    item.highlight && isActive
                      ? "text-white"
                      : isActive
                      ? "text-white dark:text-cyan-200"
                      : "text-slate-400"
                  )}
                />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer: Account Card at bottom of sidebar */}
      <div className="relative border-t border-slate-200/80 p-2.5 dark:border-slate-800" ref={accountMenuRef}>
        {collapsed ? (
          <button
            type="button"
            onClick={() => onCollapsedChange(false)}
            className="flex w-full items-center justify-center p-1.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-900 transition-colors"
            title={`${displayName} - ${displayPlan}`}
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs border border-indigo-200 dark:bg-indigo-950 dark:text-indigo-300 dark:border-indigo-800">
              {avatarLetter}
            </div>
          </button>
        ) : (
          <div className="flex items-center justify-between gap-2.5 rounded-xl p-2 transition-colors hover:bg-slate-100/80 dark:hover:bg-slate-900">
            <Link
              href="/settings"
              className="flex items-center gap-2.5 min-w-0 flex-1 group"
              title={displayName}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs border border-indigo-200 transition-transform group-hover:scale-105 dark:bg-indigo-950 dark:text-indigo-300 dark:border-indigo-800">
                {avatarLetter}
              </div>
              <div className="min-w-0 flex-1 text-left">
                <div className="truncate text-xs font-semibold text-slate-800 dark:text-slate-200 group-hover:text-indigo-600 transition-colors">
                  {displayName}
                </div>
                <div className="truncate text-[11px] text-slate-500 capitalize dark:text-slate-400">
                  {displayPlan}
                </div>
              </div>
            </Link>

            <button
              type="button"
              onClick={() => setIsAccountMenuOpen((prev) => !prev)}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200/60 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200 transition-colors"
              title="Menu tài khoản"
              aria-label="Menu tài khoản"
            >
              <MoreVertical className="h-4 w-4" />
            </button>
          </div>
        )}

        {/* Account Menu Dropdown */}
        {isAccountMenuOpen && !collapsed && (
          <div className="absolute bottom-[calc(100%+6px)] left-2.5 right-2.5 z-50 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg dark:border-slate-800 dark:bg-slate-950 animate-in fade-in slide-in-from-bottom-2 duration-150">
            <Link
              href="/settings"
              onClick={() => setIsAccountMenuOpen(false)}
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-900 transition-colors"
            >
              <Settings className="h-3.5 w-3.5 text-slate-500" />
              <span>{t("navigation.settings")}</span>
            </Link>
            {isAuthenticated && (
              <button
                type="button"
                onClick={handleLogout}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors"
              >
                <LogOut className="h-3.5 w-3.5 text-rose-500" />
                <span>{t("navigation.logout")}</span>
              </button>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
