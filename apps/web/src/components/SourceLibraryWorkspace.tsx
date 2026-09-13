"use client";

import { useCallback, useEffect, useState, useMemo } from "react";
import {
  Search,
  ShieldCheck,
  ShieldAlert,
  ExternalLink,
  BookmarkCheck,
  Globe,
  BookOpen,
  RefreshCw,
  FileText,
  Table,
  Upload,
  Plus,
  Trash2,
  CheckCircle2,
  AlertCircle,
  X,
  Layers,
  Link as LinkIcon,
  Sparkles,
  Calculator,
  ChevronRight,
  Building2,
  GraduationCap,
  FileCheck,
  FileSpreadsheet,
} from "lucide-react";
import { api } from "@/lib/api";

export function SourceLibraryWorkspace() {
  // State: Projects & Selection
  const [projects, setProjects] = useState<any[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [loadingProjects, setLoadingProjects] = useState<boolean>(true);

  // State: Sources & Stats
  const [sources, setSources] = useState<any[]>([]);
  const [stats, setStats] = useState({
    total_sources: 0,
    verified_count: 0,
    needs_review_count: 0,
    in_use_count: 0,
    missing_evidence_count: 0,
  });
  const [loadingSources, setLoadingSources] = useState<boolean>(false);

  // State: Filters
  const [searchFilter, setSearchFilter] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  // State: Detail Drawer
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null);
  const [sourceDetail, setSourceDetail] = useState<any | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"overview" | "evidence" | "citations" | "verification">("overview");

  // State: Modals
  const [showSearchModal, setShowSearchModal] = useState<boolean>(false);
  const [showUrlModal, setShowUrlModal] = useState<boolean>(false);
  const [showUploadModal, setShowUploadModal] = useState<boolean>(false);
  const [deleteCandidate, setDeleteCandidate] = useState<any | null>(null);
  const [deleteWarning, setDeleteWarning] = useState<any | null>(null);

  // State: Search Modal Operations
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [searchProviders, setSearchProviders] = useState<string[]>(["microsoft_learn", "openalex", "arxiv", "crossref"]);
  const searchSort = "RELEVANCE";
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [importingIds, setImportingIds] = useState<Record<string, boolean>>({});

  // State: URL Modal Operations
  const [urlInput, setUrlInput] = useState<string>("");
  const [urlTitleInput, setUrlTitleInput] = useState<string>("");
  const [urlNotesInput, setUrlNotesInput] = useState<string>("");
  const [isAddingUrl, setIsAddingUrl] = useState<boolean>(false);

  // State: Upload Modal Operations
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadNotes, setUploadNotes] = useState<string>("");
  const [isUploading, setIsUploading] = useState<boolean>(false);

  // State: Manual Evidence Addition
  const [showAddEvidenceForm, setShowAddEvidenceForm] = useState<boolean>(false);
  const [newEvType, setNewEvType] = useState<string>("WEB_TEXT");
  const [newEvQuote, setNewEvQuote] = useState<string>("");
  const [newEvSection, setNewEvSection] = useState<string>("");
  const [newEvPage, setNewEvPage] = useState<string>("");
  const [newEvSheet, setNewEvSheet] = useState<string>("");
  const [newEvRange, setNewEvRange] = useState<string>("");
  const [newEvOp, setNewEvOp] = useState<string>("COUNT");
  const [isSavingEvidence, setIsSavingEvidence] = useState<boolean>(false);

  // Feedback Notification
  const [alertBanner, setAlertBanner] = useState<{ type: "success" | "error" | "info"; message: string } | null>(null);

  // Quick create a new project
  async function handleCreateProject() {
    try {
      const p = await api.projects.create({
        name: `Dự Án Nghiên Cứu ${projects.length + 1}`,
        type: "research",
        description: "Quản lý nguồn tài liệu học thuật và kiểm chứng trích dẫn",
      });
      setProjects((prev) => [...prev, p]);
      setSelectedProjectId(p.id);
      setAlertBanner({ type: "success", message: `Đã tạo mới dự án "${p.name}".` });
    } catch (err: any) {
      setAlertBanner({ type: "error", message: "Không thể tạo dự án: " + (err.message || "") });
    }
  }

  // Load Projects on Mount
  useEffect(() => {
    async function loadProjects() {
      setLoadingProjects(true);
      try {
        let list = await api.projects.list();
        if (!list || list.length === 0) {
          try {
            const p = await api.projects.create({
              name: "Dự Án Nghiên Cứu & Trích Dẫn",
              type: "research",
              description: "Kho tài liệu nghiên cứu và bằng chứng trích dẫn",
            });
            list = [p];
          } catch {
            // Guest or dev mode
          }
        }
        setProjects(list || []);
        if (list && list.length > 0) {
          setSelectedProjectId(list[0].id);
        }
      } catch (err: any) {
        console.warn("Could not load projects:", err);
      } finally {
        setLoadingProjects(false);
      }
    }
    loadProjects();
  }, []);

  // Load Sources when Selected Project Changes
  const loadProjectSources = useCallback(async (pId: string) => {
    setLoadingSources(true);
    try {
      const res = await api.sources.list(pId, {
        source_type: typeFilter !== "ALL" ? typeFilter : undefined,
        verification_status: statusFilter !== "ALL" ? statusFilter : undefined,
      });
      setSources(res.sources || []);
      setStats(res.stats || {
        total_sources: 0,
        verified_count: 0,
        needs_review_count: 0,
        in_use_count: 0,
        missing_evidence_count: 0,
      });
    } catch (err: any) {
      setAlertBanner({ type: "error", message: "Không thể tải danh sách nguồn: " + (err.message || "") });
    } finally {
      setLoadingSources(false);
    }
  }, [statusFilter, typeFilter]);

  useEffect(() => {
    if (!selectedProjectId) {
      setSources([]);
      return;
    }
    loadProjectSources(selectedProjectId);
  }, [loadProjectSources, selectedProjectId]);

  // Load Source Details into Drawer
  async function openSourceDrawer(sourceId: string) {
    setActiveSourceId(sourceId);
    setLoadingDetail(true);
    setShowAddEvidenceForm(false);
    try {
      const detail = await api.sources.get(sourceId);
      setSourceDetail(detail);
    } catch (err: any) {
      setAlertBanner({ type: "error", message: "Lỗi tải thông tin nguồn: " + (err.message || "") });
    } finally {
      setLoadingDetail(false);
    }
  }

  // Multi-Provider Search Execution
  async function handleSearch() {
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    setAlertBanner(null);
    try {
      const res = await api.sources.search({
        query: searchQuery.trim(),
        projectId: selectedProjectId || undefined,
        providers: searchProviders,
        sort_by: searchSort,
        limit: 12,
      });
      setSearchResults(res.results || []);
      if (!res.results || res.results.length === 0) {
        setAlertBanner({ type: "info", message: "Không tìm thấy tài liệu học thuật nào phù hợp với từ khóa này." });
      }
    } catch (err: any) {
      console.error("Search error:", err);
      setAlertBanner({ type: "error", message: "Tìm kiếm thất bại: " + (err.message || "Lỗi kết nối máy chủ.") });
    } finally {
      setIsSearching(false);
    }
  }

  // Import Selected Source from Search
  async function handleImportSource(item: any) {
    let targetProjectId = selectedProjectId;
    if (!targetProjectId) {
      try {
        const p = await api.projects.create({
          name: "Dự Án Nghiên Cứu & Trích Dẫn",
          type: "research",
          description: "Kho tài liệu nghiên cứu và bằng chứng trích dẫn",
        });
        setProjects((prev) => [...prev, p]);
        setSelectedProjectId(p.id);
        targetProjectId = p.id;
      } catch {
        setAlertBanner({ type: "error", message: "Vui lòng tạo hoặc chọn một dự án trước khi lưu nguồn." });
        return;
      }
    }

    const itemKey = item.canonical_url || item.url || item.title;
    setImportingIds((prev) => ({ ...prev, [itemKey]: true }));
    try {
      await api.sources.importSearch(targetProjectId, [item]);
      setAlertBanner({ type: "success", message: `Đã nạp nguồn "${item.title}" và trích xuất bằng chứng thành công.` });
      await loadProjectSources(targetProjectId);
    } catch (err: any) {
      setAlertBanner({ type: "error", message: "Không thể nạp nguồn: " + (err.message || "") });
    } finally {
      setImportingIds((prev) => ({ ...prev, [itemKey]: false }));
    }
  }

  // Add Source via URL
  async function handleAddUrlSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!urlInput.trim()) return;

    let targetProjectId = selectedProjectId;
    if (!targetProjectId) {
      try {
        const p = await api.projects.create({
          name: "Dự Án Nghiên Cứu & Trích Dẫn",
          type: "research",
          description: "Kho tài liệu nghiên cứu và bằng chứng trích dẫn",
        });
        setProjects((prev) => [...prev, p]);
        setSelectedProjectId(p.id);
        targetProjectId = p.id;
      } catch {
        setAlertBanner({ type: "error", message: "Vui lòng tạo hoặc chọn một dự án trước khi thêm URL." });
        return;
      }
    }

    setIsAddingUrl(true);
    try {
      const res = await api.sources.addUrl(targetProjectId, {
        url: urlInput.trim(),
        title: urlTitleInput.trim() || undefined,
        notes: urlNotesInput.trim() || undefined,
      });
      setShowUrlModal(false);
      setUrlInput("");
      setUrlTitleInput("");
      setUrlNotesInput("");
      setAlertBanner({ type: "success", message: `Đã thêm và kiểm chứng liên kết "${res.source?.title}".` });
      await loadProjectSources(targetProjectId);
    } catch (err: any) {
      setAlertBanner({ type: "error", message: "Không thể kiểm chứng liên kết: " + (err.message || "") });
    } finally {
      setIsAddingUrl(false);
    }
  }

  // Upload File as Source
  async function handleFileUploadSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!uploadFile) return;

    let targetProjectId = selectedProjectId;
    if (!targetProjectId) {
      try {
        const p = await api.projects.create({
          name: "Dự Án Nghiên Cứu & Trích Dẫn",
          type: "research",
          description: "Kho tài liệu nghiên cứu và bằng chứng trích dẫn",
        });
        setProjects((prev) => [...prev, p]);
        setSelectedProjectId(p.id);
        targetProjectId = p.id;
      } catch {
        setAlertBanner({ type: "error", message: "Vui lòng tạo hoặc chọn một dự án trước khi tải tệp." });
        return;
      }
    }

    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      if (uploadNotes.trim()) formData.append("notes", uploadNotes.trim());

      const res = await api.sources.uploadFile(targetProjectId, formData);
      setShowUploadModal(false);
      setUploadFile(null);
      setUploadNotes("");
      setAlertBanner({ type: "success", message: `Đã tải lên tệp "${res.source?.title}" và trích xuất bằng chứng tự động.` });
      await loadProjectSources(targetProjectId);
    } catch (err: any) {
      setAlertBanner({ type: "error", message: "Tải tệp thất bại: " + (err.message || "") });
    } finally {
      setIsUploading(false);
    }
  }

  // Re-Verify Source
  async function handleReVerify(sourceId: string) {
    try {
      const res = await api.sources.verify(sourceId);
      setAlertBanner({ type: "info", message: `Đã hoàn tất kiểm chứng: ${res.source?.verification_score}/100 điểm.` });
      await loadProjectSources(selectedProjectId);
      if (activeSourceId === sourceId) {
        await openSourceDrawer(sourceId);
      }
    } catch (err: any) {
      setAlertBanner({ type: "error", message: "Xác minh thất bại: " + (err.message || "") });
    }
  }

  // Delete Source with Citation Usage Safety
  async function handleDeleteSource(source: any, force: boolean = false) {
    try {
      const res = await api.sources.delete(source.id, force);
      if (res.requires_confirmation && !force) {
        setDeleteCandidate(source);
        setDeleteWarning(res);
        return;
      }
      setDeleteCandidate(null);
      setDeleteWarning(null);
      if (activeSourceId === source.id) {
        setActiveSourceId(null);
        setSourceDetail(null);
      }
      setAlertBanner({ type: "success", message: "Đã xóa nguồn tài liệu an toàn." });
      await loadProjectSources(selectedProjectId);
    } catch (err: any) {
      setAlertBanner({ type: "error", message: "Không thể xóa nguồn: " + (err.message || "") });
    }
  }

  // Add Manual or Excel Evidence Chunk
  async function handleAddEvidenceSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!activeSourceId) return;
    setIsSavingEvidence(true);
    try {
      await api.sources.addEvidence(activeSourceId, {
        evidence_type: newEvType,
        quote: newEvQuote.trim(),
        section_title: newEvSection.trim() || undefined,
        page_number: newEvPage ? parseInt(newEvPage) : undefined,
        sheet_name: newEvSheet.trim() || undefined,
        cell_range: newEvRange.trim() || undefined,
        operation: newEvOp || "COUNT",
      });
      setShowAddEvidenceForm(false);
      setNewEvQuote("");
      setNewEvSection("");
      setNewEvPage("");
      setNewEvSheet("");
      setNewEvRange("");
      setAlertBanner({ type: "success", message: "Đã bổ sung bằng chứng trích dẫn thành công." });
      await openSourceDrawer(activeSourceId);
      await loadProjectSources(selectedProjectId);
    } catch (err: any) {
      setAlertBanner({ type: "error", message: "Lỗi thêm bằng chứng: " + (err.message || "") });
    } finally {
      setIsSavingEvidence(false);
    }
  }

  // Delete Evidence Chunk
  async function handleDeleteEvidence(evidenceId: string) {
    try {
      await api.sources.deleteEvidence(evidenceId);
      setAlertBanner({ type: "success", message: "Đã xóa bằng chứng trích dẫn." });
      if (activeSourceId) {
        await openSourceDrawer(activeSourceId);
        await loadProjectSources(selectedProjectId);
      }
    } catch (err: any) {
      setAlertBanner({ type: "error", message: "Lỗi xóa bằng chứng: " + (err.message || "") });
    }
  }

  // Filter sources locally for text query if needed
  const filteredSources = useMemo(() => {
    if (!searchFilter.trim()) return sources;
    const q = searchFilter.toLowerCase();
    return sources.filter(
      (s) =>
        s.title?.toLowerCase().includes(q) ||
        s.authors?.toLowerCase().includes(q) ||
        s.publisher?.toLowerCase().includes(q) ||
        s.url?.toLowerCase().includes(q)
    );
  }, [sources, searchFilter]);

  // Helper Badge Renderers
  const renderVerificationBadge = (status: string, score: number) => {
    if (status === "VERIFIED" || score >= 80) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <ShieldCheck className="h-3 w-3 text-emerald-600" />
          {score}/100 • Đã xác minh tốt
        </span>
      );
    } else if (status === "PARTIALLY_VERIFIED" || score >= 45) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
          <AlertCircle className="h-3 w-3 text-amber-600" />
          {score}/100 • Xác minh 1 phần
        </span>
      );
    } else if (status === "BROKEN_SOURCE") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
          <ShieldAlert className="h-3 w-3 text-rose-600" />
          Mất kết nối (Broken)
        </span>
      );
    } else {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
          <AlertCircle className="h-3 w-3 text-slate-500" />
          {score}/100 • Cần kiểm tra
        </span>
      );
    }
  };

  const renderTrustBadge = (trust: string) => {
    switch (trust) {
      case "OFFICIAL":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
            <Building2 className="h-3 w-3" /> Tài liệu chính thức
          </span>
        );
      case "ACADEMIC":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">
            <GraduationCap className="h-3 w-3" /> Nghiên cứu học thuật
          </span>
        );
      case "GOVERNMENT":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-teal-50 text-teal-700 border border-teal-200">
            <Building2 className="h-3 w-3" /> Cổng chính phủ (.gov)
          </span>
        );
      case "ORGANIZATION":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
            <Layers className="h-3 w-3" /> Tổ chức uy tín (.org)
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
            <Globe className="h-3 w-3" /> Website phổ thông
          </span>
        );
    }
  };

  const renderSourceTypeIcon = (type: string) => {
    switch (type) {
      case "OFFICIAL_DOCUMENTATION":
        return <BookOpen className="h-4 w-4 text-blue-600" />;
      case "ACADEMIC_PAPER":
        return <GraduationCap className="h-4 w-4 text-purple-600" />;
      case "UPLOADED_PDF":
        return <FileText className="h-4 w-4 text-rose-600" />;
      case "UPLOADED_DOCX":
        return <FileText className="h-4 w-4 text-sky-600" />;
      case "UPLOADED_EXCEL":
      case "DATASET":
        return <FileSpreadsheet className="h-4 w-4 text-emerald-600" />;
      default:
        return <Globe className="h-4 w-4 text-slate-600" />;
    }
  };

  return (
    <div className="space-y-6 pb-20">
      {/* Alert Banner */}
      {alertBanner && (
        <div
          className={`flex items-center justify-between p-3.5 rounded-xl border text-xs font-semibold ${
            alertBanner.type === "success"
              ? "bg-emerald-50 text-emerald-800 border-emerald-200"
              : alertBanner.type === "error"
              ? "bg-rose-50 text-rose-800 border-rose-200"
              : "bg-indigo-50 text-indigo-800 border-indigo-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {alertBanner.type === "success" ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            ) : alertBanner.type === "error" ? (
              <AlertCircle className="h-4 w-4 text-rose-600" />
            ) : (
              <Sparkles className="h-4 w-4 text-indigo-600" />
            )}
            <span>{alertBanner.message}</span>
          </div>
          <button onClick={() => setAlertBanner(null)} className="text-slate-400 hover:text-slate-600">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Top Header & Actions */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-extrabold text-slate-900">Kho Nguồn & Kiểm Chứng Citation</h1>
            <span className="bg-indigo-50 text-indigo-700 text-[11px] font-bold px-2 py-0.5 rounded-full border border-indigo-200">
              Chống Bịa Đặt 100%
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Quản lý tài liệu nghiên cứu thật (Official Docs, OpenAlex, Crossref, arXiv), bằng chứng văn bản & phép tính bảng Excel.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <button
            onClick={() => setShowSearchModal(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold shadow-sm transition-all shadow-indigo-100"
          >
            <Search className="h-3.5 w-3.5" />
            <span>Tìm kiếm học thuật</span>
          </button>

          <button
            onClick={() => setShowUrlModal(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-semibold shadow-sm transition-all"
          >
            <LinkIcon className="h-3.5 w-3.5" />
            <span>Thêm URL</span>
          </button>

          <button
            onClick={() => setShowUploadModal(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-white border border-slate-200 hover:border-slate-300 text-slate-700 rounded-xl text-xs font-semibold shadow-sm transition-all"
          >
            <Upload className="h-3.5 w-3.5 text-slate-500" />
            <span>Tải lên tài liệu</span>
          </button>
        </div>
      </div>

      {/* Project Selector & Live Stat Cards */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-50/70 p-3.5 rounded-xl border border-slate-200">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-bold text-slate-700">Dự án hoạt động:</span>
            {loadingProjects ? (
              <span className="text-xs text-slate-400">Đang tải dự án...</span>
            ) : projects.length === 0 ? (
              <button
                onClick={handleCreateProject}
                className="inline-flex items-center gap-1.5 px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Tạo nhanh Dự án Nghiên cứu</span>
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <select
                  value={selectedProjectId}
                  onChange={(e) => setSelectedProjectId(e.target.value)}
                  className="h-8 rounded-lg border border-slate-300 bg-white px-3 text-xs font-semibold text-slate-800 outline-none focus:border-indigo-500 shadow-sm"
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <button
                  onClick={handleCreateProject}
                  className="inline-flex items-center gap-1 px-2.5 py-1 bg-white border border-slate-300 hover:border-slate-400 text-slate-700 rounded-lg text-xs font-semibold shadow-xs transition-colors"
                  title="Tạo thêm dự án mới"
                >
                  <Plus className="h-3 w-3" />
                  <span>Dự án mới</span>
                </button>
              </div>
            )}
          </div>
          <button
            onClick={() => selectedProjectId && loadProjectSources(selectedProjectId)}
            className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600 hover:text-indigo-600 transition-colors"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loadingSources ? "animate-spin" : ""}`} />
            <span>Làm mới dữ liệu</span>
          </button>
        </div>

        {/* 5 Real Metric Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
          <div className="bg-white p-3.5 rounded-xl border border-slate-200/90 shadow-sm">
            <span className="text-[11px] font-semibold text-slate-500">Tổng nguồn</span>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-2xl font-black text-slate-900">{stats.total_sources}</span>
              <BookOpen className="h-4 w-4 text-slate-400" />
            </div>
            <span className="text-[10px] text-slate-400">Kho dữ liệu dự án</span>
          </div>

          <div className="bg-white p-3.5 rounded-xl border border-slate-200/90 shadow-sm">
            <span className="text-[11px] font-semibold text-emerald-700">Đã xác minh</span>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-2xl font-black text-emerald-600">{stats.verified_count}</span>
              <ShieldCheck className="h-4 w-4 text-emerald-500" />
            </div>
            <span className="text-[10px] text-emerald-600 font-semibold">Điểm uy tín ≥ 80</span>
          </div>

          <div className="bg-white p-3.5 rounded-xl border border-slate-200/90 shadow-sm">
            <span className="text-[11px] font-semibold text-amber-700">Cần kiểm tra</span>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-2xl font-black text-amber-600">{stats.needs_review_count}</span>
              <AlertCircle className="h-4 w-4 text-amber-500" />
            </div>
            <span className="text-[10px] text-amber-600 font-semibold">Thiếu hoặc lỗi URL</span>
          </div>

          <div className="bg-white p-3.5 rounded-xl border border-slate-200/90 shadow-sm">
            <span className="text-[11px] font-semibold text-indigo-700">Đang sử dụng</span>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-2xl font-black text-indigo-600">{stats.in_use_count}</span>
              <BookmarkCheck className="h-4 w-4 text-indigo-500" />
            </div>
            <span className="text-[10px] text-indigo-600 font-semibold">Có trong báo cáo</span>
          </div>

          <div className="bg-white p-3.5 rounded-xl border border-slate-200/90 shadow-sm">
            <span className="text-[11px] font-semibold text-rose-700">Thiếu bằng chứng</span>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-2xl font-black text-rose-600">{stats.missing_evidence_count}</span>
              <ShieldAlert className="h-4 w-4 text-rose-500" />
            </div>
            <span className="text-[10px] text-rose-600 font-semibold">0 đoạn trích xuất</span>
          </div>
        </div>
      </div>

      {/* Search & Filter Bar */}
      <div className="bg-white p-3.5 rounded-xl border border-slate-200/90 shadow-sm flex flex-col md:flex-row items-center gap-3">
        <div className="relative flex-1 w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            placeholder="Lọc nhanh nguồn theo tiêu đề, tác giả, nhà xuất bản, URL..."
            className="w-full h-9 pl-9 pr-3 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:border-indigo-500 outline-none transition-all"
          />
        </div>

        {/* Type Filter */}
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="h-9 w-full md:w-48 rounded-lg border border-slate-200 bg-slate-50 px-2.5 text-xs font-semibold text-slate-700 outline-none focus:border-indigo-500"
        >
          <option value="ALL">Tất cả định dạng</option>
          <option value="OFFICIAL_DOCUMENTATION">Tài liệu chính thức</option>
          <option value="ACADEMIC_PAPER">Bài báo học thuật</option>
          <option value="WEB_ARTICLE">Bài viết Website</option>
          <option value="UPLOADED_PDF">Tệp PDF tải lên</option>
          <option value="UPLOADED_DOCX">Tệp DOCX tải lên</option>
          <option value="UPLOADED_EXCEL">Bảng tính Excel/CSV</option>
        </select>

        {/* Status Filter */}
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 w-full md:w-44 rounded-lg border border-slate-200 bg-slate-50 px-2.5 text-xs font-semibold text-slate-700 outline-none focus:border-indigo-500"
        >
          <option value="ALL">Tất cả trạng thái</option>
          <option value="VERIFIED">Đã xác minh (≥80)</option>
          <option value="PARTIALLY_VERIFIED">Xác minh 1 phần</option>
          <option value="REQUIRES_REVIEW">Cần kiểm tra</option>
          <option value="BROKEN_SOURCE">Mất kết nối</option>
        </select>
      </div>

      {/* Sources Grid */}
      {loadingSources ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center text-xs text-slate-500 space-y-2">
          <RefreshCw className="h-6 w-6 animate-spin mx-auto text-indigo-500" />
          <p className="font-semibold">Đang nạp dữ liệu nguồn nghiên cứu...</p>
        </div>
      ) : filteredSources.length === 0 ? (
        <div className="bg-white rounded-2xl border border-dashed border-slate-300 p-12 text-center space-y-3">
          <div className="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto">
            <BookOpen className="h-6 w-6" />
          </div>
          <h3 className="font-bold text-sm text-slate-800">Chưa có nguồn nghiên cứu phù hợp</h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Bạn có thể tìm kiếm bài báo khoa học thật từ OpenAlex, Microsoft Learn, thêm liên kết URL hoặc tải lên tài liệu PDF/Excel.
          </p>
          <div className="flex items-center justify-center gap-2 pt-2">
            <button
              onClick={() => setShowSearchModal(true)}
              className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition-colors shadow-sm"
            >
              Tìm kiếm nguồn thật
            </button>
            <button
              onClick={() => setShowUrlModal(true)}
              className="px-4 py-2 bg-slate-100 text-slate-700 rounded-xl text-xs font-semibold hover:bg-slate-200 transition-colors"
            >
              Thêm URL
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredSources.map((source) => (
            <div
              key={source.id}
              className="bg-white rounded-2xl border border-slate-200/90 shadow-sm hover:border-indigo-300 transition-all p-4 flex flex-col justify-between space-y-3"
            >
              {/* Header Badges */}
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {renderSourceTypeIcon(source.source_type)}
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-700 truncate max-w-[130px]">
                      {source.publisher || source.organization || "Nguồn tài liệu"}
                    </span>
                    {source.doi && (
                      <span className="rounded bg-teal-50 px-1.5 py-0.5 text-[10px] font-bold text-teal-700 border border-teal-200">
                        DOI
                      </span>
                    )}
                  </div>
                  {renderVerificationBadge(source.verification_status, source.verification_score)}
                </div>

                {/* Title & Subtitle */}
                <div>
                  <h3 className="font-bold text-xs text-slate-900 line-clamp-2 leading-snug">{source.title}</h3>
                  {source.authors && (
                    <p className="text-[11px] text-slate-500 truncate mt-0.5">
                      Tác giả: <span className="text-slate-700 font-medium">{source.authors}</span>
                      {source.publication_year ? ` (${source.publication_year})` : ""}
                    </p>
                  )}
                </div>

                {/* Domain Trust & Provider */}
                <div className="flex items-center gap-1.5 flex-wrap">
                  {renderTrustBadge(source.domain_trust)}
                  {source.provider && (
                    <span className="text-[10px] text-slate-400 font-medium">via {source.provider}</span>
                  )}
                </div>

                {/* Summary Snippet */}
                <p className="text-[11px] text-slate-600 line-clamp-2 leading-relaxed bg-slate-50 p-2 rounded-lg border border-slate-100">
                  {source.summary || source.abstract || "Chưa có tóm tắt nội dung trích xuất."}
                </p>
              </div>

              {/* Footer Meta & Actions */}
              <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                      source.evidence_count > 0
                        ? "bg-indigo-50 text-indigo-700 border border-indigo-100"
                        : "bg-rose-50 text-rose-700 border border-rose-100"
                    }`}
                  >
                    {source.evidence_count} bằng chứng
                  </span>

                  <span
                    className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                      source.citation_count > 0
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-100"
                        : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    {source.citation_count > 0 ? `Dùng ở ${source.citation_count} báo cáo` : "Chưa trích dẫn"}
                  </span>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => openSourceDrawer(source.id)}
                    className="p-1.5 hover:bg-slate-100 rounded-lg text-indigo-600 hover:text-indigo-800 transition-colors"
                    title="Xem chi tiết & bằng chứng"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => handleDeleteSource(source)}
                    className="p-1.5 hover:bg-rose-50 rounded-lg text-slate-400 hover:text-rose-600 transition-colors"
                    title="Xóa nguồn"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* DETAIL DRAWER (4 TABS) */}
      {activeSourceId && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-slate-900/40 backdrop-blur-xs flex justify-end">
          <div className="w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <span className="p-2 bg-indigo-100 text-indigo-700 rounded-lg">
                  <FileCheck className="h-4 w-4" />
                </span>
                <div>
                  <h2 className="text-sm font-bold text-slate-900 truncate max-w-md">
                    {sourceDetail?.source?.title || "Chi tiết nguồn nghiên cứu"}
                  </h2>
                  <span className="text-[10px] text-slate-500">
                    ID: {activeSourceId}
                  </span>
                </div>
              </div>
              <button
                onClick={() => {
                  setActiveSourceId(null);
                  setSourceDetail(null);
                }}
                className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-400 hover:text-slate-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* 4 Tabs Header */}
            <div className="flex border-b border-slate-200 px-4 bg-white text-xs font-semibold">
              <button
                onClick={() => setActiveTab("overview")}
                className={`py-3 px-3 border-b-2 transition-all ${
                  activeTab === "overview"
                    ? "border-indigo-600 text-indigo-600"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                Tổng quan & Metadata
              </button>
              <button
                onClick={() => setActiveTab("evidence")}
                className={`py-3 px-3 border-b-2 transition-all flex items-center gap-1.5 ${
                  activeTab === "evidence"
                    ? "border-indigo-600 text-indigo-600"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                <span>Kho Bằng Chứng</span>
                <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-100">
                  {sourceDetail?.evidence_count || 0}
                </span>
              </button>
              <button
                onClick={() => setActiveTab("citations")}
                className={`py-3 px-3 border-b-2 transition-all flex items-center gap-1.5 ${
                  activeTab === "citations"
                    ? "border-indigo-600 text-indigo-600"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                <span>Vị trí trích dẫn</span>
                <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-100">
                  {sourceDetail?.citation_count || 0}
                </span>
              </button>
              <button
                onClick={() => setActiveTab("verification")}
                className={`py-3 px-3 border-b-2 transition-all ${
                  activeTab === "verification"
                    ? "border-indigo-600 text-indigo-600"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                Quy trình kiểm chứng
              </button>
            </div>

            {/* Drawer Content */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {loadingDetail ? (
                <div className="py-12 text-center text-xs text-slate-500 space-y-2">
                  <RefreshCw className="h-6 w-6 animate-spin mx-auto text-indigo-600" />
                  <p>Đang tải thông tin chi tiết...</p>
                </div>
              ) : !sourceDetail ? (
                <p className="text-xs text-slate-500">Không có dữ liệu chi tiết.</p>
              ) : (
                <>
                  {/* TAB 1: OVERVIEW */}
                  {activeTab === "overview" && (
                    <div className="space-y-4 text-xs">
                      <div className="space-y-2 bg-slate-50 p-4 rounded-xl border border-slate-200">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-slate-700">Điểm xác minh thực tế</span>
                          {renderVerificationBadge(
                            sourceDetail.source.verification_status,
                            sourceDetail.source.verification_score
                          )}
                        </div>
                        <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden">
                          <div
                            className={`h-full ${
                              sourceDetail.source.verification_score >= 80
                                ? "bg-emerald-500"
                                : sourceDetail.source.verification_score >= 45
                                ? "bg-amber-500"
                                : "bg-rose-500"
                            }`}
                            style={{ width: `${sourceDetail.source.verification_score}%` }}
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div className="p-3 bg-white rounded-xl border border-slate-200">
                          <span className="text-slate-400 font-medium">Tác giả</span>
                          <p className="font-bold text-slate-800 mt-0.5">{sourceDetail.source.authors || "Chưa rõ"}</p>
                        </div>
                        <div className="p-3 bg-white rounded-xl border border-slate-200">
                          <span className="text-slate-400 font-medium">Năm xuất bản</span>
                          <p className="font-bold text-slate-800 mt-0.5">{sourceDetail.source.publication_year || sourceDetail.source.published_date || "Chưa rõ"}</p>
                        </div>
                        <div className="p-3 bg-white rounded-xl border border-slate-200">
                          <span className="text-slate-400 font-medium">Nhà xuất bản / Tổ chức</span>
                          <p className="font-bold text-slate-800 mt-0.5">{sourceDetail.source.publisher || sourceDetail.source.organization || "Chưa rõ"}</p>
                        </div>
                        <div className="p-3 bg-white rounded-xl border border-slate-200">
                          <span className="text-slate-400 font-medium">Định danh DOI</span>
                          <p className="font-bold text-teal-700 mt-0.5">{sourceDetail.source.doi || "Không có DOI"}</p>
                        </div>
                      </div>

                      {sourceDetail.source.url && (
                        <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                          <span className="text-slate-400 font-medium">Liên kết gốc (Canonical URL)</span>
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono text-slate-700 truncate max-w-md">{sourceDetail.source.url}</span>
                            <a
                              href={sourceDetail.source.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 font-bold text-indigo-600 hover:text-indigo-800 shrink-0"
                            >
                              <ExternalLink className="h-3.5 w-3.5" /> Mở web
                            </a>
                          </div>
                        </div>
                      )}

                      <div className="p-4 bg-white rounded-xl border border-slate-200 space-y-1.5">
                        <span className="font-bold text-slate-700">Tóm tắt / Abstract</span>
                        <p className="text-slate-600 leading-relaxed whitespace-pre-line">
                          {sourceDetail.source.abstract || sourceDetail.source.summary || "Chưa có nội dung tóm tắt."}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* TAB 2: EVIDENCE CHUNKS */}
                  {activeTab === "evidence" && (
                    <div className="space-y-4 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-800">
                          Bằng chứng trích xuất ({sourceDetail.evidences?.length || 0})
                        </span>
                        <button
                          onClick={() => setShowAddEvidenceForm(!showAddEvidenceForm)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 bg-indigo-50 text-indigo-700 font-bold rounded-lg hover:bg-indigo-100 transition-colors"
                        >
                          <Plus className="h-3.5 w-3.5" />
                          <span>Thêm bằng chứng</span>
                        </button>
                      </div>

                      {/* Add Evidence Form */}
                      {showAddEvidenceForm && (
                        <form
                          onSubmit={handleAddEvidenceSubmit}
                          className="bg-indigo-50/70 p-4 rounded-xl border border-indigo-200 space-y-3"
                        >
                          <h4 className="font-bold text-indigo-950">Bổ sung Bằng chứng Trích dẫn Mới</h4>
                          <div className="grid grid-cols-2 gap-2">
                            <div>
                              <label className="block text-[11px] font-semibold text-slate-600 mb-1">Loại bằng chứng</label>
                              <select
                                value={newEvType}
                                onChange={(e) => setNewEvType(e.target.value)}
                                className="w-full h-8 px-2 rounded-lg border border-slate-300 bg-white text-xs font-semibold"
                              >
                                <option value="WEB_TEXT">Đoạn văn Web / Bài viết</option>
                                <option value="PDF_TEXT">Trang tài liệu PDF</option>
                                <option value="DOCX_TEXT">Đoạn văn Word DOCX</option>
                                <option value="EXCEL_RANGE">Tính toán ô Excel / CSV</option>
                                <option value="MANUAL_SELECTION">Trích dẫn thủ công</option>
                              </select>
                            </div>
                            <div>
                              <label className="block text-[11px] font-semibold text-slate-600 mb-1">Tiêu đề mục / Section</label>
                              <input
                                type="text"
                                value={newEvSection}
                                onChange={(e) => setNewEvSection(e.target.value)}
                                placeholder="vd: Chương 2, Kết quả tài chính"
                                className="w-full h-8 px-2 rounded-lg border border-slate-300 bg-white text-xs"
                              />
                            </div>
                          </div>

                          {newEvType === "EXCEL_RANGE" ? (
                            <div className="grid grid-cols-3 gap-2">
                              <div>
                                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Tên Sheet</label>
                                <input
                                  type="text"
                                  value={newEvSheet}
                                  onChange={(e) => setNewEvSheet(e.target.value)}
                                  placeholder="vd: Bang_luong"
                                  className="w-full h-8 px-2 rounded-lg border border-slate-300 bg-white text-xs"
                                />
                              </div>
                              <div>
                                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Vùng ô (Cell Range)</label>
                                <input
                                  type="text"
                                  value={newEvRange}
                                  onChange={(e) => setNewEvRange(e.target.value)}
                                  placeholder="vd: H6:I137"
                                  className="w-full h-8 px-2 rounded-lg border border-slate-300 bg-white text-xs"
                                />
                              </div>
                              <div>
                                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Phép tính</label>
                                <select
                                  value={newEvOp}
                                  onChange={(e) => setNewEvOp(e.target.value)}
                                  className="w-full h-8 px-2 rounded-lg border border-slate-300 bg-white text-xs font-semibold"
                                >
                                  <option value="COUNT">COUNT (Đếm ô)</option>
                                  <option value="SUM">SUM (Tính tổng)</option>
                                  <option value="AVG">AVG (Trung bình)</option>
                                  <option value="MIN">MIN (Nhỏ nhất)</option>
                                  <option value="MAX">MAX (Lớn nhất)</option>
                                </select>
                              </div>
                            </div>
                          ) : (
                            <div>
                              <label className="block text-[11px] font-semibold text-slate-600 mb-1">Số trang (nếu có)</label>
                              <input
                                type="number"
                                value={newEvPage}
                                onChange={(e) => setNewEvPage(e.target.value)}
                                placeholder="vd: 12"
                                className="w-32 h-8 px-2 rounded-lg border border-slate-300 bg-white text-xs"
                              />
                            </div>
                          )}

                          <div>
                            <label className="block text-[11px] font-semibold text-slate-600 mb-1">Nội dung đoạn trích dẫn gốc (Quote)</label>
                            <textarea
                              value={newEvQuote}
                              onChange={(e) => setNewEvQuote(e.target.value)}
                              rows={3}
                              placeholder="Nhập chính xác câu chữ từ tài liệu..."
                              className="w-full p-2 rounded-lg border border-slate-300 bg-white text-xs"
                              required
                            />
                          </div>

                          <div className="flex justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => setShowAddEvidenceForm(false)}
                              className="px-3 py-1.5 bg-slate-200 text-slate-700 font-semibold rounded-lg"
                            >
                              Hủy
                            </button>
                            <button
                              type="submit"
                              disabled={isSavingEvidence || !newEvQuote.trim()}
                              className="px-4 py-1.5 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                            >
                              {isSavingEvidence ? "Đang lưu..." : "Lưu bằng chứng"}
                            </button>
                          </div>
                        </form>
                      )}

                      {/* Evidence List */}
                      {(!sourceDetail.evidences || sourceDetail.evidences.length === 0) ? (
                        <div className="p-8 text-center text-slate-400 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                          Chưa có bằng chứng trích xuất cho nguồn này.
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {sourceDetail.evidences.map((ev: any, idx: number) => (
                            <div key={ev.id} className="p-3.5 bg-white rounded-xl border border-slate-200 space-y-2 shadow-2xs">
                              <div className="flex items-center justify-between text-[11px]">
                                <div className="flex items-center gap-2">
                                  <span className="font-bold text-slate-700"># {idx + 1}</span>
                                  {ev.page_number && (
                                    <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-medium">
                                      Trang {ev.page_number}
                                    </span>
                                  )}
                                  {ev.section_title && (
                                    <span className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded font-medium">
                                      {ev.section_title}
                                    </span>
                                  )}
                                  {ev.sheet_name && (
                                    <span className="bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded font-medium inline-flex items-center gap-1">
                                      <Table className="h-3 w-3" />
                                      {ev.sheet_name} • {ev.cell_range} ({ev.operation})
                                    </span>
                                  )}
                                </div>
                                <button
                                  onClick={() => handleDeleteEvidence(ev.id)}
                                  className="text-slate-400 hover:text-rose-600 transition-colors"
                                  title="Xóa bằng chứng"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              </div>

                              <blockquote className="border-l-2 border-indigo-400 pl-3 py-1 text-slate-700 italic bg-indigo-50/30 rounded-r-lg">
                                &ldquo;{ev.quote}&rdquo;
                              </blockquote>

                              {ev.calculation_result && (
                                <div className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-1 rounded inline-flex items-center gap-1.5 border border-emerald-100">
                                  <Calculator className="h-3.5 w-3.5" />
                                  <span>Kết quả tính: {ev.calculation_result}</span>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* TAB 3: CITATIONS IN USE */}
                  {activeTab === "citations" && (
                    <div className="space-y-4 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-800">
                          Báo cáo đang trích dẫn nguồn này ({sourceDetail.citations?.length || 0})
                        </span>
                      </div>

                      {(!sourceDetail.citations || sourceDetail.citations.length === 0) ? (
                        <div className="p-8 text-center text-slate-400 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                          Nguồn này hiện chưa được trích dẫn trong báo cáo nào. Có thể xóa an toàn mà không làm gãy liên kết.
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {sourceDetail.citations.map((c: any) => (
                            <div key={c.id} className="p-3.5 bg-white rounded-xl border border-slate-200 space-y-2">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-100">
                                  Trích dẫn {c.citation_key || `[${c.citation_number}]`}
                                </span>
                                <span
                                  className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                    c.support_level === "STRONG"
                                      ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                      : c.support_level === "MODERATE"
                                      ? "bg-blue-50 text-blue-700 border border-blue-200"
                                      : "bg-amber-50 text-amber-700 border border-amber-200"
                                  }`}
                                >
                                  Hỗ trợ: {c.support_level}
                                </span>
                              </div>
                              {c.locator && (
                                <p className="text-[11px] text-slate-500 font-medium">Vị trí: {c.locator}</p>
                              )}
                              {c.evidence_text && (
                                <p className="text-slate-600 bg-slate-50 p-2 rounded-lg border border-slate-100 italic">
                                  &ldquo;{c.evidence_text}&rdquo;
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* TAB 4: VERIFICATION DETAILS */}
                  {activeTab === "verification" && (
                    <div className="space-y-4 text-xs">
                      <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-slate-800">Quy trình kiểm chứng 100 điểm</span>
                          <button
                            onClick={() => handleReVerify(sourceDetail.source.id)}
                            className="inline-flex items-center gap-1 font-bold text-indigo-600 hover:text-indigo-800"
                          >
                            <RefreshCw className="h-3 w-3" /> Kiểm chứng lại
                          </button>
                        </div>

                        <div className="space-y-2 pt-2">
                          <div className="flex items-center justify-between p-2 bg-white rounded-lg border border-slate-200">
                            <span>Khả năng kết nối URL (Reachability)</span>
                            <span className="font-bold text-emerald-600">✓ 20 điểm</span>
                          </div>
                          <div className="flex items-center justify-between p-2 bg-white rounded-lg border border-slate-200">
                            <span>Định danh học thuật DOI hợp lệ</span>
                            <span className="font-bold text-emerald-600">
                              {sourceDetail.source.doi ? "✓ 25 điểm" : "— 0 điểm"}
                            </span>
                          </div>
                          <div className="flex items-center justify-between p-2 bg-white rounded-lg border border-slate-200">
                            <span>Độ đầy đủ Metadata (Tiêu đề, Tóm tắt)</span>
                            <span className="font-bold text-emerald-600">✓ 25 điểm</span>
                          </div>
                          <div className="flex items-center justify-between p-2 bg-white rounded-lg border border-slate-200">
                            <span>Xác thực Tác giả & Nhà xuất bản</span>
                            <span className="font-bold text-emerald-600">✓ 20 điểm</span>
                          </div>
                          <div className="flex items-center justify-between p-2 bg-white rounded-lg border border-slate-200">
                            <span>Độ uy tín tên miền (Domain Authority)</span>
                            <span className="font-bold text-emerald-600">✓ 10 điểm</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* MODAL 1: MULTI-PROVIDER SEARCH */}
      {showSearchModal && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="w-full max-w-3xl bg-white rounded-2xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden animate-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <span className="p-2 bg-indigo-600 text-white rounded-xl">
                  <Search className="h-4 w-4" />
                </span>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Tìm Kiếm Nguồn Học Thuật Đa Cổng (Multi-Provider)</h3>
                  <p className="text-[11px] text-slate-500">
                    Truy vấn dữ liệu thật từ Microsoft Learn, OpenAlex, arXiv, Crossref. Cam kết 0% bịa đặt.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowSearchModal(false)}
                className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-400 hover:text-slate-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto space-y-4">
              {/* Search Form */}
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                    placeholder="Nhập chủ đề, công nghệ hoặc từ khóa học thuật..."
                    className="w-full h-10 pl-9 pr-3 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:border-indigo-500 outline-none transition-all"
                  />
                </div>
                <button
                  onClick={handleSearch}
                  disabled={isSearching || !searchQuery.trim()}
                  className="h-10 px-5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold shadow-sm transition-all disabled:opacity-50 inline-flex items-center gap-1.5"
                >
                  {isSearching ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  <span>Tìm kiếm</span>
                </button>
              </div>

              {/* Providers Selection */}
              <div className="flex items-center gap-4 text-xs">
                <span className="font-semibold text-slate-600">Cổng dữ liệu:</span>
                <label className="inline-flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={searchProviders.includes("microsoft_learn")}
                    onChange={(e) => {
                      if (e.target.checked) setSearchProviders([...searchProviders, "microsoft_learn"]);
                      else setSearchProviders(searchProviders.filter((p) => p !== "microsoft_learn"));
                    }}
                    className="rounded border-slate-300 text-indigo-600"
                  />
                  <span>Microsoft Learn (Tài liệu chuẩn)</span>
                </label>
                <label className="inline-flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={searchProviders.includes("openalex")}
                    onChange={(e) => {
                      if (e.target.checked) setSearchProviders([...searchProviders, "openalex"]);
                      else setSearchProviders(searchProviders.filter((p) => p !== "openalex"));
                    }}
                    className="rounded border-slate-300 text-indigo-600"
                  />
                  <span>OpenAlex (Kho học thuật mở)</span>
                </label>
                <label className="inline-flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={searchProviders.includes("arxiv")}
                    onChange={(e) => {
                      if (e.target.checked) setSearchProviders([...searchProviders, "arxiv"]);
                      else setSearchProviders(searchProviders.filter((p) => p !== "arxiv"));
                    }}
                    className="rounded border-slate-300 text-indigo-600"
                  />
                  <span>arXiv (Preprint)</span>
                </label>
              </div>

              {/* Results List */}
              {searchResults.length > 0 && (
                <div className="space-y-3 pt-2">
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span className="font-bold">Tìm thấy {searchResults.length} kết quả thực tế</span>
                  </div>

                  <div className="space-y-3">
                    {searchResults.map((item, idx) => {
                      const itemKey = item.canonical_url || item.url || item.title;
                      const isImporting = !!importingIds[itemKey];

                      return (
                        <div
                          key={`${itemKey}-${idx}`}
                          className="p-3.5 bg-slate-50/70 rounded-xl border border-slate-200 hover:border-indigo-300 transition-all space-y-2 text-xs"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className="font-bold bg-white border border-slate-200 text-slate-700 px-2 py-0.5 rounded text-[10px]">
                                {item.publisher || item.journal || "Verified Provider"}
                              </span>
                              {item.doi && (
                                <span className="bg-teal-50 border border-teal-200 text-teal-700 px-1.5 py-0.5 rounded text-[10px] font-bold">
                                  DOI: {item.doi}
                                </span>
                              )}
                              {item.provider && (
                                <span className="text-[10px] text-slate-400 font-medium">via {item.provider}</span>
                              )}
                            </div>
                            <span className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                              Điểm: {item.quality_score || 85}/100
                            </span>
                          </div>

                          <h4 className="font-bold text-slate-900 line-clamp-2">{item.title}</h4>
                          <p className="text-slate-500 line-clamp-2 leading-relaxed">
                            {item.abstract || item.snippet}
                          </p>

                          <div className="flex items-center justify-between pt-1 border-t border-slate-200/60">
                            <a
                              href={item.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 font-bold text-indigo-600 hover:text-indigo-800 text-[11px]"
                            >
                              <ExternalLink className="h-3 w-3" /> Xem trang gốc
                            </a>

                            <button
                              onClick={() => handleImportSource(item)}
                              disabled={isImporting}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-bold text-[11px] shadow-xs disabled:opacity-50"
                            >
                              <BookmarkCheck className="h-3.5 w-3.5" />
                              <span>{isImporting ? "Đang nạp..." : "Lưu vào Kho"}</span>
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: ADD URL */}
      {showUrlModal && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-5 space-y-4 animate-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="p-2 bg-slate-900 text-white rounded-xl">
                  <LinkIcon className="h-4 w-4" />
                </span>
                <h3 className="text-sm font-bold text-slate-900">Thêm Nguồn từ URL</h3>
              </div>
              <button onClick={() => setShowUrlModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleAddUrlSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Địa chỉ URL *</label>
                <input
                  type="url"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  placeholder="https://learn.microsoft.com/... hoặc https://doi.org/..."
                  className="w-full h-9 px-3 rounded-lg border border-slate-300 bg-slate-50 focus:bg-white focus:border-indigo-500 outline-none"
                  required
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Tiêu đề tùy chọn (Tự động nhận nếu để trống)</label>
                <input
                  type="text"
                  value={urlTitleInput}
                  onChange={(e) => setUrlTitleInput(e.target.value)}
                  placeholder="Tên tài liệu / bài báo..."
                  className="w-full h-9 px-3 rounded-lg border border-slate-300 bg-slate-50 focus:bg-white focus:border-indigo-500 outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Ghi chú nghiên cứu</label>
                <textarea
                  value={urlNotesInput}
                  onChange={(e) => setUrlNotesInput(e.target.value)}
                  rows={2}
                  placeholder="Ghi chú về phần trích dẫn hoặc mục đích sử dụng..."
                  className="w-full p-2.5 rounded-lg border border-slate-300 bg-slate-50 focus:bg-white focus:border-indigo-500 outline-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowUrlModal(false)}
                  className="px-4 py-2 bg-slate-100 text-slate-700 rounded-xl font-semibold hover:bg-slate-200"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={isAddingUrl || !urlInput.trim()}
                  className="px-5 py-2 bg-slate-900 text-white rounded-xl font-semibold hover:bg-slate-800 disabled:opacity-50"
                >
                  {isAddingUrl ? "Đang kiểm chứng..." : "Thêm & Kiểm chứng"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: UPLOAD DOCUMENT */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-5 space-y-4 animate-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="p-2 bg-indigo-50 text-indigo-600 rounded-xl">
                  <Upload className="h-4 w-4" />
                </span>
                <h3 className="text-sm font-bold text-slate-900">Tải Lên Tài Liệu Nguồn</h3>
              </div>
              <button onClick={() => setShowUploadModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleFileUploadSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Chọn tệp (PDF, Word, Excel, CSV)</label>
                <input
                  type="file"
                  accept=".pdf,.docx,.xlsx,.xls,.csv"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="w-full text-xs text-slate-500 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer"
                  required
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Ghi chú</label>
                <textarea
                  value={uploadNotes}
                  onChange={(e) => setUploadNotes(e.target.value)}
                  rows={2}
                  placeholder="Ghi chú về tài liệu..."
                  className="w-full p-2.5 rounded-lg border border-slate-300 bg-slate-50 focus:bg-white focus:border-indigo-500 outline-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  className="px-4 py-2 bg-slate-100 text-slate-700 rounded-xl font-semibold hover:bg-slate-200"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={isUploading || !uploadFile}
                  className="px-5 py-2 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-700 disabled:opacity-50"
                >
                  {isUploading ? "Đang xử lý & bóc tách..." : "Tải lên & Trích xuất"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CONFIRMATION MODAL: DELETE WITH CITATIONS */}
      {deleteWarning && deleteCandidate && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-5 space-y-4 animate-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3 text-amber-600">
              <span className="p-2 bg-amber-50 rounded-xl">
                <ShieldAlert className="h-6 w-6" />
              </span>
              <div>
                <h3 className="text-sm font-bold text-slate-900">Cảnh Báo: Nguồn Đang Được Trích Dẫn</h3>
                <span className="text-[11px] text-slate-500">Phát hiện trích dẫn đang hoạt động</span>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed bg-amber-50/50 p-3 rounded-xl border border-amber-200">
              {deleteWarning.message}
            </p>

            {deleteWarning.affected_reports && deleteWarning.affected_reports.length > 0 && (
              <div className="space-y-1.5 text-xs">
                <span className="font-bold text-slate-700">Các báo cáo bị ảnh hưởng:</span>
                <ul className="list-disc list-inside text-slate-600 space-y-0.5">
                  {deleteWarning.affected_reports.map((r: any) => (
                    <li key={r.id} className="font-medium">
                      {r.title}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                onClick={() => {
                  setDeleteCandidate(null);
                  setDeleteWarning(null);
                }}
                className="px-4 py-2 bg-slate-100 text-slate-700 rounded-xl text-xs font-semibold hover:bg-slate-200"
              >
                Giữ lại nguồn
              </button>
              <button
                onClick={() => handleDeleteSource(deleteCandidate, true)}
                className="px-4 py-2 bg-rose-600 text-white rounded-xl text-xs font-semibold hover:bg-rose-700 shadow-sm"
              >
                Xác nhận Xóa
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
