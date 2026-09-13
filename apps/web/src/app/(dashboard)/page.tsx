"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Briefcase,
  TrendingUp,
  Search,
  FileSpreadsheet,
  FileText,
  ArrowRight,
  Sparkles,
  Clock,
  Layers,
  FolderKanban,
  Zap,
  CheckCircle2,
  Database,
  Gauge,
} from "lucide-react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { useTranslation } from "@/i18n/I18nContext";
import { AnimatedCard } from "@/components/AnimatedCard";
import { SkeletonLoader } from "@/components/SkeletonLoader";

export default function DashboardPage() {
  const router = useRouter();
  const { t, locale } = useTranslation();
  const [projects, setProjects] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [heroPrompt, setHeroPrompt] = useState("");

  useEffect(() => {
    async function loadData() {
      try {
        const data = await api.projects.list();
        setProjects(data);
      } catch {
        // User not yet authenticated
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const handleHeroSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!heroPrompt.trim()) return;
    router.push(`/projects/new?prompt=${encodeURIComponent(heroPrompt)}`);
  };

  const handleDemoProject = async () => {
    try {
      const res = await api.projects.create({
        name: "Báo Cáo Tăng Trưởng Doanh Số Mẫu (Demo)",
        type: "business_report",
        description: "Dự án mẫu khám phá tính năng tạo báo cáo tự động và phân tích định lượng.",
      });
      router.push(`/projects/${res.id}`);
    } catch {
      router.push("/projects/new");
    }
  };

  const quickActions = [
    {
      type: "business_report",
      href: "/projects/new?mode=auto&type=business_report",
      title: t("dashboard.createReport"),
      desc: t("dashboard.createReportDesc"),
      icon: Briefcase,
      color: "text-blue-600 bg-blue-50 border-blue-100 hover:border-blue-300",
      action: "Tạo tự động",
    },
    {
      type: "data_analysis",
      href: "/projects/new?mode=auto&type=data_analysis&workflow=data",
      title: t("dashboard.analyzeData"),
      desc: t("dashboard.analyzeDataDesc"),
      icon: TrendingUp,
      color: "text-emerald-600 bg-emerald-50 border-emerald-100 hover:border-emerald-300",
      action: "Tải XLSX/CSV",
    },
    {
      type: "research",
      href: "/projects/new?mode=auto&type=research&prompt=Nghiên%20cứu%20chuyên%20sâu%20về%20một%20đề%20tài%20có%20nguồn%20tham%20khảo%20và%20kiểm%20chứng",
      title: t("dashboard.deepResearch"),
      desc: t("dashboard.deepResearchDesc"),
      icon: Search,
      color: "text-indigo-600 bg-indigo-50 border-indigo-100 hover:border-indigo-300",
      action: "Tạo nghiên cứu",
    },
    {
      type: "custom",
      href: "/projects/new?mode=auto&type=custom",
      title: locale === "vi" ? "Tài Liệu Tùy Chỉnh" : "Custom Document",
      desc: locale === "vi" ? "Dùng khi tài liệu đặc thù, AI tự suy luận cấu trúc từ yêu cầu." : "For special documents where AI infers the right structure.",
      icon: FileText,
      color: "text-slate-600 bg-slate-50 border-slate-200 hover:border-slate-300",
      action: locale === "vi" ? "Tạo tùy chỉnh" : "Create custom",
    },
  ];
  const workflowStats = [
    { label: locale === "vi" ? "Luồng cốt lõi" : "Core flows", value: "4", icon: Gauge },
    { label: locale === "vi" ? "Nguồn dữ liệu" : "Data sources", value: "XLSX", icon: Database },
    { label: locale === "vi" ? "Kiểm chứng" : "Grounding", value: "ON", icon: CheckCircle2 },
  ];

  return (
    <div className="space-y-7 py-2">
      {/* Central Hero: What do you want to create? */}
      <section className="studio-hero relative overflow-hidden rounded-xl border border-slate-800 bg-slate-950 text-white shadow-[0_18px_60px_-36px_rgba(15,23,42,0.85)]">
        <div className="relative z-10 grid gap-6 p-5 sm:p-7 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="max-w-3xl space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-md border border-cyan-400/25 bg-cyan-400/10 px-2.5 py-1 text-xs font-semibold text-cyan-100">
                <Sparkles className="h-3.5 w-3.5 text-cyan-200" />
                AI Report Studio
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-medium text-slate-300">
                <Zap className="h-3.5 w-3.5 text-amber-300" />
                {locale === "vi" ? "PDF, Word, Excel trong một luồng" : "PDF, Word, Excel in one flow"}
              </span>
            </div>

            <div className="space-y-2">
              <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-4xl">
                {t("dashboard.heroQuestion")}
              </h1>
              <p className="max-w-2xl text-sm leading-6 text-slate-300">
                {locale === "vi"
                  ? "Tạo báo cáo, phân tích bảng tính và gom nguồn tham khảo trong một không gian làm việc rõ ràng, có kiểm chứng."
                  : "Create reports, analyze spreadsheets, and organize references in a grounded workspace."}
              </p>
            </div>

            <form onSubmit={handleHeroSubmit} className="space-y-3">
              <div className="relative rounded-xl border border-white/10 bg-white/[0.07] p-2 shadow-inner shadow-black/20 transition-colors focus-within:border-cyan-300/60">
                <textarea
                  value={heroPrompt}
                  onChange={(e) => setHeroPrompt(e.target.value)}
                  placeholder={t("dashboard.heroPlaceholder")}
                  rows={3}
                  className="min-h-24 w-full resize-none bg-transparent p-2 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-500"
                />

                {/* Bottom toolbar inside input */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 px-1 pt-2">
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                    <span className="mr-1 text-[11px] font-medium">{t("dashboard.attachDoc")}:</span>
                    <Link
                      href="/projects/new"
                      className="inline-flex items-center gap-1 rounded-md bg-white/10 px-2 py-1 text-slate-300 transition-colors hover:bg-white/15 hover:text-white"
                    >
                      <FileText className="h-3 w-3" />
                      <span>PDF / DOCX</span>
                    </Link>
                    <Link
                      href="/data"
                      className="inline-flex items-center gap-1 rounded-md bg-white/10 px-2 py-1 text-slate-300 transition-colors hover:bg-white/15 hover:text-white"
                    >
                      <FileSpreadsheet className="h-3 w-3" />
                      <span>Excel</span>
                    </Link>
                    <Link
                      href="/templates"
                      className="inline-flex items-center gap-1 rounded-md bg-white/10 px-2 py-1 text-slate-300 transition-colors hover:bg-white/15 hover:text-white"
                    >
                      <Layers className="h-3 w-3" />
                      <span>Template</span>
                    </Link>
                  </div>

                  <button
                    type="submit"
                    disabled={!heroPrompt.trim()}
                    className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-cyan-300 px-4 text-xs font-bold text-slate-950 shadow-sm transition-all hover:bg-cyan-200 disabled:opacity-40"
                  >
                    <span>{t("dashboard.generateAuto")}</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </form>
          </div>

          <div className="hidden rounded-xl border border-white/10 bg-white/[0.06] p-4 backdrop-blur lg:block">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase text-slate-400">
                  {locale === "vi" ? "Trạng thái studio" : "Studio status"}
                </p>
                <p className="mt-1 text-sm font-semibold text-white">
                  {locale === "vi" ? "Sẵn sàng tạo tài liệu" : "Ready to compose"}
                </p>
              </div>
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-300 shadow-[0_0_18px_rgba(110,231,183,0.9)]" />
            </div>
            <div className="space-y-2">
              {workflowStats.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label} className="flex items-center justify-between rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2">
                    <span className="inline-flex items-center gap-2 text-xs text-slate-300">
                      <Icon className="h-3.5 w-3.5 text-cyan-200" />
                      {item.label}
                    </span>
                    <span className="text-xs font-bold text-white">{item.value}</span>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 rounded-lg bg-cyan-300/10 p-3 text-xs leading-5 text-cyan-50 ring-1 ring-cyan-300/20">
              {locale === "vi"
                ? "Gợi ý: tải Excel lương và hỏi AI lọc, tô màu, xuất file đã highlight."
                : "Tip: upload payroll Excel, then ask AI to filter, highlight, and export."}
            </div>
          </div>
        </div>
      </section>

      {/* Quick Actions */}
      <section className="space-y-3 rounded-xl border border-slate-200 bg-white/75 p-4 shadow-[0_18px_60px_-45px_rgba(15,23,42,0.6)] backdrop-blur dark:border-slate-800 dark:bg-slate-950/60">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">
            {t("dashboard.quickActions")}
          </h2>
          <button
            onClick={handleDemoProject}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 transition-colors hover:border-indigo-200 hover:text-indigo-700 dark:border-slate-700 dark:bg-slate-900"
          >
            <Zap className="h-3.5 w-3.5" />
            <span>{t("dashboard.demoProjectBtn")}</span>
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {quickActions.map((qa) => {
            const Icon = qa.icon;
            return (
              <Link
                key={qa.type}
                href={qa.href}
                className="block group"
              >
                <AnimatedCard className={`h-full rounded-xl border bg-white p-4 shadow-[0_1px_0_rgba(15,23,42,0.04)] transition-all duration-200 hover:shadow-[0_14px_35px_-26px_rgba(15,23,42,0.9)] dark:bg-slate-900 ${qa.color}`}>
                  <div className="space-y-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white shadow-2xs dark:bg-slate-950">
                      <Icon className="h-5 w-5" />
                    </div>
                    <h3 className="font-bold text-slate-900 text-sm group-hover:text-indigo-600 transition-colors">
                      {qa.title}
                    </h3>
                    <p className="text-xs text-slate-500 leading-relaxed">{qa.desc}</p>
                  </div>
                  <div className="flex items-center gap-1 pt-4 text-xs font-semibold text-indigo-600 opacity-0 transition-opacity group-hover:opacity-100">
                    <span>{qa.action}</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </div>
                </AnimatedCard>
              </Link>
            );
          })}
        </div>
      </section>

      {/* Recent Projects */}
      <section className="space-y-3 rounded-xl border border-slate-200 bg-white/75 p-4 backdrop-blur dark:border-slate-800 dark:bg-slate-950/60">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">
            {t("dashboard.recentProjects")}
          </h2>
          <Link href="/projects" className="text-xs font-semibold text-indigo-600 hover:text-indigo-700">
            {t("dashboard.viewAll")}
          </Link>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <SkeletonLoader count={3} className="h-32" />
          </div>
        ) : projects.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center space-y-2">
            <FolderKanban className="mx-auto h-8 w-8 text-slate-400" />
            <h3 className="text-xs font-bold text-slate-800">{t("dashboard.noProjectsYet")}</h3>
            <p className="text-xs text-slate-500">{t("dashboard.noProjectsDesc")}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {projects.slice(0, 6).map((proj) => (
              <Link
                key={proj.id}
                href={`/projects/${proj.id}`}
                className="block group"
              >
                <AnimatedCard className="p-4 rounded-2xl bg-white border border-slate-200 hover:border-indigo-300 hover:shadow-xs transition-all space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="px-2 py-0.5 rounded-md bg-indigo-50 text-[10px] font-bold text-indigo-700 uppercase">
                      {proj.type || "Report"}
                    </span>
                    <span className="text-[10px] text-slate-400 flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatDate(proj.created_at)}
                    </span>
                  </div>
                  <h4 className="font-bold text-slate-900 text-xs truncate group-hover:text-indigo-600 transition-colors">
                    {proj.name}
                  </h4>
                  <p className="text-[11px] text-slate-500 line-clamp-2 leading-relaxed">
                    {proj.description || t("common.noData")}
                  </p>
                </AnimatedCard>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
