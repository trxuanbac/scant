"use client";

import { GoogleDataConnection } from "@/components/GoogleDataConnection";

import { useCallback, useState, useEffect, Suspense, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Briefcase,
  TrendingUp,
  Search,
  FileText,
  Sparkles,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  Trash2,
  Upload,
  Layers,
  Wand2,
  Play,
  Pause,
  RotateCcw,
  XCircle,
  Table,
  Check,
  RefreshCw,
  ExternalLink,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { api, API_BASE } from "@/lib/api";
import {
  buildAutoJobSnapshot,
  canSafelySwitchAutoContext,
  shouldRestoreAutoJob,
} from "@/lib/autoJobState";
import { formatUnknownError } from "@/lib/apiErrors";
import { buildDatasetSourcePromptParts, hasDatasetSource } from "@/lib/datasetSource";
import { getVisibleProjectTypes, normalizeNewProjectType } from "@/lib/productFocus";
import ExcelAnalysisWorkspace from "@/components/ExcelAnalysisWorkspace";
import DirectAnalysisPromptPanel from "@/components/DirectAnalysisPromptPanel";
import { resolveSelectedSheetName } from "@/lib/directAnalysisPreview";
import { useTranslation } from "@/i18n/I18nContext";
import { DataAnalysisModeSelection, type DataAnalysisMode } from "@/components/DataAnalysisModeSelection";
import { readAnalysisMode, analysisModeUrl, readDatasetId } from "@/lib/dataAnalysisNavigation";
import { useModeStore } from "@/stores/useModeStore";

interface CustomFieldItem {
  key: string;
  label: string;
  type: string;
  required: boolean;
  value: any;
  unit?: string;
}

interface OutlineItemUI {
  title: string;
  level: number;
  position: number;
  section_number?: string;
  description?: string;
  children: OutlineItemUI[];
}

const PROJECT_TYPE_META = [
  { id: "business_report", icon: Briefcase, color: "text-blue-600 bg-blue-50" },
  { id: "data_analysis", icon: TrendingUp, color: "text-emerald-600 bg-emerald-50" },
  { id: "research", icon: Search, color: "text-indigo-600 bg-indigo-50" },
  { id: "custom", icon: FileText, color: "text-slate-600 bg-slate-50" },
].filter(({ id }) => getVisibleProjectTypes().includes(id));

const PROJECT_TYPE_GUIDE = {
  vi: {
    business_report: {
      bestFor: "Chiến lược, vận hành, kế hoạch tăng trưởng",
      output: "Tóm tắt điều hành, phân tích hiện trạng, KPI, lộ trình",
      example: "Kế hoạch kinh doanh 2026",
      badge: "Quản trị",
    },
    data_analysis: {
      bestFor: "Có file Excel/CSV, số liệu, KPI cần phân tích",
      output: "Bảng thống kê, biểu đồ, nhận xét dữ liệu, kết luận",
      example: "Phân tích doanh thu theo quý",
      badge: "Số liệu",
    },
    research: {
      bestFor: "Đề tài học thuật, tiểu luận, nghiên cứu chuyên sâu",
      output: "Cơ sở lý thuyết, phương pháp, phân tích, kết luận",
      example: "So sánh ARM và x86",
      badge: "Học thuật",
    },
    technical: {
      bestFor: "Hệ thống, phần mềm, API, máy chủ, mạng, triển khai",
      output: "Kiến trúc, yêu cầu, thiết kế, cài đặt, kiểm thử",
      example: "Triển khai ứng dụng lên server",
      badge: "Kỹ thuật",
    },
    proposal: {
      bestFor: "Chào thầu, đề xuất dự án, xin ngân sách",
      output: "Mục tiêu, phạm vi, giải pháp, nhân sự, chi phí",
      example: "Hồ sơ đề xuất xây dựng hệ thống",
      badge: "Đề xuất",
    },
    financial: {
      bestFor: "Doanh thu, chi phí, dòng tiền, kế hoạch tài chính",
      output: "Bảng tài chính, KPI, dự báo, rủi ro, khuyến nghị",
      example: "Báo cáo tài chính quý",
      badge: "Tài chính",
    },
    market_research: {
      bestFor: "Thị trường, khách hàng, đối thủ, chiến lược thâm nhập",
      output: "Quy mô thị trường, phân khúc, đối thủ, chân dung khách hàng",
      example: "Nghiên cứu thị trường xe điện",
      badge: "Thị trường",
    },
    custom: {
      bestFor: "Không chắc chọn loại nào hoặc tài liệu rất đặc thù",
      output: "AI tự suy luận cấu trúc phù hợp từ yêu cầu của bạn",
      example: "Tài liệu theo yêu cầu riêng",
      badge: "Linh hoạt",
    },
  },
  en: {
    business_report: {
      bestFor: "Strategy, operations, and growth planning",
      output: "Executive summary, current state, KPIs, roadmap",
      example: "2026 business plan",
      badge: "Management",
    },
    data_analysis: {
      bestFor: "Excel/CSV data, metrics, and KPI analysis",
      output: "Statistical tables, charts, data insights, conclusion",
      example: "Quarterly revenue analysis",
      badge: "Data",
    },
    research: {
      bestFor: "Academic topics, essays, and deep research",
      output: "Theory, methodology, analysis, conclusion",
      example: "ARM vs x86 comparison",
      badge: "Academic",
    },
    technical: {
      bestFor: "Systems, software, APIs, servers, networking",
      output: "Architecture, requirements, design, setup, testing",
      example: "Deploying an app to a server",
      badge: "Technical",
    },
    proposal: {
      bestFor: "Bids, proposals, project approval, budgeting",
      output: "Objective, scope, solution, staffing, cost",
      example: "System implementation proposal",
      badge: "Proposal",
    },
    financial: {
      bestFor: "Revenue, cost, cash flow, financial planning",
      output: "Financial tables, KPIs, forecast, risks, recommendations",
      example: "Quarterly financial report",
      badge: "Finance",
    },
    market_research: {
      bestFor: "Market, customers, competitors, entry strategy",
      output: "Market size, segments, competitors, customer profile",
      example: "EV market research",
      badge: "Market",
    },
    custom: {
      bestFor: "Unclear category or highly specific document",
      output: "AI infers the most suitable structure from your request",
      example: "Custom document request",
      badge: "Flexible",
    },
  },
} as const;

const MODULE_SCREEN_COPY = {
  vi: {
    business_report: {
      title: "Màn Báo cáo Doanh nghiệp",
      desc: "Dành cho báo cáo quản trị, đề xuất chiến lược, phân tích thị trường và tài liệu điều hành.",
      input: "Nhập mục tiêu, phạm vi doanh nghiệp, phòng ban phụ trách và kết quả mong muốn.",
      files: "Tùy chọn tải thêm tài liệu nguồn hoặc file mẫu DOCX của doanh nghiệp.",
      primary: "Mở màn báo cáo doanh nghiệp",
      prompt: "Tạo báo cáo chiến lược doanh nghiệp năm 2026, đánh giá cơ hội tăng trưởng, rủi ro vận hành và lộ trình triển khai chi tiết.",
    },
    data_analysis: {
      title: "Màn Phân tích Dữ liệu",
      desc: "Dành cho đối chiếu số liệu, phân tích KPI, kiểm tra chất lượng dữ liệu và trực quan hóa bảng biểu.",
      input: "Tải file dữ liệu hoặc dán link Google Sheets/CSV công khai, sau đó chọn phân tích trực tiếp hoặc xuất báo cáo.",
      files: "Bắt buộc có file bảng tính CSV/XLSX/XLS hoặc link dữ liệu công khai.",
      primary: "Mở màn phân tích dữ liệu",
      prompt: "Phân tích số liệu bảng tính, đánh giá chỉ số KPI, phát hiện điểm bất thường và đối chiếu các trường dữ liệu quan trọng.",
    },
    research: {
      title: "Màn Báo cáo Nghiên cứu",
      desc: "Dành cho nghiên cứu chuyên sâu, luận văn, khảo sát thị trường và báo cáo học thuật.",
      input: "Nhập câu hỏi nghiên cứu, phương pháp luận, phạm vi đối tượng và cấu trúc dự kiến.",
      files: "Tùy chọn tải thêm tài liệu tham khảo, bài báo khoa học hoặc mẫu Word.",
      primary: "Mở màn nghiên cứu",
      prompt: "Tạo báo cáo nghiên cứu chuyên sâu về xu hướng chuyển đổi số, tổng quan tài liệu, phương pháp nghiên cứu và hàm ý chính sách.",
    },
    technical: {
      title: "Màn Tài liệu Kỹ thuật",
      desc: "Dành cho kiến trúc hệ thống, đặc tả API, hướng dẫn triển khai và tài liệu phần mềm.",
      input: "Nhập kiến trúc hệ thống, thành phần công nghệ, luồng xử lý và tiêu chuẩn kỹ thuật.",
      files: "Tùy chọn tải thêm sơ đồ, file cấu hình, đặc tả API hoặc mẫu tài liệu.",
      primary: "Mở màn tài liệu kỹ thuật",
      prompt: "Tạo tài liệu đặc tả kiến trúc kỹ thuật hệ thống, luồng dữ liệu, bảo mật, hạ tầng đám mây và kế hoạch triển khai.",
    },
    proposal: {
      title: "Màn Đề xuất Dự án / RFP",
      desc: "Dành cho hồ sơ năng lực, đề xuất thầu, kế hoạch triển khai và dự toán ngân sách.",
      input: "Nhập bài toán khách hàng, giải pháp đề xuất, phạm vi công việc và mốc thời gian.",
      files: "Tùy chọn tải thêm hồ sơ yêu cầu (RFP), bảng giá hoặc mẫu thầu DOCX.",
      primary: "Mở màn đề xuất dự án",
      prompt: "Tạo đề xuất giải pháp dự án và kế hoạch triển khai chi tiết, gồm phạm vi công việc, cam kết chất lượng và dự toán kinh phí.",
    },
    financial: {
      title: "Màn Báo cáo Tài chính",
      desc: "Dành cho phân tích kết quả kinh doanh, dòng tiền, định giá và dự báo tài chính.",
      input: "Nhập kỳ báo cáo, đơn vị tiền tệ, các chỉ số trọng yếu và mục tiêu phân tích.",
      files: "Tùy chọn tải thêm bảng cân đối, báo cáo tài chính hoặc mẫu Word tài chính.",
      primary: "Mở màn báo cáo tài chính",
      prompt: "Tạo báo cáo phân tích tài chính toàn diện, đánh giá khả năng sinh lời, dòng tiền, cơ cấu vốn và dự báo tài chính 3 năm.",
    },
    market_research: {
      title: "Màn Nghiên cứu Thị trường",
      desc: "Dành cho phân tích ngành hàng, khách hàng mục tiêu, đối thủ cạnh tranh và dung lượng thị trường.",
      input: "Nhập thị trường mục tiêu, sản phẩm/dịch vụ, khu vực địa lý và mục tiêu nghiên cứu.",
      files: "Tùy chọn tải thêm khảo sát, báo cáo ngành hoặc mẫu Word nghiên cứu.",
      primary: "Mở màn nghiên cứu thị trường",
      prompt: "Tạo báo cáo nghiên cứu thị trường chi tiết về quy mô ngành, phân khúc khách hàng, đối thủ cạnh tranh và chiến lược thâm nhập.",
    },
    custom: {
      title: "Màn Tài liệu Tùy chỉnh",
      desc: "Dành cho các loại văn bản đặc thù theo yêu cầu riêng không thuộc các nhóm trên.",
      input: "Mô tả rõ mục tiêu, đối tượng người đọc, cấu trúc mong muốn và tiêu chí hoàn thành.",
      files: "Tùy chọn tải thêm tài liệu liên quan hoặc file mẫu DOCX định dạng chuẩn.",
      primary: "Mở màn tùy chỉnh",
      prompt: "Tạo tài liệu tùy chỉnh với cấu trúc mạch lạc, đầy đủ nội dung theo yêu cầu và văn phong chuyên nghiệp.",
    },
  },
  en: {
    business_report: {
      title: "Business Report Screen",
      desc: "For management reports, strategic proposals, market analysis, and executive summaries.",
      input: "Enter goals, business scope, responsible department, and desired outputs.",
      files: "Optional source documents or corporate DOCX template.",
      primary: "Open business report screen",
      prompt: "Create a strategic business report for 2026, evaluating growth opportunities, operational risks, and roadmap.",
    },
    data_analysis: {
      title: "Data Analysis Screen",
      desc: "For data reconciliation, KPI analysis, data quality checks, and chart visualization.",
      input: "Upload a dataset file or paste public Google Sheets/CSV link, then choose direct analysis or report generation.",
      files: "Requires CSV/XLSX/XLS dataset file or public data link.",
      primary: "Open data analysis screen",
      prompt: "Analyze spreadsheet data, assess KPIs, detect anomalies, and reconcile critical data fields.",
    },
    research: {
      title: "Research Report Screen",
      desc: "For deep research, theses, market surveys, and academic literature reviews.",
      input: "Enter research questions, methodology, target scope, and proposed outline.",
      files: "Optional references, papers, or Word template.",
      primary: "Open research screen",
      prompt: "Create a deep research report on digital transformation trends, literature review, methodology, and policy implications.",
    },
    technical: {
      title: "Technical Documentation Screen",
      desc: "For system architectures, API specs, deployment guides, and engineering docs.",
      input: "Enter system architecture, tech stack, data pipelines, and engineering standards.",
      files: "Optional diagrams, configs, API specs, or document template.",
      primary: "Open technical screen",
      prompt: "Create technical architecture documentation covering system components, data flows, security, and cloud deployment.",
    },
    proposal: {
      title: "Proposal / RFP Screen",
      desc: "For capability statements, bid proposals, project roadmaps, and budget estimates.",
      input: "Enter client problem, proposed solution, statement of work, and key milestones.",
      files: "Optional RFP documents, pricing tables, or bid DOCX template.",
      primary: "Open proposal screen",
      prompt: "Create a comprehensive project proposal with technical solution, statement of work, timeline, and cost estimate.",
    },
    financial: {
      title: "Financial Report Screen",
      desc: "For business performance, cash flow analysis, valuation, and financial forecasts.",
      input: "Enter reporting period, currency, key ratios, and financial analysis goals.",
      files: "Optional balance sheets, financial statements, or finance Word template.",
      primary: "Open financial screen",
      prompt: "Create a comprehensive financial analysis report evaluating profitability, cash flow, capital structure, and 3-year forecasts.",
    },
    market_research: {
      title: "Market Research Screen",
      desc: "For markets, customers, competitors, segmentation, and entry strategy.",
      input: "Enter target market, product, region, customer group, and research goal.",
      files: "Optional surveys, market data, competitor reports, or Word template.",
      primary: "Open market research screen",
      prompt: "Create a market research report with market size, segments, competitors, customer profile, opportunities, risks, and entry strategy.",
    },
    custom: {
      title: "Custom Document Screen",
      desc: "For special documents that do not fit another module.",
      input: "Clearly enter goal, audience, desired structure, and completion criteria.",
      files: "Optional source documents or related Word template.",
      primary: "Open custom screen",
      prompt: "Create a custom document with clear structure, complete content, and professional formatting.",
    },
  },
} as const;

const WIZARD_COPY = {
  vi: {
    defaultPrompt: "Phân tích thị trường xe điện Việt Nam năm 2026 và đề xuất chiến lược thâm nhập thị trường cho dòng xe điện phân khúc phổ thông.",
    title: "Khởi tạo báo cáo và tài liệu thông minh",
    subtitle: "Chọn tạo tự động, tùy chỉnh từng bước hoặc sinh hàng loạt theo bảng tính.",
    modes: {
      auto: "Tự động",
      advanced: "Tùy chỉnh",
      bulk: "Hàng loạt",
    },
    autoQuestion: "Bạn muốn tạo báo cáo hoặc tài liệu gì?",
    createMode: "Cách tạo tài liệu",
    scratchMode: "Tạo mới từ đầu",
    scratchDesc: "AI tự lập cấu trúc, viết nội dung và tạo tài liệu hoàn chỉnh.",
    templateMode: "Tạo theo mẫu",
    templateDesc: "Tải mẫu DOCX lên để AI viết nội dung vào đúng khung mẫu.",
    templateUpload: "Mẫu tài liệu",
    dropTemplate: "Tải lên mẫu DOCX / DOC",
    templatePreview: "Xem trước mẫu",
    templatePreviewLoading: "Đang đọc cấu trúc mẫu...",
    templatePreviewEmpty: "Chưa đọc được nội dung trong mẫu này.",
    templateStats: "thông tin mẫu",
    changeTemplate: "Đổi file mẫu",
    removeTemplate: "Xóa file mẫu",
    selectedTemplate: "File mẫu đang dùng",
    fullTemplateContent: "Nội dung toàn bộ file mẫu",
    hideTemplateInfo: "Ẩn thông tin mẫu",
    showTemplateInfo: "Hiện thông tin mẫu",
    topicLabel: "Đề tài cần tạo",
    pageCount: "Số trang mục tiêu",
    extraRequirements: "Yêu cầu chi tiết",
    extraPlaceholder: "Ví dụ: văn phong học thuật, có mục lục, bảng biểu, kết luận, tài liệu tham khảo; viết khoảng 30 trang A4...",
    startCreate: "Bắt đầu tạo",
    openStudioNow: "Vào Studio chỉnh sửa",
    exportingTemplate: "Đang tạo file Word theo mẫu...",
    completedTitle: "Tạo tài liệu hoàn tất",
    completedDesc: "Nội dung đã được sinh xong và file Word theo mẫu đã sẵn sàng.",
    downloadDocx: "Tải file Word theo mẫu",
    voiceIdea: "Nói ý tưởng",
    autoPlaceholder: "Ví dụ: Báo cáo phân tích thị trường ô tô điện Việt Nam 2026, đánh giá chính sách thuế, dung lượng trạm sạc và chiến lược giá...",
    attachments: "Tài liệu tham khảo và dữ liệu đính kèm",
    optional: "Tùy chọn",
    dropFiles: "Kéo thả hoặc chọn file tài liệu",
    chooseFile: "Chọn tệp",
    readiness: "Mức độ sẵn sàng",
    readyDesc: "Kiểm tra các thành phần trước khi bắt đầu tạo tự động.",
    step1Title: "Bước 1: Chọn loại dự án & Mục tiêu",
    step1Desc: "Chọn cấu trúc và mẫu chuẩn phù hợp với nhu cầu của bạn.",
    projectType: "Loại dự án",
    projectName: "Tên dự án / Báo cáo",
    projectDesc: "Mô tả chi tiết & Yêu cầu",
    targetAudience: "Đối tượng độc giả chính",
    nextStep2: "Tiếp tục sang bước 2",
    step2Title: "Bước 2: Bổ sung dữ liệu tham khảo",
    step2Desc: "Đính kèm file nghiên cứu, quy chuẩn hoặc tập dữ liệu.",
    uploadData: "Tải lên tệp PDF, DOCX, XLSX",
    chooseDataFile: "Chọn tệp dữ liệu",
    home: "Trang chủ",
    back: "Quay lại",
    generateOutline: "Lập dàn ý bằng AI",
    step4Title: "Bước 4: Xem dàn ý & Bắt đầu viết",
    step4Desc: "Cấu trúc các chương mục đã được tối ưu hóa.",
    chapter: "Chương",
    finishAndOpen: "Hoàn tất & Mở Canvas Studio",
    loadingWizard: "Đang tải trình tạo dự án...",
    bulkReadError: "Lỗi đọc file hàng loạt:",
    bulkLaunchError: "Lỗi kích hoạt hàng loạt:",
    outlineError: "Không thể lập dàn ý.",
    createReportError: "Không thể tạo báo cáo.",
    missingProject: "Thiếu ID dự án",
    batchTitle: "Đợt sinh báo cáo",
    startingAuto: "Đang khởi tạo tài liệu tự động...",
    autoRunningTitle: "AI đang tự động phân tích và tạo tài liệu",
    progress: "Tiến độ thực hiện",
    pause: "Tạm dừng",
    resume: "Tiếp tục",
    cancel: "Hủy bỏ",
    autoFailed: "Tạo báo cáo tự động thất bại.",
    autoStartError: "Không thể khởi động tiến trình tạo tự động.",
    pausedMsg: "Đã tạm dừng tiến trình.",
    bulkTitle: "Sinh báo cáo hàng loạt từ bảng tính",
    bulkSubtitle: "Tải lên file CSV hoặc Excel chứa danh sách đề tài; hệ thống sẽ sinh nhiều báo cáo độc lập.",
    uploadTopics: "Tải lên danh sách đề tài (.CSV hoặc .XLSX)",
    suggestedColumns: "Các cột đề xuất: tiêu đề, mô tả, loại báo cáo, độc giả",
    selectedFile: "Đã chọn",
    chooseSheet: "Chọn tệp CSV / Excel",
    previewRows: "Xem trước dữ liệu",
    topicTitle: "Tiêu đề đề tài",
    requirement: "Mô tả / Yêu cầu",
    type: "Loại",
    audience: "Độc giả",
    launchBulkPrefix: "Kích hoạt sinh",
    launchBulkSuffix: "báo cáo hàng loạt",
    bulkSuccessTitle: "Đã kích hoạt đợt sinh báo cáo thành công",
    bulkSuccessDesc: "tài liệu đang được xử lý song song trong nền.",
    openStudio: "Mở Studio",
    ideaLabel: "Mô tả tóm tắt ý tưởng / yêu cầu đề tài:",
    ideaPlaceholder: "Nhập mô tả đề tài để AI phân tích cấu trúc...",
    analyzeIdea: "Phân tích ý tưởng với AI",
    projectTypes: {
      business_report: ["Báo cáo Doanh nghiệp", "Chiến lược, kế hoạch kinh doanh và phân tích vận hành"],
      data_analysis: ["Phân tích Dữ liệu", "Số liệu, phân tích KPI, đối chiếu và trực quan hóa"],
      research: ["Báo cáo Nghiên cứu", "Nghiên cứu thị trường, học thuật và chuyên sâu"],
      technical: ["Tài liệu Kỹ thuật", "Kiến trúc hệ thống, API và đặc tả phần mềm"],
      proposal: ["Đề xuất Dự án & RFP", "Hồ sơ đề xuất, chào thầu và dự toán ngân sách"],
      financial: ["Báo cáo Tài chính", "Báo cáo tài chính, dòng tiền và dự báo doanh thu"],
      market_research: ["Nghiên cứu Thị trường", "Thị trường, đối thủ cạnh tranh và khách hàng"],
      custom: ["Tài liệu Tùy chỉnh", "Định dạng tài liệu linh hoạt theo nhu cầu riêng"],
    },
  },
  en: {
    defaultPrompt: "Analyze the 2026 Vietnam electric vehicle market and propose an entry strategy for the affordable segment.",
    title: "Create smart reports and documents",
    subtitle: "Choose one-click automatic, step-by-step custom, or bulk spreadsheet generation.",
    modes: {
      auto: "Automatic",
      advanced: "Custom",
      bulk: "Bulk",
    },
    autoQuestion: "What report or document do you want to create?",
    createMode: "Creation mode",
    scratchMode: "Create from scratch",
    scratchDesc: "AI plans the structure, writes content, and generates the complete document.",
    templateMode: "Use template",
    templateDesc: "Upload a DOCX template so AI writes content into your layout.",
    templateUpload: "Document template",
    dropTemplate: "Upload DOCX / DOC template",
    templatePreview: "Template preview",
    templatePreviewLoading: "Reading template structure...",
    templatePreviewEmpty: "Could not read content from this template.",
    templateStats: "template info",
    changeTemplate: "Change template",
    removeTemplate: "Remove template",
    selectedTemplate: "Active template file",
    fullTemplateContent: "Full template content",
    hideTemplateInfo: "Hide template info",
    showTemplateInfo: "Show template info",
    topicLabel: "Topic to create",
    pageCount: "Target page count",
    extraRequirements: "Detailed requirements",
    extraPlaceholder: "Example: academic tone, table of contents, charts, conclusion, references; around 30 A4 pages...",
    startCreate: "Start creating",
    openStudioNow: "Open editing Studio",
    exportingTemplate: "Generating Word document from template...",
    completedTitle: "Document creation complete",
    completedDesc: "Content generation is finished and the Word document is ready.",
    downloadDocx: "Download Word document",
    voiceIdea: "Voice idea",
    autoPlaceholder: "Example: 2026 Vietnam EV market analysis report, tax policies, charging station coverage, and pricing strategy...",
    attachments: "References and attached datasets",
    optional: "Optional",
    dropFiles: "Drop or choose document files",
    chooseFile: "Choose file",
    readiness: "Readiness level",
    readyDesc: "Check components before starting automatic creation.",
    step1Title: "Step 1: Choose project type & goal",
    step1Desc: "Pick a structure and standard template matching your needs.",
    projectType: "Project type",
    projectName: "Project / Report name",
    projectDesc: "Detailed description & requirements",
    targetAudience: "Primary audience",
    startingAuto: "Starting automatic document creation...",
    autoRunningTitle: "AI is analyzing and creating the document",
    progress: "Progress",
    pause: "Pause",
    resume: "Resume",
    cancel: "Cancel",
    autoFailed: "Automatic report creation failed.",
    autoStartError: "Could not start the automatic creation workflow.",
    pausedMsg: "Workflow paused.",
    bulkTitle: "Generate reports in batch from a spreadsheet",
    bulkSubtitle: "Upload a CSV or Excel file with topics; the system will generate multiple independent reports.",
    uploadTopics: "Upload a topic list (.CSV or .XLSX)",
    suggestedColumns: "Suggested columns: title, description, report type, audience",
    selectedFile: "Selected",
    chooseSheet: "Choose CSV / Excel file",
    previewRows: "Preview data",
    topicTitle: "Topic title",
    requirement: "Description / Requirement",
    type: "Type",
    audience: "Audience",
    launchBulkPrefix: "Generate",
    launchBulkSuffix: "reports in batch",
    bulkSuccessTitle: "Batch generation started successfully",
    bulkSuccessDesc: "documents are being processed in the background.",
    openStudio: "Open Studio",
    ideaLabel: "Brief idea / topic requirement:",
    ideaPlaceholder: "Describe the topic so AI can analyze the structure...",
    analyzeIdea: "Analyze idea with AI",
    nextStep2: "Continue to step 2",
    step2Title: "Step 2: Add reference data",
    step2Desc: "Attach research files, standards, or datasets.",
    uploadData: "Upload PDF, DOCX, XLSX files",
    chooseDataFile: "Choose data file",
    home: "Home",
    back: "Back",
    generateOutline: "Generate outline with AI",
    step4Title: "Step 4: Review outline and start drafting",
    step4Desc: "The section structure has been optimized.",
    chapter: "Chapter",
    finishAndOpen: "Finish and open Canvas Studio",
    loadingWizard: "Loading project creator...",
    bulkReadError: "Batch file reading error:",
    bulkLaunchError: "Batch launch error:",
    outlineError: "Could not generate the outline.",
    createReportError: "Could not create the report.",
    missingProject: "Missing project ID",
    batchTitle: "Report batch",
    projectTypes: {
      business_report: ["Business Report", "Strategy, business planning, and operational analysis"],
      data_analysis: ["Data Analysis", "Metrics, KPI analysis, reconciliation, and visualization"],
      research: ["Research Report", "Market, academic, and deep analytical research"],
      technical: ["Technical Documentation", "System architecture, APIs, and software specifications"],
      proposal: ["Proposal & RFP", "Project proposals, bids, and budget estimates"],
      financial: ["Financial Report", "Financial statements, cash flow, and revenue forecasts"],
      market_research: ["Market Research", "Market, competitor, and customer analysis"],
      custom: ["Custom Document", "Flexible document format for any need"],
    },
  },
} as const;

function UniversalProjectWizardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { locale } = useTranslation();
  const copy = WIZARD_COPY[locale];
  const initialType = normalizeNewProjectType(searchParams?.get("type") || "business_report");
  const initialPrompt = searchParams?.get("prompt") || "";
  const initialMode = searchParams?.get("mode");
  const initialWorkflow = searchParams?.get("workflow");
  const initialIsDataWorkflow = initialType === "data_analysis" || initialWorkflow === "data";
  const initialStoredDatasetId = readDatasetId(searchParams ?? new URLSearchParams());

  // Mode Selection: "auto" | "advanced" | "bulk"
  const [mode, setMode] = useState<"auto" | "advanced" | "bulk">(
    initialMode === "advanced" || initialMode === "bulk" ? initialMode : "auto"
  );

  // AUTO CREATE STATE
  const [autoPrompt, setAutoPrompt] = useState(
    initialPrompt || (initialIsDataWorkflow
      ? ""
      : copy.defaultPrompt)
  );
  const [autoCreationMode, setAutoCreationMode] = useState<"scratch" | "template">("scratch");
  const [autoTemplateFile, setAutoTemplateFile] = useState<File | null>(null);
  const [templatePreview, setTemplatePreview] = useState<any | null>(null);
  const [isTemplatePreviewing, setIsTemplatePreviewing] = useState(false);
  const [templatePreviewError, setTemplatePreviewError] = useState<string | null>(null);
  const [isTemplateInfoHidden, setIsTemplateInfoHidden] = useState(false);
  const [targetPages, setTargetPages] = useState<number>(30);
  const [autoRequirements, setAutoRequirements] = useState("");
  const [autoFiles, setAutoFiles] = useState<File[]>([]);
  const [dataSourceMode, setDataSourceMode] = useState<"file" | "url">("file");
  const [dataSourceUrl, setDataSourceUrl] = useState("");
  const [storedDatasetId, setStoredDatasetId] = useState<string | null>(initialStoredDatasetId);
  const [storedDatasetName, setStoredDatasetName] = useState("");
  const [storedDatasetLoading, setStoredDatasetLoading] = useState(Boolean(initialStoredDatasetId));
  const [storedDatasetError, setStoredDatasetError] = useState("");
  const [storedDatasetReload, setStoredDatasetReload] = useState(0);
  const [dataSheetRange, setDataSheetRange] = useState("");
  const [dataAnalysisRequest, setDataAnalysisRequest] = useState("");
  const [isRunningInitialAnalysis, setIsRunningInitialAnalysis] = useState(false);
  const [interactiveAnalysisResult, setInteractiveAnalysisResult] = useState<any | null>(null);
  const [dataPreview, setDataPreview] = useState<any | null>(null);
  const [isDataPreviewing, setIsDataPreviewing] = useState(false);
  const [dataPreviewConfirmed, setDataPreviewConfirmed] = useState(false);
  const [selectedDataSheetName, setSelectedDataSheetName] = useState<string>("");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState<number>(0);
  const [jobStatusMsg, setJobStatusMsg] = useState<string>("");
  const [jobStatus, setJobStatus] = useState<string>("");
  const [jobTimeline, setJobTimeline] = useState<any[]>([]);
  const [jobErrorMessage, setJobErrorMessage] = useState<string>("");
  const [jobNextAction, setJobNextAction] = useState<string>("");
  const [createdReportId, setCreatedReportId] = useState<string | null>(null);
  const [isAutoSubmitting, setIsAutoSubmitting] = useState(false);
  const [isExportingDocx, setIsExportingDocx] = useState(false);
  const [autoExportResult, setAutoExportResult] = useState<any | null>(null);
  const exportStartedRef = useRef(false);
  const autoFileInputRef = useRef<HTMLInputElement | null>(null);
  const restoredAutoJobRef = useRef(false);

  // DIRECT INTERACTIVE ANALYSIS WORKSPACE STATE
  const [isInteractiveWorkspaceOpen, setIsInteractiveWorkspaceOpen] = useState(false);
  const [interactivePreferredSheet, setInteractivePreferredSheet] = useState("");
  const [dataPreviewLoadingStep, setDataPreviewLoadingStep] = useState("");

  useEffect(() => {
    if (!autoFiles.length && !dataSourceUrl && !autoTemplateFile && !autoRequirements && !dataAnalysisRequest) return;
    const warnBeforeLeaving = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warnBeforeLeaving);
    return () => window.removeEventListener("beforeunload", warnBeforeLeaving);
  }, [autoFiles, dataSourceUrl, autoTemplateFile, autoRequirements, dataAnalysisRequest]);

  // BULK BATCH STATE
  const [bulkFile, setBulkFile] = useState<File | null>(null);
  const [bulkPreviewRows, setBulkPreviewRows] = useState<any[]>([]);
  const [isBulkSubmitting, setIsBulkSubmitting] = useState(false);
  const [bulkBatchResult, setBulkBatchResult] = useState<any | null>(null);

  // ADVANCED WIZARD STATE
  const [step, setStep] = useState(initialMode === "advanced" ? 1 : 1);
  const [projectType, setProjectType] = useState(initialType);
  const isDataWorkflow = projectType === "data_analysis" || initialWorkflow === "data";
  const selectedAnalysisMode = readAnalysisMode(searchParams ?? new URLSearchParams());
  const dataAnalysisBranch = selectedAnalysisMode === "direct-analysis" ? "interactive" : selectedAnalysisMode === "docx-report" ? "report" : null;
  const setDataAnalysisBranch = (branch: "interactive" | "report" | null) => {
    if (!guardAutoJobContextChange()) return;
    const nextMode: DataAnalysisMode | null = branch === "interactive" ? "direct-analysis" : branch === "report" ? "docx-report" : null;
    window.history.pushState(null, "", analysisModeUrl(searchParams?.toString() ?? "", nextMode));
  };
  const [isAnalyzingIntent, setIsAnalyzingIntent] = useState(false);
  const [topicName, setTopicName] = useState("Báo cáo Chiến lược Doanh nghiệp 2026");
  const [description, setDescription] = useState(initialPrompt || "Báo cáo phân tích thực trạng và xây dựng chiến lược phát triển tối ưu.");
  const [audience, setAudience] = useState("Hội đồng Quản trị & Ban Điều hành");
  const [customFields, setCustomFields] = useState<CustomFieldItem[]>([
    { key: "company_name", label: "Tên Doanh nghiệp", type: "text", required: true, value: "VinFast Auto" },
    { key: "department", label: "Phòng ban phụ trách", type: "text", required: false, value: "Khối Chiến lược" },
    { key: "lead_author", label: "Người lập báo cáo", type: "text", required: true, value: "Alex Nguyen" },
  ]);
  const selectedTemplate = "tpl_corp_standard";
  const [knowledgeFiles, setKnowledgeFiles] = useState<File[]>([]);
  const [isGeneratingOutline, setIsGeneratingOutline] = useState(false);
  const [outline, setOutline] = useState<OutlineItemUI[]>([]);
  const [isCreatingReport, setIsCreatingReport] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getSuggestedProjectType = (text: string) => {
    const normalized = text.toLowerCase();
    if (/(arm|x86|api|server|máy chủ|mạng|network|kiến trúc|architecture|phần mềm|software|triển khai|deploy|hệ thống)/i.test(normalized)) {
      return "business_report";
    }
    if (/(nghiên cứu|research|học thuật|tiểu luận|bài tập lớn|luận|phân tích chuyên sâu|so sánh)/i.test(normalized)) {
      return "research";
    }
    if (/(excel|csv|số liệu|kpi|dataset|data|thống kê|biểu đồ|đối soát)/i.test(normalized)) {
      return "data_analysis";
    }
    if (/(thị trường|market|khách hàng|đối thủ|customer|competitor|phân khúc)/i.test(normalized)) {
      return "research";
    }
    if (/(tài chính|doanh thu|chi phí|dòng tiền|financial|revenue|cash flow|lợi nhuận)/i.test(normalized)) {
      return "business_report";
    }
    if (/(đề xuất|proposal|hồ sơ thầu|chào thầu|dự toán|ngân sách)/i.test(normalized)) {
      return "business_report";
    }
    if (/(kinh doanh|business|chiến lược|quản trị|vận hành|kế hoạch)/i.test(normalized)) {
      return "business_report";
    }
    return "custom";
  };

  const resolveDownloadUrl = (downloadUrl?: string) => {
    if (!downloadUrl) return "#";
    if (downloadUrl.startsWith("http")) return downloadUrl;
    const apiOrigin = API_BASE.replace(/\/api\/v1\/?$/, "");
    return `${apiOrigin}${downloadUrl.startsWith("/") ? downloadUrl : `/${downloadUrl}`}`;
  };

  const guardAutoJobContextChange = useCallback(() => {
    if (!activeJobId || canSafelySwitchAutoContext(jobStatus)) return true;
    window.alert(
      locale === "vi"
        ? "Tài liệu vẫn đang được tạo. Vui lòng tạm dừng, hủy hoặc chờ hoàn tất trước khi đổi module để không mất màn hình theo dõi."
        : "This document is still being generated. Please pause, cancel, or wait for it to finish before changing modules so the progress view is not lost."
    );
    return false;
  }, [activeJobId, jobStatus, locale]);

  useEffect(() => {
    if (!storedDatasetId || !isDataWorkflow) {
      setStoredDatasetLoading(false);
      return;
    }

    let active = true;
    setStoredDatasetLoading(true);
    setStoredDatasetError("");
    setError(null);

    void api.data.profile(storedDatasetId).then((savedProfile: any) => {
      if (!active) return;
      const firstSheet = savedProfile?.sheets?.[0]?.name || savedProfile?.visual_workbook?.sheets?.[0]?.name || "";
      const displayName = savedProfile?.original_name || savedProfile?.file_name || (locale === "vi" ? "Tập dữ liệu đã lưu" : "Saved dataset");
      setStoredDatasetName(displayName);
      setDataSourceMode("file");
      setAutoFiles([]);
      setDataPreview({ ...savedProfile, ok: true, file_name: displayName });
      setSelectedDataSheetName(firstSheet);
      setDataPreviewConfirmed(true);
      setInteractiveAnalysisResult(null);
      setInteractivePreferredSheet(firstSheet);
      setIsInteractiveWorkspaceOpen(true);
    }).catch((cause: unknown) => {
      if (!active) return;
      setDataPreview(null);
      setDataPreviewConfirmed(false);
      setIsInteractiveWorkspaceOpen(false);
      setStoredDatasetError(formatUnknownError(cause, locale === "vi" ? "Không thể mở tập dữ liệu đã lưu." : "Could not open the saved dataset."));
    }).finally(() => {
      if (active) setStoredDatasetLoading(false);
    });

    return () => { active = false; };
  }, [isDataWorkflow, locale, storedDatasetId, storedDatasetReload]);

  const registerModeChangeHandler = useModeStore((state) => state.registerModeChangeHandler);

  useEffect(() => {
    useModeStore.setState({ mode });
  }, [mode]);

  useEffect(() => {
    registerModeChangeHandler((nextMode) => {
      if (nextMode === "advanced" || nextMode === "bulk") {
        if (!guardAutoJobContextChange()) return false;
      }
      setMode(nextMode);
      if (nextMode === "advanced") {
        setStep(1);
      }
      return true;
    });
    return () => registerModeChangeHandler(null);
  }, [guardAutoJobContextChange, registerModeChangeHandler]);

  useEffect(() => {
    if (restoredAutoJobRef.current || typeof window === "undefined") return;
    restoredAutoJobRef.current = true;

    try {
      const raw = window.localStorage.getItem("ai_report_studio:auto_job_state");
      const saved = raw ? JSON.parse(raw) : null;
      if (!shouldRestoreAutoJob(saved)) return;

      setMode("auto");
      setProjectType(normalizeNewProjectType(saved.projectType || initialType));
      setActiveJobId(saved.jobId);
      setCreatedReportId(saved.reportId || null);
      setJobStatus(saved.status || "running");
      setJobProgress(Number(saved.progress) || 0);
      setJobStatusMsg(
        saved.statusMessage ||
        (locale === "vi" ? "Đang khôi phục tiến trình tạo tài liệu..." : "Restoring document generation progress...")
      );
    } catch {
      window.localStorage.removeItem("ai_report_studio:auto_job_state");
    }
  }, [initialType, locale]);

  useEffect(() => {
    if (typeof window === "undefined" || !activeJobId) return;

    if (!canSafelySwitchAutoContext(jobStatus)) {
      const snapshot = buildAutoJobSnapshot({
        jobId: activeJobId,
        reportId: createdReportId,
        projectType,
        status: jobStatus,
        progress: jobProgress,
        statusMessage: jobStatusMsg,
      });
      window.localStorage.setItem(snapshot.storageKey, JSON.stringify(snapshot.value));
      return;
    }

    window.localStorage.removeItem("ai_report_studio:auto_job_state");
  }, [activeJobId, createdReportId, jobProgress, jobStatus, jobStatusMsg, projectType]);

  // Polling Job Status for Auto Mode
  useEffect(() => {
    if (!activeJobId) return;

    const interval = setInterval(async () => {
      try {
        const job = await api.reports.getJob(activeJobId);
        setJobProgress(job.progress_percent);
        setJobStatusMsg(job.status_message);
        setJobStatus(job.status);
        setJobTimeline(job.timeline || job.metadata?.timeline || []);
        setJobErrorMessage(job.error_message || "");
        setJobNextAction(job.next_action || "");

        const repId = (job.metadata && job.metadata.report_id) || (job.payload && job.payload.report_id);
        if (repId && !createdReportId) {
          setCreatedReportId(repId);
        }

        if (job.status === "completed") {
          clearInterval(interval);
          setIsAutoSubmitting(false);
          setJobProgress(100);
          if (repId && !exportStartedRef.current) {
            exportStartedRef.current = true;
            setIsExportingDocx(true);
            setJobStatusMsg(copy.exportingTemplate);
            try {
              const exportRes = await api.exports.exportDocx({
                report_id: repId,
                export_format: "docx",
                include_cover: true,
                include_toc: true,
                include_references: true,
                citation_style: "IEEE",
              });
              setAutoExportResult(exportRes);
              setJobStatusMsg(copy.completedDesc);
            } catch (exportErr: any) {
              setError(formatUnknownError(exportErr, locale === "vi" ? "Đã sinh nội dung nhưng chưa xuất được file Word theo mẫu." : "Content was generated, but the templated Word export failed."));
            } finally {
              setIsExportingDocx(false);
            }
          }
        } else if (job.status === "review_needed") {
          clearInterval(interval);
          setIsAutoSubmitting(false);
          setJobProgress(100);
          setError(formatUnknownError(job.status_message, locale === "vi" ? "Báo cáo đã tạo nhưng cần rà soát trước khi xuất Word." : "The report was created but needs review before Word export."));
        } else if (job.status === "failed") {
          clearInterval(interval);
          setError(formatUnknownError(job.status_message, copy.autoFailed));
          setIsAutoSubmitting(false);
        }
      } catch (err) {
        console.error("Job status check error:", err);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeJobId, createdReportId, copy.autoFailed, copy.completedDesc, copy.exportingTemplate, locale]);

  const handleTemplateFileChange = async (file: File | null) => {
    setAutoTemplateFile(file);
    setTemplatePreview(null);
    setTemplatePreviewError(null);
    setIsTemplateInfoHidden(false);
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".docx")) {
      setTemplatePreviewError(locale === "vi" ? "Hiện chỉ xem trước được file DOCX." : "Only DOCX preview is currently supported.");
      return;
    }

    setIsTemplatePreviewing(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const preview = await api.templates.previewDocx(fd);
      setTemplatePreview(preview);
    } catch (err: any) {
      setTemplatePreviewError(formatUnknownError(err, locale === "vi" ? "Không thể xem trước mẫu này." : "Could not preview this template."));
    } finally {
      setIsTemplatePreviewing(false);
    }
  };

  const clearTemplateFile = () => {
    setAutoTemplateFile(null);
    setTemplatePreview(null);
    setTemplatePreviewError(null);
    setIsTemplatePreviewing(false);
    setIsTemplateInfoHidden(false);
  };

  const clearAutoFiles = () => {
    setAutoFiles([]);
    setStoredDatasetId(null);
    setStoredDatasetName("");
    setStoredDatasetError("");
    setDataPreview(null);
    setDataPreviewConfirmed(false);
    setIsInteractiveWorkspaceOpen(false);
    setInteractiveAnalysisResult(null);
    setInteractivePreferredSheet("");
    setSelectedDataSheetName("");
    setError(null);
    if (autoFileInputRef.current) {
      autoFileInputRef.current.value = "";
    }
  };

  const handleRunSpreadsheetAnalysis = async (prompt: string, preferredSheet?: string) => {
    const request = prompt.trim();
    if (!request || isRunningInitialAnalysis) return;
    if (!dataPreview || dataPreview.error) return;

    setIsRunningInitialAnalysis(true);
    setError(null);
    try {
      const formData = new FormData();
      if (dataSourceMode === "file" && selectedDatasetFile) {
        formData.append("file", selectedDatasetFile);
      } else if (dataSourceMode === "file" && storedDatasetId) {
        formData.append("file_id", storedDatasetId);
      }
      if (dataSourceMode === "url" && dataSourceUrl.trim()) {
        formData.append("data_source_url", dataSourceUrl.trim());
      }
      formData.append("sheet_name", preferredSheet || selectedDataSheetName || dataPreview?.sheets?.[0]?.name || "Sheet1");
      formData.append("prompt", request);
      formData.append("scope", JSON.stringify({ type: "workbook" }));
      formData.append("conversation_id", `excel_analysis_setup_${Date.now()}`);

      const result = await api.data.workbookAnalysisAction(formData);
      setInteractiveAnalysisResult(result);

      let matchedPromptSheet = "";
      if (dataPreview?.sheets && Array.isArray(dataPreview.sheets)) {
        const reqLower = request.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        for (const s of dataPreview.sheets) {
          if (s.name) {
            const sLower = s.name.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
            if (reqLower.includes(sLower)) {
              matchedPromptSheet = s.name;
              break;
            }
          }
        }
      }

      setInteractivePreferredSheet(
        result.context?.sheet && result.context.sheet !== "workbook" && result.context.sheet !== "multiple_sheets"
          ? result.context.sheet
          : matchedPromptSheet || preferredSheet || selectedDataSheetName || dataPreview?.sheets?.[0]?.name || ""
      );
      setIsInteractiveWorkspaceOpen(true);
    } catch (err: any) {
      setError(formatUnknownError(err, locale === "vi" ? "Không thể chạy phân tích dữ liệu." : "Could not run spreadsheet analysis."));
    } finally {
      setIsRunningInitialAnalysis(false);
    }
  };

  const handleStartInteractiveAnalysis = (prompt: string, preferredSheet?: string) => {
    handleRunSpreadsheetAnalysis(prompt, preferredSheet);
  };

  const handleOpenInteractiveWorkspaceOnly = () => {
    setInteractiveAnalysisResult(null);
    setInteractivePreferredSheet(selectedDataSheetName || "");
    setIsInteractiveWorkspaceOpen(true);
  };

  const previewDatasetSource = async (datasetFile?: File | null, modeOverride?: "file" | "url") => {
    const modeToUse = modeOverride || dataSourceMode;
    const previousSelectedSheet = selectedDataSheetName;
    setDataPreview(null);
    setDataPreviewConfirmed(false);
    setIsInteractiveWorkspaceOpen(false);
    setSelectedDataSheetName("");
    setIsDataPreviewing(true);
    setDataPreviewLoadingStep(locale === "vi" ? "Đang kết nối..." : "Connecting...");
    setError(null);

    const stepTimer1 = setTimeout(() => {
      setDataPreviewLoadingStep(locale === "vi" ? "Đang tải bảng tính..." : "Downloading spreadsheet...");
    }, 400);
    const stepTimer2 = setTimeout(() => {
      setDataPreviewLoadingStep(locale === "vi" ? "Đang đọc workbook & schema..." : "Reading workbook schema...");
    }, 900);
    const stepTimer3 = setTimeout(() => {
      setDataPreviewLoadingStep(locale === "vi" ? "Đang lấy danh sách sheet & số liệu..." : "Extracting sheets & metrics...");
    }, 1500);

    try {
      const fd = new FormData();
      if (modeToUse === "url") {
        const trimmedUrl = dataSourceUrl.trim();
        if (!trimmedUrl) {
          setDataPreview({
            error: locale === "vi" ? "Vui lòng nhập đường liên kết dữ liệu công khai." : "Please enter a public data link."
          });
          return;
        }
        fd.append("data_source_url", trimmedUrl);
      } else if (datasetFile) {
        fd.append("file", datasetFile);
      } else {
        setDataPreview({
          error: locale === "vi" ? "Vui lòng chọn tệp dữ liệu XLSX, XLS hoặc CSV để tải lên." : "Please choose a XLSX, XLS or CSV dataset file."
        });
        return;
      }
      // Load every sheet; analysis selection belongs to the workspace.
      if (dataAnalysisRequest.trim()) fd.append("analysis_request", dataAnalysisRequest.trim());
      const preview = await api.data.previewUpload(fd);
      if (preview && !preview.error) {
        setDataPreview(preview);
        const resolvedSheet = resolveSelectedSheetName(preview, previousSelectedSheet, dataSheetRange);
        setSelectedDataSheetName(resolvedSheet);
        setDataPreviewConfirmed(true);
      } else {
        setDataPreview({
          error: preview?.error || (locale === "vi" ? "Không thể đọc dữ liệu từ liên kết này." : "Could not read data from this source.")
        });
      }
    } catch (err: any) {
      setDataPreview({ error: formatUnknownError(err, locale === "vi" ? "Không thể đọc dữ liệu từ liên kết này." : "Could not read data from this source.") });
    } finally {
      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      clearTimeout(stepTimer3);
      setIsDataPreviewing(false);
      setDataPreviewLoadingStep("");
    }
  };

  const handleAutoFilesChange = async (files: File[]) => {
    setDataSourceMode("file");
    setStoredDatasetId(null);
    setStoredDatasetName("");
    setStoredDatasetError("");
    setAutoFiles(files);
    setDataPreview(null);
    setDataPreviewConfirmed(false);
    setSelectedDataSheetName("");
    if (!isDataWorkflow) return;
    const datasetFile = files.find((file) => /\.(xlsx|xls|xlsm|csv)$/i.test(file.name));
    if (!datasetFile) return;
    await previewDatasetSource(datasetFile, "file");
  };

  const buildInteractiveReportAnalysisRequest = (analysisResult?: any) => {
    const result = analysisResult || interactiveAnalysisResult;
    const originalRequest = dataAnalysisRequest.trim();
    if (!result) return originalRequest;

    const prompt = String(result.prompt || result.analysis_history_item?.prompt || originalRequest || "").trim();
    const title = String(result.title || "").trim();
    const answer = String(result.answer || "").trim();
    const sheet = String(result.context?.sheet || result.evidence?.sheet || selectedDataSheetName || "").trim();
    const ranges = Array.isArray(result.evidence?.ranges) ? result.evidence.ranges.filter(Boolean).join(", ") : "";
    const matchedCells = Array.isArray(result.result?.matched_cells)
      ? result.result.matched_cells
          .slice(0, 30)
          .map((cell: any) => (typeof cell === "object" ? cell.address : String(cell)))
          .filter(Boolean)
          .join(", ")
      : "";

    return [
      originalRequest ? `Yêu cầu phân tích ban đầu: ${originalRequest}` : "",
      prompt && prompt !== originalRequest ? `Câu hỏi vừa chạy: ${prompt}` : "",
      title ? `Kết quả cần chèn vào báo cáo: ${title}` : "",
      answer ? `Nhận xét phân tích: ${answer}` : "",
      sheet ? `Sheet nguồn: ${sheet}` : "",
      ranges ? `Vùng dữ liệu: ${ranges}` : "",
      matchedCells ? `Các ô/dòng liên quan: ${matchedCells}` : "",
      "Hãy đưa kết quả phân tích trên vào báo cáo Word, có phần nhận xét, bằng chứng dữ liệu và kết luận ngắn gọn.",
    ].filter(Boolean).join("\n");
  };

  const startAutoCreate = async (analysisRequestOverride?: string) => {
    if (!isDataWorkflow && !autoPrompt.trim()) return;
    if (autoCreationMode === "template" && !autoTemplateFile) {
      setError(locale === "vi" ? "Vui lòng tải lên file mẫu trước khi bắt đầu tạo." : "Please upload a template file before starting.");
      return;
    }
    if (isDataWorkflow && !hasActiveDatasetSource) {
      setError(locale === "vi" ? "Vui lòng tải file dữ liệu hoặc dán link dữ liệu công khai để phân tích." : "Please upload a dataset file or paste a public dataset link for analysis.");
      return;
    }
    const previewIsConfirmed = dataPreviewConfirmed || Boolean(isDataWorkflow && dataPreview && analysisRequestOverride?.trim());
    if (isDataWorkflow && !previewIsConfirmed) {
      setError(locale === "vi" ? "Vui lòng xác nhận dữ liệu đã đọc trước khi tạo báo cáo." : "Please confirm the dataset preview before creating the report.");
      return;
    }

    setIsAutoSubmitting(true);
    setError(null);
    setJobProgress(0);
    setJobStatusMsg(copy.startingAuto);
    setJobStatus("queued");
    setJobTimeline([{ stage: "queued", progress: 0, message: copy.startingAuto }]);
    setJobErrorMessage("");
    setJobNextAction("");
    setAutoExportResult(null);
    setIsExportingDocx(false);
    exportStartedRef.current = false;

    try {
      const formData = new FormData();
      const effectiveDataAnalysisRequest = (analysisRequestOverride || dataAnalysisRequest).trim();
      const fullPrompt = [
        isDataWorkflow
          ? locale === "vi"
            ? "Module: Phân tích dữ liệu. Chỉ đọc và phân tích file Excel/CSV đã tải lên; không dùng cấu trúc hoặc nội dung của các module khác."
            : "Module: Data analysis. Only read and analyze the uploaded Excel/CSV files; do not use structures or content from other modules."
          : `${locale === "vi" ? "Đề tài" : "Topic"}: ${autoPrompt.trim()}`,
        ...(isDataWorkflow ? buildDatasetSourcePromptParts({
          locale,
          mode: dataSourceMode,
          files: autoFiles,
          url: dataSourceUrl,
          fileId: storedDatasetId,
          fileName: storedDatasetName,
          sheetRange: dataSheetRange,
          analysisRequest: effectiveDataAnalysisRequest,
        }) : []),
        isDataWorkflow && autoPrompt.trim()
          ? `${locale === "vi" ? "Câu hỏi/KPI cần tập trung" : "Focus questions/KPIs"}: ${autoPrompt.trim()}`
          : "",
        `${locale === "vi" ? "Số trang mục tiêu" : "Target pages"}: ${targetPages} ${locale === "vi" ? "trang A4" : "A4 pages"}`,
        `${locale === "vi" ? "Cách tạo" : "Creation method"}: ${autoCreationMode === "template" ? copy.templateMode : copy.scratchMode}`,
        autoRequirements.trim() ? `${locale === "vi" ? "Yêu cầu chi tiết" : "Detailed requirements"}: ${autoRequirements.trim()}` : "",
        autoCreationMode === "template"
          ? locale === "vi"
            ? "Hãy viết nội dung trực tiếp theo cấu trúc của file mẫu đã tải lên, giữ bố cục chính và thay nội dung mẫu bằng nội dung mới."
            : "Write directly into the uploaded template structure, keep the main layout, and replace sample content with new content."
          : locale === "vi"
            ? "Hãy tự lập đề cương, viết nội dung đầy đủ, có bảng biểu khi phù hợp và tạo tài liệu hoàn chỉnh."
            : "Create the outline from scratch, write complete content, add tables where useful, and produce a finished document.",
      ].filter(Boolean).join("\n");

      formData.append("prompt", fullPrompt);
      if (isDataWorkflow) {
        if (storedDatasetId) {
          formData.append("dataset_file_id", storedDatasetId);
        }
        if (dataSourceMode === "url" && dataSourceUrl.trim()) {
          formData.append("data_source_url", dataSourceUrl.trim());
        }
        if (dataSheetRange.trim()) formData.append("sheet_range", dataSheetRange.trim());
        if (effectiveDataAnalysisRequest) formData.append("analysis_request", effectiveDataAnalysisRequest);
      }
      if (autoCreationMode === "template" && autoTemplateFile) {
        formData.append("use_uploaded_template", "true");
        const normalizedName = /mau|mẫu|template/i.test(autoTemplateFile.name)
          ? autoTemplateFile.name
          : `template_${autoTemplateFile.name}`;
        formData.append("files", autoTemplateFile, normalizedName);
      }
      if (!isDataWorkflow || (dataSourceMode === "file" && !storedDatasetId)) {
        autoFiles.forEach((f) => formData.append("files", f));
      }

      const res = await api.reports.autoCreate(formData);
      setActiveJobId(res.job_id);
      setCreatedReportId(res.report_id);
      setJobStatus("running");
    } catch (err: any) {
      setError(formatUnknownError(err, copy.autoStartError));
      setIsAutoSubmitting(false);
    }
  };

  const handleAutoCreateSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    await startAutoCreate();
  };

  const handleCreateDocxFromInteractiveFinding = async (analysisResult?: any) => {
    const enrichedRequest = buildInteractiveReportAnalysisRequest(analysisResult);
    if (enrichedRequest) {
      setDataAnalysisRequest(enrichedRequest);
    }
    setDataPreviewConfirmed(true);
    setDataAnalysisBranch("report");
    await startAutoCreate(enrichedRequest);
  };

  const handlePauseJob = async () => {
    if (!activeJobId) return;
    await api.reports.pauseJob(activeJobId);
    setJobStatus("paused");
    setJobStatusMsg(copy.pausedMsg);
  };

  const handleResumeJob = async () => {
    if (!activeJobId) return;
    await api.reports.resumeJob(activeJobId);
    setJobStatus("running");
  };

  const handleCancelJob = async () => {
    if (!activeJobId) return;
    await api.reports.cancelJob(activeJobId);
    setActiveJobId(null);
    setCreatedReportId(null);
    setIsAutoSubmitting(false);
  };

  const handleRetryJob = async () => {
    if (!activeJobId) return;
    setError(null);
    setIsAutoSubmitting(true);
    setJobStatus("running");
    setJobStatusMsg(locale === "vi" ? "Đang chạy lại quy trình..." : "Retrying workflow...");
    try {
      await api.reports.retryJob(activeJobId);
    } catch (err: any) {
      setError(formatUnknownError(err, locale === "vi" ? "Không thể chạy lại quy trình." : "Could not retry the workflow."));
      setIsAutoSubmitting(false);
    }
  };

  const handleBulkFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBulkFile(file);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.reports.bulkPreview(fd);
      setBulkPreviewRows(res.preview || []);
    } catch (err: any) {
      alert(`${copy.bulkReadError} ${formatUnknownError(err)}`);
    }
  };

  const handleLaunchBulk = async () => {
    if (!bulkFile) return;
    setIsBulkSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("file", bulkFile);
      fd.append("batch_title", `${copy.batchTitle} ${new Date().toLocaleDateString(locale === "vi" ? "vi-VN" : "en-US")}`);
      const res = await api.reports.bulkCreate(fd);
      setBulkBatchResult(res);
    } catch (err: any) {
      alert(`${copy.bulkLaunchError} ${formatUnknownError(err)}`);
    } finally {
      setIsBulkSubmitting(false);
    }
  };

  const handleAnalyzeIntent = async () => {
    setIsAnalyzingIntent(true);
    setError(null);
    try {
      const res = await api.ai.analyzeIntent({
        user_prompt: description || topicName,
        selected_type: projectType,
      });

      setTopicName(res.suggested_title);
      setProjectType(res.suggested_type);
      setAudience(res.target_audience);
      setDescription(res.objective);
      if (res.suggested_custom_fields?.length > 0) {
        setCustomFields(res.suggested_custom_fields);
      }
    } catch (err: any) {
      setError(formatUnknownError(err, copy.outlineError));
    } finally {
      setIsAnalyzingIntent(false);
    }
  };

  const handleGenerateOutline = async () => {
    setIsGeneratingOutline(true);
    setError(null);
    try {
      const project = await api.projects.create({
        name: topicName,
        type: projectType,
        description,
        settings: {
          audience,
          custom_fields: customFields,
          template_id: selectedTemplate,
        },
      });

      for (const file of knowledgeFiles) {
        const fd = new FormData();
        fd.append("project_id", project.id);
        fd.append("document_type", "reference");
        fd.append("file", file);
        await api.files.upload(fd);
      }

      const outlineRes = await api.ai.generateOutline({
        project_id: project.id,
        topic_name: topicName,
        project_type: projectType,
        topic_description: description,
        audience,
        target_chapters_count: 5,
      });

      setOutline(outlineRes.outline);
      (window as any).__created_project_id = project.id;
      setStep(4);
    } catch (err: any) {
      setError(formatUnknownError(err, copy.outlineError));
    } finally {
      setIsGeneratingOutline(false);
    }
  };

  const handleCreateAndOpenStudio = async () => {
    setIsCreatingReport(true);
    setError(null);
    try {
      const projectId = (window as any).__created_project_id;
      if (!projectId) throw new Error(copy.missingProject);

      const reportRes = await api.reports.create({
        project_id: projectId,
        template_version_id: selectedTemplate,
        title: topicName,
        report_type: projectType,
        outline: outline,
      });

      router.push(`/reports/${reportRes.id}/editor`);
    } catch (err: any) {
      setError(formatUnknownError(err, copy.createReportError));
      setIsCreatingReport(false);
    }
  };

  const suggestedProjectType = getSuggestedProjectType(description || topicName || autoPrompt);
  const selectedTypeGuide = PROJECT_TYPE_GUIDE[locale][projectType as keyof typeof PROJECT_TYPE_GUIDE[typeof locale]];
  const selectedModuleScreen = MODULE_SCREEN_COPY[locale][projectType as keyof typeof MODULE_SCREEN_COPY[typeof locale]];
  const moduleAutoFields = (() => {
    const base = {
      mainLabel: copy.topicLabel,
      mainPlaceholder: copy.autoPlaceholder,
      mainHint: selectedModuleScreen.input,
      requirementsLabel: copy.extraRequirements,
      requirementsPlaceholder: copy.extraPlaceholder,
      fileLabel: `${copy.attachments} (${copy.optional})`,
      fileHint: selectedModuleScreen.files,
      accept: ".pdf,.docx,.xlsx,.csv,.txt",
      primaryAction: copy.startCreate,
      requiresPrompt: true,
      showVoice: true,
    };

    if (projectType === "data_analysis") {
      return {
        mainLabel: locale === "vi" ? "Câu hỏi phân tích / KPI cần tập trung" : "Analysis questions / focus KPIs",
        mainPlaceholder: locale === "vi"
          ? "Tùy chọn: ví dụ phân tích doanh thu theo quý, so sánh KPI giữa phòng ban, tìm bất thường trong chi phí..."
          : "Optional: e.g. analyze quarterly revenue, compare department KPIs, find cost anomalies...",
        mainHint: locale === "vi"
          ? "Không cần nhập đề tài. Chỉ cần tải file dữ liệu; AI sẽ đọc sheet, cột, số liệu và tự lập báo cáo."
          : "No topic is required. Upload the dataset and AI will read sheets, columns, metrics, and build the report.",
        requirementsLabel: locale === "vi" ? "Quy tắc phân tích / đầu ra mong muốn" : "Analysis rules / expected output",
        requirementsPlaceholder: locale === "vi"
          ? "Ví dụ: ưu tiên biểu đồ doanh thu, kiểm tra dữ liệu thiếu, nêu 5 insight chính, kết luận bằng khuyến nghị..."
          : "Example: prioritize revenue charts, check missing data, show 5 key insights, end with recommendations...",
        fileLabel: locale === "vi" ? "File dữ liệu Excel/CSV cần phân tích" : "Excel/CSV dataset to analyze",
        fileHint: locale === "vi"
          ? "Bắt buộc có XLSX, XLS, XLSM hoặc CSV. Word mẫu có thể tải riêng ở mục Có mẫu Word."
          : "Requires XLSX, XLS, XLSM, or CSV. Upload a Word template separately under Use Word template.",
        accept: ".xlsx,.xls,.xlsm,.csv",
        primaryAction: locale === "vi" ? "Bắt đầu phân tích dữ liệu" : "Start data analysis",
        requiresPrompt: false,
        showVoice: false,
      };
    }

    if (projectType === "technical") {
      return {
        ...base,
        mainLabel: locale === "vi" ? "Hệ thống / sản phẩm kỹ thuật cần viết" : "System / technical product",
        mainPlaceholder: locale === "vi"
          ? "Ví dụ: Cài đặt, cấu hình máy chủ, mạng và triển khai ứng dụng web nội bộ..."
          : "Example: Server setup, network configuration, and internal web app deployment...",
        requirementsPlaceholder: locale === "vi"
          ? "Nêu môi trường, công nghệ, sơ đồ cần có, bảng cấu hình, kiểm thử, rủi ro và số trang..."
          : "Describe environment, technologies, required diagrams, configuration tables, tests, risks, and page count...",
        fileHint: locale === "vi" ? "Có thể đính kèm mã nguồn, đặc tả, sơ đồ, log, DOCX mẫu hoặc tài liệu yêu cầu." : "Attach source code, specs, diagrams, logs, DOCX templates, or requirements.",
      };
    }

    if (projectType === "financial") {
      return {
        ...base,
        mainLabel: locale === "vi" ? "Kỳ báo cáo / bài toán tài chính" : "Reporting period / financial question",
        mainPlaceholder: locale === "vi"
          ? "Ví dụ: Phân tích doanh thu, chi phí và dòng tiền quý 4/2026 của công ty..."
          : "Example: Analyze Q4 2026 revenue, costs, and cash flow...",
        fileLabel: locale === "vi" ? "File tài chính hoặc tài liệu nguồn" : "Financial files or source documents",
        fileHint: locale === "vi" ? "Nên tải Excel/CSV để hệ thống tự tính bảng KPI, tổng, trung bình và biểu đồ." : "Prefer Excel/CSV so the system can compute KPI tables, totals, averages, and charts.",
      };
    }

    if (projectType === "proposal") {
      return {
        ...base,
        mainLabel: locale === "vi" ? "Tên dự án / gói thầu / đề xuất" : "Project / bid / proposal name",
        mainPlaceholder: locale === "vi"
          ? "Ví dụ: Hồ sơ đề xuất triển khai hệ thống quản lý tài liệu AI cho doanh nghiệp..."
          : "Example: Proposal for implementing an AI document management system...",
        fileHint: locale === "vi" ? "Có thể tải yêu cầu mời thầu, bảng giá, năng lực công ty hoặc mẫu hồ sơ." : "Attach RFPs, pricing sheets, company credentials, or proposal templates.",
      };
    }

    if (projectType === "research") {
      return {
        ...base,
        mainLabel: locale === "vi" ? "Đề tài nghiên cứu / bài tập lớn" : "Research topic / academic assignment",
        mainPlaceholder: locale === "vi"
          ? "Ví dụ: So sánh kiến trúc ARM và x86 trong hệ thống máy tính hiện đại..."
          : "Example: Compare ARM and x86 architecture in modern computer systems...",
        requirementsPlaceholder: locale === "vi"
          ? "Nêu yêu cầu chương mục, chuẩn trích dẫn, số trang, bảng, hình, phạm vi và tài liệu tham khảo..."
          : "Describe chapters, citation style, page count, tables, figures, scope, and references...",
      };
    }

    if (projectType === "market_research") {
      return {
        ...base,
        mainLabel: locale === "vi" ? "Thị trường / sản phẩm cần nghiên cứu" : "Market / product to research",
        mainPlaceholder: locale === "vi"
          ? "Ví dụ: Nghiên cứu thị trường xe điện Việt Nam 2026 cho phân khúc phổ thông..."
          : "Example: Research Vietnam's 2026 EV market for the affordable segment...",
      };
    }

    return base;
  })();
  const selectedDatasetFile = autoFiles.find((file) => /\.(xlsx|xls|xlsm|csv)$/i.test(file.name));
  const hasActiveDatasetSource = hasDatasetSource({ mode: dataSourceMode, files: autoFiles, url: dataSourceUrl, fileId: storedDatasetId });
  const hasRequiredPrompt = !moduleAutoFields.requiresPrompt || Boolean(autoPrompt.trim());
  const hasRequiredTemplate = autoCreationMode !== "template" || Boolean(autoTemplateFile);
  const hasRequiredData = !isDataWorkflow || (hasActiveDatasetSource && dataPreviewConfirmed);
  const canSubmitAuto = !isAutoSubmitting && hasRequiredPrompt && hasRequiredTemplate && hasRequiredData;
  const readinessItems = isDataWorkflow && dataAnalysisBranch === "interactive"
    ? [
        {
          label: locale === "vi" ? "Đã chọn nguồn dữ liệu (File / Link)" : "Dataset source selected",
          done: hasActiveDatasetSource,
        },
        {
          label: locale === "vi" ? "Bảng tính & Workspace tương tác" : "Spreadsheet & Interactive Workspace",
          done: Boolean(dataPreview),
        },
        {
          label: locale === "vi" ? "Phân tích trực tiếp (Không bắt buộc DOCX)" : "Direct analysis (DOCX optional)",
          done: true,
        },
      ]
    : [
        {
          label: isDataWorkflow
            ? locale === "vi" ? "Đã có nguồn dữ liệu" : "Dataset source provided"
            : locale === "vi" ? "Đã nhập nội dung cần tạo" : "Topic entered",
          done: isDataWorkflow ? hasActiveDatasetSource : hasRequiredPrompt,
        },
        {
          label: autoCreationMode === "template"
            ? locale === "vi" ? "Đã có mẫu Word" : "Word template attached"
            : locale === "vi" ? "Tạo mới từ đầu" : "Create from scratch",
          done: hasRequiredTemplate,
        },
        ...(isDataWorkflow ? [{
          label: locale === "vi" ? "Đã xác nhận dữ liệu đọc trước" : "Dataset preview confirmed",
          done: dataPreviewConfirmed,
        }] : []),
        {
          label: locale === "vi" ? "Số trang mục tiêu hợp lệ" : "Valid target pages",
          done: targetPages >= 1 && targetPages <= 120,
        },
      ];
  const selectedDataSheet = dataPreview?.sheets?.find((sheet: any) => sheet.name === selectedDataSheetName) || dataPreview?.sheets?.[0];
  const selectedDataColumns = selectedDataSheet?.columns || [];

  const openModuleScreen = (typeId: string) => {
    if (!guardAutoJobContextChange()) return;

    if (typeId === projectType) { setMode("auto"); return; }
    if ((autoFiles.length || dataSourceUrl || autoTemplateFile || autoRequirements || dataAnalysisRequest) && !window.confirm(locale === "vi"
      ? "Đổi module sẽ xóa dữ liệu và thiết lập hiện tại. Bạn có muốn tiếp tục?"
      : "Changing modules will clear the current data and settings. Continue?")) return;

    const moduleCopy = MODULE_SCREEN_COPY[locale][typeId as keyof typeof MODULE_SCREEN_COPY[typeof locale]];
    setProjectType(typeId);
    setMode("auto");
    setStep(1);
    setActiveJobId(null);
    setCreatedReportId(null);
    setAutoExportResult(null);
    setError(null);
    setAutoPrompt(typeId === "data_analysis" ? "" : moduleCopy?.prompt || copy.defaultPrompt);
    setAutoRequirements("");
    setAutoCreationMode("scratch");
    setDataPreview(null);
    setDataPreviewConfirmed(false);
    setSelectedDataSheetName("");
    setStoredDatasetId(null);
    setStoredDatasetName("");
    setStoredDatasetError("");
    if (typeId !== "data_analysis") {
      setAutoFiles([]);
    }
    const workflow = typeId === "data_analysis" ? "&workflow=data" : "";
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", `/projects/new?mode=auto&type=${typeId}${workflow}`);
    }
  };

  return (
    <div className="mx-auto min-w-0 w-full max-w-[1600px] overflow-x-hidden px-4 py-4 sm:px-6 lg:px-8 space-y-4">
      {/* Data workspaces keep their contextual header; other flows start at their content. */}
      {isDataWorkflow && mode === "auto" && (
      <div className="flex flex-wrap items-center gap-3 pb-1">
        <button
          type="button"
          onClick={() => isDataWorkflow && mode === "auto" && selectedAnalysisMode ? setDataAnalysisBranch(null) : router.push("/")}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:bg-slate-50 hover:text-slate-900 shadow-2xs"
          title={isDataWorkflow && selectedAnalysisMode ? copy.back : copy.home}
          aria-label={isDataWorkflow && selectedAnalysisMode ? copy.back : copy.home}
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 leading-tight">{dataAnalysisBranch === "report" ? (locale === "vi" ? "Tạo báo cáo DOCX" : "Create DOCX report") : (locale === "vi" ? "Phân tích dữ liệu" : "Data analysis")}</h1>
          <p className="text-[14px] text-slate-500 mt-0.5">
            {dataAnalysisBranch === "report" ? (locale === "vi" ? "AI phân tích dữ liệu và tạo tài liệu Word" : "AI analyzes your data and creates a Word document") : (locale === "vi" ? "Phân tích Excel / Google Sheets / CSV bằng AI" : "Analyze Excel / Google Sheets / CSV with AI")}
          </p>
        </div>
        {isDataWorkflow && mode === "auto" && <div className="flex w-full flex-wrap justify-end gap-2 sm:w-auto">
          {selectedAnalysisMode && <button type="button" onClick={() => setDataAnalysisBranch(null)} className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs font-medium hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-emerald-500">{locale === "vi" ? "Đổi chế độ" : "Change mode"}</button>}
          <button type="button" onClick={() => { if (guardAutoJobContextChange()) setMode("advanced"); }} className="rounded-md px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-emerald-500">{locale === "vi" ? "Đổi module" : "Change module"}</button>
        </div>}
      </div>
      )}

      {mode === "auto" && isDataWorkflow && !selectedAnalysisMode && !activeJobId && <DataAnalysisModeSelection locale={locale} onSelect={(next) => setDataAnalysisBranch(next === "direct-analysis" ? "interactive" : "report")} />}
      {mode === "auto" && isDataWorkflow && (dataAnalysisBranch === "report" || activeJobId) && (
        <ol aria-label={locale === "vi" ? "Tiến trình báo cáo" : "Report progress"} className="grid grid-cols-2 gap-x-4 gap-y-2 border-b border-slate-200 pb-3 text-xs text-slate-600 sm:grid-cols-3 lg:grid-cols-6">
          {(locale === "vi" ? ["Chọn dữ liệu", "Mẫu Word (tùy chọn)", "Thiết lập báo cáo", "AI phân tích & tạo nội dung", "Xem trước", "Xuất DOCX"] : ["Choose data", "Word template (optional)", "Report settings", "AI analysis & writing", "Preview", "Export DOCX"]).map((label, index) => <li key={label} className="flex items-start gap-2"><span className="font-semibold text-emerald-700">{index + 1}.</span>{label}</li>)}
        </ol>
      )}

      {storedDatasetLoading && (
        <div className="flex items-center gap-3 rounded-lg border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm text-indigo-800" aria-live="polite">
          <RefreshCw className="h-4 w-4 animate-spin" />
          <span>{locale === "vi" ? "Đang mở tập dữ liệu đã lưu…" : "Opening the saved dataset…"}</span>
        </div>
      )}

      {storedDatasetError && (
        <div role="alert" className="flex flex-col gap-3 rounded-lg border border-red-200 bg-red-50 p-4 sm:flex-row sm:items-center">
          <AlertCircle className="h-5 w-5 shrink-0 text-red-600" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-red-900">{locale === "vi" ? "Không thể mở tập dữ liệu đã lưu" : "Could not open the saved dataset"}</p>
            <p className="mt-1 break-words text-xs text-red-700">{storedDatasetError}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => setStoredDatasetReload((value) => value + 1)} className="rounded-md border border-red-200 bg-white px-3 py-2 text-xs font-medium text-red-800 hover:bg-red-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500">
              {locale === "vi" ? "Thử tải lại" : "Try again"}
            </button>
            <a href="/data" className="rounded-md px-3 py-2 text-xs font-medium text-slate-700 hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">
              {locale === "vi" ? "Về thư viện dữ liệu" : "Back to data library"}
            </a>
          </div>
        </div>
      )}

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-xl text-xs flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Keep the spreadsheet mounted while switching modes so unsaved workspace edits survive. */}
      {isInteractiveWorkspaceOpen && dataPreview && !dataPreview.error && (
          <div hidden={mode !== "auto" || !isDataWorkflow || dataAnalysisBranch !== "interactive"} data-auto-create-shell className="w-full min-w-0 overflow-hidden">
            <ExcelAnalysisWorkspace
              fileName={storedDatasetName || dataPreview.file_name || autoFiles[0]?.name || "Bảng tính dữ liệu"}
              file={autoFiles[0] || null}
              fileId={storedDatasetId || undefined}
              dataSourceUrl={dataSourceUrl}
              visualWorkbook={dataPreview.visual_workbook}
              initialAnalysis={dataPreview.initial_analysis}
              legacyData={dataPreview}
              initialAnalysisResult={interactiveAnalysisResult}
              preferredSheet={interactivePreferredSheet}
              onBackToSetup={() => setIsInteractiveWorkspaceOpen(false)}
              onSwitchToReportMode={() => setDataAnalysisBranch("report")}
              onGenerateDocx={handleCreateDocxFromInteractiveFinding}
              isGeneratingDocx={isAutoSubmitting}
              locale={locale}
            />
          </div>
      )}
      {/* MODE 1: ONE-CLICK AUTO REPORT */}
      {mode === "auto" && (!isDataWorkflow || selectedAnalysisMode || activeJobId) && !(isDataWorkflow && dataAnalysisBranch === "interactive" && isInteractiveWorkspaceOpen && dataPreview && !dataPreview.error) && (
          <div className={isDataWorkflow ? "min-w-0" : "min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-white p-4 shadow-xs sm:p-6"}>
            {!activeJobId ? (
              <div
                data-auto-create-shell
                className={`grid min-w-0 gap-6 overflow-hidden ${
                  isDataWorkflow
                    ? (dataAnalysisBranch === "report" ? "lg:grid-cols-[minmax(0,1fr)_300px]" : "grid-cols-1")
                    : "2xl:grid-cols-[300px_minmax(0,1fr)_340px]"
                }`}
              >
                {!isDataWorkflow && <>
                <div
                  className={`rounded-lg border border-slate-200 bg-slate-50 p-4 ${
                    isDataWorkflow && dataAnalysisBranch === "interactive" ? "2xl:col-span-2" : "2xl:col-span-3"
                  }`}
                >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                      {locale === "vi" ? "Module đang dùng" : "Active module"}
                    </p>
                    <h2 className="mt-1 text-lg font-bold text-slate-900">{selectedModuleScreen.title}</h2>
                    <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">{selectedModuleScreen.desc}</p>
                  </div>
                  <button
                    type="button"
	                    onClick={() => {
	                      if (!guardAutoJobContextChange()) return;
	                      setMode("advanced");
	                    }}
                    className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md bg-white px-3 py-2 text-xs font-bold text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
                  >
                    <Layers className="h-3.5 w-3.5" />
                    {locale === "vi" ? "Đổi module" : "Change module"}
                  </button>
                </div>
              </div>

              <aside className="hidden rounded-lg border border-slate-200 bg-slate-50 p-3 2xl:block 2xl:self-start">
                <div className="mb-3 px-1">
                  <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                    {locale === "vi" ? "Chọn nhanh module" : "Quick module"}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    {locale === "vi" ? "Mỗi lựa chọn đổi sang đúng màn nhập của module đó." : "Each choice switches to that module's input screen."}
                  </p>
                </div>
                <div className="space-y-1.5">
                  {PROJECT_TYPE_META.map((t) => {
                    const Icon = t.icon;
                    const isSelected = projectType === t.id;
                    const [name, desc] = copy.projectTypes[t.id as keyof typeof copy.projectTypes];
                    return (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => openModuleScreen(t.id)}
                        className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                          isSelected
                            ? "border-indigo-300 bg-white text-indigo-700 shadow-xs"
                            : "border-transparent text-slate-600 hover:border-slate-200 hover:bg-white hover:text-slate-900"
                        }`}
                      >
                        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${t.color}`}>
                          <Icon className="h-4 w-4" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-xs font-bold">{name}</span>
                          <span className="mt-0.5 line-clamp-1 block text-[11px] leading-4 text-slate-500">{desc}</span>
                        </span>
                        {isSelected && <CheckCircle2 className="h-4 w-4 shrink-0 text-indigo-600" />}
                      </button>
                    );
                  })}
                </div>
              </aside>

              </>}
              <div className="min-w-0 space-y-6 overflow-hidden">
              {/* WORKFLOW B: TẠO BÁO CÁO DOCX (KEEP 100% INTACT) */}
              {(!isDataWorkflow || dataAnalysisBranch === "report") && (
                <>
                  {/* File Attachments / Data Source for DOCX Report */}
                  <div className="space-y-2">
                    <label className="text-xs font-bold text-slate-700">
                      {isDataWorkflow ? (locale === "vi" ? "Chọn dữ liệu" : "Choose data") : moduleAutoFields.fileLabel}
                      {isDataWorkflow && <span className="ml-1 text-red-500">*</span>}
                    </label>
                    <input
                      ref={autoFileInputRef}
                      type="file"
                      multiple
                      accept={moduleAutoFields.accept}
                      onChange={(e) => {
                        if (e.target.files) handleAutoFilesChange(Array.from(e.target.files));
                      }}
                      className="hidden"
                      id="auto-file-input"
                    />

                    {isDataWorkflow ? (
                      <div className="space-y-3 rounded-lg border border-emerald-200 bg-white p-4">
                        <div className="grid grid-cols-2 gap-2 rounded-lg bg-emerald-50 p-1">
                          <button
                            type="button"
                            onClick={() => {
                              setDataSourceMode("file");
                              setStoredDatasetId(null);
                              setStoredDatasetName("");
                              setStoredDatasetError("");
                              setDataPreview(null);
                              setDataPreviewConfirmed(false);
                              setError(null);
                            }}
                            className={`inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-xs font-bold ${
                              dataSourceMode === "file" ? "bg-white text-emerald-800 shadow-sm" : "text-emerald-700 hover:bg-white/60"
                            }`}
                          >
                            <Upload className="h-3.5 w-3.5" />
                            {locale === "vi" ? "Tải file từ máy" : "Upload file"}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setDataSourceMode("url");
                              setStoredDatasetId(null);
                              setStoredDatasetName("");
                              setStoredDatasetError("");
                              setDataPreview(null);
                              setDataPreviewConfirmed(false);
                              setError(null);
                            }}
                            className={`inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-xs font-bold ${
                              dataSourceMode === "url" ? "bg-white text-emerald-800 shadow-sm" : "text-emerald-700 hover:bg-white/60"
                            }`}
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                            {locale === "vi" ? "Dán link dữ liệu" : "Paste data link"}
                          </button>
                        </div>

                        {dataSourceMode === "url" && (
                          <div className="space-y-2">
                    <GoogleDataConnection />
                            <label className="text-xs font-bold text-slate-700">
                              {locale === "vi" ? "Link dữ liệu công khai" : "Public data link"}
                            </label>
                            <div className="flex flex-col gap-2 sm:flex-row">
                              <input
                                type="url"
                                value={dataSourceUrl}
                                onChange={(e) => {
                                  setDataSourceUrl(e.target.value);
                                  setDataPreviewConfirmed(false);
                                }}
                                placeholder="https://.../data.csv hoặc Google Sheets public"
                                className="h-10 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-semibold text-slate-800 outline-none focus:border-emerald-500 focus:bg-white focus:ring-2 focus:ring-emerald-100"
                              />
                              <button
                                type="button"
                                onClick={() => previewDatasetSource(null, "url")}
                                disabled={!dataSourceUrl.trim() || isDataPreviewing}
                                className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-bold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50 transition"
                              >
                                <RefreshCw className={`h-3.5 w-3.5 ${isDataPreviewing ? "animate-spin" : ""}`} />
                                {isDataPreviewing
                                  ? locale === "vi"
                                    ? "Đang đọc dữ liệu..."
                                    : "Reading data..."
                                  : locale === "vi"
                                  ? "Đọc link"
                                  : "Read link"}
                              </button>
                            </div>
                            <p className="text-[11px] text-slate-500">
                              {locale === "vi" ? "Hỗ trợ CSV/XLSX/XLS hoặc Google Sheets public/export CSV." : "Supports CSV/XLSX/XLS or public Google Sheets/export CSV."}
                            </p>
                          </div>
                        )}

                        <div className="grid gap-3 lg:grid-cols-2">
                          <div className="space-y-2">
                            <label className="text-xs font-bold text-slate-700">
                              {locale === "vi" ? "Đọc sheet/range nào?" : "Sheet/range to read"}
                            </label>
                            <input
                              type="text"
                              value={dataSheetRange}
                              onChange={(e) => {
                                setDataSheetRange(e.target.value);
                                setDataPreviewConfirmed(false);
                              }}
                              placeholder="Sheet1, BangLuong, Sheet1!A1:H200"
                              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-semibold text-slate-800 outline-none focus:border-emerald-500 focus:bg-white focus:ring-2 focus:ring-emerald-100"
                            />
                          </div>
                          <div className="space-y-2">
                            <label className="text-xs font-bold text-slate-700">
                              {locale === "vi" ? "Nội dung yêu cầu" : "Analysis request"}
                            </label>
                            <input
                              type="text"
                              value={dataAnalysisRequest}
                              onChange={(e) => {
                                setDataAnalysisRequest(e.target.value);
                                setDataPreviewConfirmed(false);
                              }}
                              placeholder={locale === "vi" ? "Ví dụ: Phân tích lương theo phòng ban, tìm bất thường..." : "Example: Analyze salary by department, find anomalies..."}
                              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-semibold text-slate-800 outline-none focus:border-emerald-500 focus:bg-white focus:ring-2 focus:ring-emerald-100"
                            />
                          </div>
                        </div>
                      </div>
                    ) : null}

                    {isDataWorkflow && dataSourceMode === "file" && selectedDatasetFile ? (
                      <div className="rounded-lg border border-emerald-200 bg-white p-4">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                          <div className="min-w-0">
                            <p className="text-[11px] font-bold uppercase tracking-wide text-emerald-600">
                              {locale === "vi" ? "File dữ liệu đang phân tích" : "Active dataset"}
                            </p>
                            <div className="mt-1 flex min-w-0 items-center gap-2">
                              <Table className="h-4 w-4 shrink-0 text-emerald-600" />
                              <span className="truncate text-sm font-bold text-slate-900">{selectedDatasetFile.name}</span>
                            </div>
                            <p className="mt-1 text-xs text-slate-500">
                              {(selectedDatasetFile.size / 1024).toFixed(1)} KB
                              {dataPreview ? ` · ${dataPreview.sheet_count || 0} sheet · ${dataPreview.total_rows || 0} dòng · ${dataPreview.total_columns || 0} cột` : ""}
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => previewDatasetSource(selectedDatasetFile, "file")}
                              disabled={isDataPreviewing}
                              className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-2 text-xs font-bold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              <RefreshCw className={`h-3.5 w-3.5 ${isDataPreviewing ? "animate-spin" : ""}`} />
                              {locale === "vi" ? "Đọc lại" : "Read again"}
                            </button>
                            <label
                              htmlFor="auto-file-input"
                              className="inline-flex cursor-pointer items-center gap-1.5 rounded-md bg-slate-100 px-3 py-2 text-xs font-bold text-slate-700 transition hover:bg-slate-200"
                            >
                              <Upload className="h-3.5 w-3.5" />
                              {locale === "vi" ? "Đổi file dữ liệu" : "Change dataset"}
                            </label>
                            <button
                              type="button"
                              onClick={clearAutoFiles}
                              className="inline-flex items-center gap-1.5 rounded-md bg-red-50 px-3 py-2 text-xs font-bold text-red-600 transition hover:bg-red-100"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              {locale === "vi" ? "Xóa file dữ liệu" : "Remove dataset"}
                            </button>
                          </div>
                        </div>
                      </div>
                    ) : dataSourceMode === "file" ? (
                      <div className={`rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
                        isDataWorkflow ? "border-emerald-200 bg-emerald-50/40 hover:bg-emerald-50" : "border-slate-200 hover:bg-slate-50"
                      }`}>
                        <Upload className={`h-8 w-8 mx-auto mb-2 ${isDataWorkflow ? "text-emerald-500" : "text-slate-400"}`} />
                        <p className="text-xs font-bold text-slate-700">
                          {isDataWorkflow
                            ? locale === "vi"
                              ? "Kéo thả hoặc chọn file XLSX, XLS, CSV"
                              : "Drop or choose XLSX, XLS, CSV files"
                            : copy.dropFiles}
                        </p>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          {moduleAutoFields.fileHint}
                        </p>
                        <label
                          htmlFor="auto-file-input"
                          className="mt-3 inline-block cursor-pointer rounded-md bg-slate-100 px-3.5 py-1.5 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-200"
                        >
                          {copy.chooseFile}
                        </label>
                      </div>
                    ) : null}

                    {autoFiles.length > 0 && !isDataWorkflow && (
                      <div className="space-y-1.5 pt-2">
                        {autoFiles.map((f, i) => (
                          <div key={i} className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 p-2 text-xs">
                            <span className="font-medium text-slate-700 truncate max-w-sm">{f.name}</span>
                            <span className="text-slate-400">{(f.size / 1024).toFixed(1)} KB</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}
              {/* REPORT-SPECIFIC FIELDS: Word template, prompt, page count, extra requirements */}
              {(!isDataWorkflow || dataAnalysisBranch === "report") && (
                <>
                  <div className="space-y-3">
                    <p className="text-sm font-bold text-slate-900 flex items-center gap-2">
                      <Wand2 className="h-4 w-4 text-indigo-600" />
                      <span>{isDataWorkflow ? (locale === "vi" ? "Chọn mẫu Word (tùy chọn)" : "Word template (optional)") : copy.createMode}</span>
                    </p>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {[
                        {
                          id: "scratch" as const,
                          title: isDataWorkflow ? (locale === "vi" ? "Không dùng mẫu Word" : "No Word template") : copy.scratchMode,
                          desc: isDataWorkflow
                            ? (locale === "vi" ? "AI tự tạo bố cục báo cáo từ file dữ liệu đã tải lên." : "AI creates the report layout from the uploaded dataset.")
                            : copy.scratchDesc,
                          icon: Sparkles,
                        },
                        {
                          id: "template" as const,
                          title: isDataWorkflow ? (locale === "vi" ? "Có mẫu Word" : "Use Word template") : copy.templateMode,
                          desc: isDataWorkflow
                            ? (locale === "vi" ? "Tải thêm file DOCX mẫu để AI đổ kết quả phân tích vào đúng bố cục." : "Upload a DOCX template so AI writes the analysis into that layout.")
                            : copy.templateDesc,
                          icon: FileText,
                        },
                      ].map((item) => {
                        const Icon = item.icon;
                        const active = autoCreationMode === item.id;
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => setAutoCreationMode(item.id)}
                            className={`text-left rounded-lg border p-4 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                              active
                                ? "border-indigo-500 bg-indigo-50 text-indigo-950 shadow-xs"
                                : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                            }`}
                          >
                            <span className="flex items-center justify-between gap-3">
                              <span className="flex items-center gap-2 text-sm font-bold">
                                <Icon className={`h-4 w-4 ${active ? "text-indigo-600" : "text-slate-500"}`} />
                                {item.title}
                              </span>
                              {active && <Check className="h-4 w-4 text-indigo-600" />}
                            </span>
                            <span className="mt-2 block text-xs leading-5 text-slate-500">{item.desc}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {autoCreationMode === "template" && (
                    <div className="space-y-2">
                      <label className="text-xs font-bold text-slate-700">{copy.templateUpload}</label>
                      <input
                        type="file"
                        accept=".docx"
                        onChange={(e) => handleTemplateFileChange(e.target.files?.[0] || null)}
                        className="hidden"
                        id="auto-template-input"
                      />

                      {!autoTemplateFile ? (
                        <div className="rounded-lg border border-dashed border-indigo-200 bg-indigo-50/50 p-5 text-center">
                          <Upload className="mx-auto mb-2 h-7 w-7 text-indigo-500" />
                          <p className="text-xs font-bold text-slate-800">{copy.dropTemplate}</p>
                          <label
                            htmlFor="auto-template-input"
                            className="mt-3 inline-flex cursor-pointer items-center gap-1.5 rounded-md bg-white px-3.5 py-1.5 text-xs font-semibold text-indigo-700 shadow-xs ring-1 ring-indigo-100 transition hover:bg-indigo-50"
                          >
                            <Upload className="h-3.5 w-3.5" />
                            {copy.chooseFile}
                          </label>
                        </div>
                      ) : (
                        <div className="rounded-lg border border-slate-200 bg-white p-4">
                          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                            <div className="min-w-0">
                              <p className="text-xs font-bold uppercase text-slate-500">{copy.selectedTemplate}</p>
                              <div className="mt-1 flex min-w-0 items-center gap-2 text-sm font-bold text-slate-900">
                                <FileText className="h-4 w-4 shrink-0 text-indigo-600" />
                                <span className="truncate">{autoTemplateFile.name}</span>
                              </div>
                              <p className="mt-1 text-xs text-slate-500">
                                {(autoTemplateFile.size / 1024).toFixed(1)} KB
                                {templatePreview ? ` · ${templatePreview.word_count || 0} từ · ${templatePreview.tables_count || 0} bảng` : ""}
                              </p>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              <label
                                htmlFor="auto-template-input"
                                className="inline-flex cursor-pointer items-center gap-1.5 rounded-md bg-slate-100 px-3 py-2 text-xs font-bold text-slate-700 transition hover:bg-slate-200"
                              >
                                <Upload className="h-3.5 w-3.5" />
                                {copy.changeTemplate}
                              </label>
                              <button
                                type="button"
                                onClick={clearTemplateFile}
                                className="inline-flex items-center gap-1.5 rounded-md bg-red-50 px-3 py-2 text-xs font-bold text-red-600 transition hover:bg-red-100"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                                {copy.removeTemplate}
                              </button>
                            </div>
                          </div>
                        </div>
                      )}

                      {(isTemplatePreviewing || templatePreview || templatePreviewError) && (
                        <div className="rounded-lg border border-slate-200 bg-white p-4">
                          <div className="mb-3 flex items-center justify-between gap-3">
                            <h3 className="text-xs font-bold uppercase text-slate-500">{copy.templatePreview}</h3>
                            <div className="flex flex-wrap items-center justify-end gap-2">
                              {templatePreview && (
                                <span className="text-[11px] font-semibold text-slate-400">
                                  {templatePreview.word_count || 0} từ · {templatePreview.tables_count || 0} bảng
                                </span>
                              )}
                              {templatePreview && !templatePreviewError && (
                                <button
                                  type="button"
                                  onClick={() => setIsTemplateInfoHidden((value) => !value)}
                                  className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1.5 text-[11px] font-bold text-slate-700 transition hover:bg-slate-200"
                                >
                                  {isTemplateInfoHidden ? (
                                    <PanelLeftOpen className="h-3.5 w-3.5" />
                                  ) : (
                                    <PanelLeftClose className="h-3.5 w-3.5" />
                                  )}
                                  <span>{isTemplateInfoHidden ? copy.showTemplateInfo : copy.hideTemplateInfo}</span>
                                </button>
                              )}
                            </div>
                          </div>
                          {isTemplatePreviewing ? (
                            <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                              <span>{copy.templatePreviewLoading}</span>
                            </div>
                          ) : templatePreviewError ? (
                            <p className="text-xs font-medium text-red-600">{templatePreviewError}</p>
                          ) : templatePreview ? (
                            <div className={`grid gap-4 ${isTemplateInfoHidden ? "lg:grid-cols-1" : "lg:grid-cols-[260px_1fr]"}`}>
                              {!isTemplateInfoHidden && (
                                <div className="space-y-2">
                                  <p className="text-xs font-bold text-slate-800">{copy.templateStats}</p>
                                  <div className="max-h-80 space-y-1.5 overflow-y-auto pr-1 text-xs text-slate-600">
                                    {(templatePreview.headings || []).map((heading: any, idx: number) => (
                                      <div key={idx} className="rounded-lg bg-slate-50 px-2.5 py-1.5">
                                        {heading.text}
                                      </div>
                                    ))}
                                    {(templatePreview.headings || []).length === 0 && (
                                      <p className="text-slate-400">{copy.templatePreviewEmpty}</p>
                                    )}
                                  </div>
                                </div>
                              )}
                              <div>
                                <p className="mb-2 text-xs font-bold text-slate-800">{copy.fullTemplateContent}</p>
                                {templatePreview.html_document ? (
                                  <div className="h-[640px] overflow-hidden rounded-lg border border-slate-200 bg-slate-100">
                                    <iframe
                                      title={copy.templatePreview}
                                      srcDoc={templatePreview.html_document}
                                      className="h-full w-full bg-slate-100"
                                    />
                                  </div>
                                ) : (
                                  <div className="max-h-[520px] overflow-y-auto rounded-lg bg-slate-50 p-4 text-xs leading-6 text-slate-700">
                                    {(templatePreview.paragraphs || []).length > 0 ? (
                                      (templatePreview.paragraphs || []).map((paragraph: any, idx: number) => (
                                        <p key={idx} className={paragraph.is_heading ? "mt-2 font-bold text-slate-900" : "mt-1"}>
                                          {paragraph.text}
                                        </p>
                                      ))
                                    ) : (
                                      <p className="text-slate-400">{copy.templatePreviewEmpty}</p>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                          ) : null}
                        </div>
                      )}
                    </div>
                  )}

                  {isDataWorkflow && <h2 className="text-sm font-semibold text-slate-900">{locale === "vi" ? "Thiết lập báo cáo" : "Report settings"}</h2>}
                  <div className="grid gap-4 lg:grid-cols-[1fr_180px]">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <label className="text-sm font-bold text-slate-900">
                            {moduleAutoFields.mainLabel}
                            {moduleAutoFields.requiresPrompt && <span className="ml-1 text-red-500">*</span>}
                          </label>
                          <p className="mt-1 text-[11px] leading-4 text-slate-500">{moduleAutoFields.mainHint}</p>
                        </div>
                      </div>
                      <textarea
                        rows={isDataWorkflow ? 3 : 4}
                        value={autoPrompt}
                        onChange={(e) => setAutoPrompt(e.target.value)}
                        placeholder={moduleAutoFields.mainPlaceholder}
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm leading-relaxed outline-none focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-100"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-bold text-slate-900">{copy.pageCount}</label>
                      <input
                        type="number"
                        min={1}
                        max={120}
                        value={targetPages}
                        onChange={(e) => setTargetPages(Math.max(1, Math.min(120, Number(e.target.value) || 1)))}
                        className="h-12 w-full rounded-lg border border-slate-200 bg-slate-50 px-4 text-sm font-bold text-slate-900 outline-none focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-100"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-bold text-slate-900">{moduleAutoFields.requirementsLabel}</label>
                    <textarea
                      rows={3}
                      value={autoRequirements}
                      onChange={(e) => setAutoRequirements(e.target.value)}
                      placeholder={moduleAutoFields.requirementsPlaceholder}
                      className="w-full rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm leading-relaxed outline-none focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-100"
                    />
                  </div>
                </>
              )}

              {/* WORKFLOW A: PHÂN TÍCH TRỰC TIẾP (INTERACTIVE DATA ANALYSIS) */}
              {isDataWorkflow && dataAnalysisBranch === "interactive" && (
                <div className="min-w-0 space-y-4 overflow-hidden">
                  {/* If Workspace is active and dataset is loaded, render Workspace View */}
                  {isInteractiveWorkspaceOpen && dataPreview && !dataPreview.error ? (
                    <div className="min-w-0 space-y-4 overflow-hidden">
                      <ExcelAnalysisWorkspace
                        fileName={storedDatasetName || dataPreview.file_name || autoFiles[0]?.name || "Bảng tính dữ liệu"}
                        file={autoFiles[0] || null}
                        fileId={storedDatasetId || undefined}
                        dataSourceUrl={dataSourceUrl}
                        visualWorkbook={dataPreview.visual_workbook}
                        initialAnalysis={dataPreview.initial_analysis}
                        legacyData={dataPreview}
                        initialAnalysisResult={interactiveAnalysisResult}
                        preferredSheet={interactivePreferredSheet}
                        onBackToSetup={() => setIsInteractiveWorkspaceOpen(false)}
                        onSwitchToReportMode={() => setDataAnalysisBranch("report")}
                        onGenerateDocx={handleCreateDocxFromInteractiveFinding}
                        isGeneratingDocx={isAutoSubmitting}
                        locale={locale}
                      />
                    </div>
                  ) : (
                    /* Step-by-step Setup & Prompt Flow */
                    <div className="min-w-0 space-y-4 overflow-hidden">
                      {/* Show source setup until reading succeeds; changing source restores it. */}
                      {(!dataPreview || dataPreview.error || isDataPreviewing) && (
                      <div className="space-y-3.5">
                        <div className="flex items-center justify-between">
                          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                            <Upload className="h-4 w-4 text-emerald-600" />
                            <span>{locale === "vi" ? "Chọn nguồn dữ liệu bảng tính" : "Choose spreadsheet data source"}</span>
                          </h3>

                        </div>

                        {/* Mode Switcher: Tải file từ máy vs Dán link dữ liệu */}
                        <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-100 p-1">
                          <button
                            type="button"
                            onClick={() => {
                              setDataSourceMode("file");
                              setStoredDatasetId(null);
                              setStoredDatasetName("");
                              setStoredDatasetError("");
                              setDataPreview(null);
                              setDataPreviewConfirmed(false);
                              setIsInteractiveWorkspaceOpen(false);
                              setError(null);
                            }}
                            className={`inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-xs font-bold transition ${
                              dataSourceMode === "file" ? "bg-white text-emerald-800 shadow-sm" : "text-slate-600 hover:text-slate-900"
                            }`}
                          >
                            <Upload className="h-3.5 w-3.5 text-emerald-600" />
                            <span>{locale === "vi" ? "Tải file từ máy" : "Upload file"}</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setDataSourceMode("url");
                              setStoredDatasetId(null);
                              setStoredDatasetName("");
                              setStoredDatasetError("");
                              setDataPreview(null);
                              setDataPreviewConfirmed(false);
                              setIsInteractiveWorkspaceOpen(false);
                              setError(null);
                            }}
                            className={`inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-xs font-bold transition ${
                              dataSourceMode === "url" ? "bg-white text-emerald-800 shadow-sm" : "text-slate-600 hover:text-slate-900"
                            }`}
                          >
                            <ExternalLink className="h-3.5 w-3.5 text-emerald-600" />
                            <span>{locale === "vi" ? "Dán link dữ liệu" : "Paste data link"}</span>
                          </button>
                        </div>

                        {/* URL Mode Input */}
                        {dataSourceMode === "url" && (
                          <div className="space-y-2 pt-1">
                    <GoogleDataConnection />
                            <label className="text-xs font-bold text-slate-700">
                              {locale === "vi" ? "Link Google Sheets công khai hoặc file CSV/XLSX URL" : "Public Google Sheets URL or CSV/XLSX Link"}
                            </label>
                            <div className="flex flex-col gap-2 sm:flex-row">
                              <input
                                type="url"
                                value={dataSourceUrl}
                                onChange={(e) => {
                                  setDataSourceUrl(e.target.value);
                                  setDataPreviewConfirmed(false);
                                }}
                                placeholder="https://docs.google.com/spreadsheets/d/... hoặc link XLSX/CSV"
                                className="h-10 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-semibold text-slate-800 outline-none focus:border-emerald-500 focus:bg-white focus:ring-2 focus:ring-emerald-100"
                              />
                              <button
                                type="button"
                                onClick={() => previewDatasetSource(null, "url")}
                                disabled={!dataSourceUrl.trim() || isDataPreviewing}
                                className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50 transition shadow-2xs"
                              >
                                <RefreshCw className={`h-3.5 w-3.5 ${isDataPreviewing ? "animate-spin" : ""}`} />
                                <span>
                                  {isDataPreviewing
                                    ? locale === "vi" ? "Đang đọc link..." : "Reading..."
                                    : locale === "vi" ? "Đọc link" : "Read link"}
                                </span>
                              </button>
                            </div>
                            <p className="text-[11px] text-slate-400">
                              {locale === "vi"
                                ? "Google Sheets cần ở chế độ 'Bất kỳ ai có đường liên kết đều có thể xem' (Public/Viewer)."
                                : "Google Sheets must have 'Anyone with the link can view' permissions."}
                            </p>
                          </div>
                        )}

                        {/* File Mode Input */}
                        {dataSourceMode === "file" && (
                          <div className="space-y-2 pt-1">
                            <input
                              ref={autoFileInputRef}
                              type="file"
                              multiple={false}
                              accept=".xlsx,.xls,.xlsm,.csv"
                              onChange={(e) => {
                                if (e.target.files) handleAutoFilesChange(Array.from(e.target.files));
                              }}
                              className="hidden"
                              id="auto-file-input-interactive"
                            />

                            {selectedDatasetFile ? (
                              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-lg border border-slate-200 bg-slate-50/70 p-3">
                                <div className="min-w-0 flex items-center gap-2.5">
                                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-100 text-emerald-700">
                                    <Table className="h-4 w-4" />
                                  </div>
                                  <div className="min-w-0">
                                    <span className="truncate block text-xs font-bold text-slate-800">{selectedDatasetFile.name}</span>
                                    <span className="text-[11px] text-slate-400">{(selectedDatasetFile.size / 1024).toFixed(1)} KB</span>
                                  </div>
                                </div>
                                <div className="flex items-center gap-2">
                                  <button
                                    type="button"
                                    onClick={() => previewDatasetSource(selectedDatasetFile, "file")}
                                    disabled={isDataPreviewing}
                                    className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white transition hover:bg-emerald-700 disabled:opacity-50"
                                  >
                                    <RefreshCw className={`h-3.5 w-3.5 ${isDataPreviewing ? "animate-spin" : ""}`} />
                                    <span>{locale === "vi" ? "Đọc lại" : "Read again"}</span>
                                  </button>
                                  <label
                                    htmlFor="auto-file-input-interactive"
                                    className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-100 transition shadow-2xs"
                                  >
                                    <Upload className="h-3.5 w-3.5" />
                                    <span>{locale === "vi" ? "Đổi file" : "Change"}</span>
                                  </label>
                                  <button
                                    type="button"
                                    onClick={clearAutoFiles}
                                    className="inline-flex items-center gap-1.5 rounded-lg bg-red-50 px-2.5 py-1.5 text-xs font-bold text-red-600 hover:bg-red-100 transition"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div className="rounded-xl border-2 border-dashed border-emerald-200 bg-emerald-50/30 p-6 text-center hover:bg-emerald-50/60 transition">
                                <Upload className="mx-auto h-8 w-8 text-emerald-600 mb-2" />
                                <p className="text-xs font-bold text-slate-800">
                                  {locale === "vi" ? "Kéo thả hoặc chọn file XLSX, XLS, CSV" : "Drop or choose XLSX, XLS, CSV"}
                                </p>
                                <p className="text-[11px] text-slate-400 mt-0.5">
                                  {locale === "vi" ? "Hỗ trợ file Excel đa sheet hoặc bảng dữ liệu CSV" : "Supports multi-sheet Excel files or CSV spreadsheets"}
                                </p>
                                <label
                                  htmlFor="auto-file-input-interactive"
                                  className="mt-3 inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-700 transition shadow-2xs"
                                >
                                  <Upload className="h-3.5 w-3.5" />
                                  <span>{copy.chooseFile}</span>
                                </label>
                              </div>
                            )}
                          </div>
                        )}

                        {/* Progressive Reading Feedback */}
                        {isDataPreviewing && (
                          <div className="rounded-lg border border-emerald-200 bg-emerald-50/80 p-3.5 text-xs font-bold text-emerald-800 flex items-center gap-2.5 animate-pulse">
                            <RefreshCw className="h-4 w-4 animate-spin text-emerald-600 shrink-0" />
                            <span>{dataPreviewLoadingStep || (locale === "vi" ? "Đang đọc dữ liệu bảng tính..." : "Reading spreadsheet data...")}</span>
                          </div>
                        )}

                        {/* Error State with Retry button */}
                        {dataPreview?.error && !isDataPreviewing && (
                          <div className="rounded-lg border border-red-200 bg-red-50 p-3.5 text-xs font-semibold text-red-700 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5">
                            <div className="flex items-start gap-2">
                              <AlertCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
                              <span>{dataPreview.error}</span>
                            </div>
                            <button
                              type="button"
                              onClick={() => {
                                if (dataSourceMode === "url") {
                                  previewDatasetSource(null, "url");
                                } else if (selectedDatasetFile) {
                                  previewDatasetSource(selectedDatasetFile, "file");
                                }
                              }}
                              className="inline-flex items-center gap-1.5 self-start sm:self-auto rounded-md bg-red-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-700 transition shadow-2xs"
                            >
                              <RefreshCw className="h-3.5 w-3.5" />
                              <span>{locale === "vi" ? "Thử lại" : "Retry"}</span>
                            </button>
                          </div>
                        )}
                      </div>
                      )}

                      {/* BƯỚC 2 & BƯỚC 3: DỮ LIỆU ĐÃ ĐỌC & KHUNG NHẬP YÊU CẦU */}
                      {dataPreview && !dataPreview.error && (
                        <DirectAnalysisPromptPanel
                          workbook={{
                            fileName: dataPreview.file_name || autoFiles[0]?.name || "Bảng tính dữ liệu",
                            sheetCount: dataPreview.sheet_count || dataPreview.sheets?.length || 1,
                            totalRows: dataPreview.total_rows || 0,
                            totalCols: dataPreview.total_columns || 0,
                            sheets: dataPreview.sheets || [],
                            columns: selectedDataColumns || dataPreview.columns || [],
                            rawPreview: dataPreview,
                          }}
                          sheetRange={dataSheetRange}
                          onChangeSheetRange={setDataSheetRange}
                          selectedSheetName={selectedDataSheetName}
                        onSelectSheet={setSelectedDataSheetName}
                          analysisPrompt={dataAnalysisRequest}
                          onChangeAnalysisPrompt={setDataAnalysisRequest}
                          onAnalyze={handleStartInteractiveAnalysis}
                          isAnalyzing={isRunningInitialAnalysis}
                          onOpenWorkspace={handleOpenInteractiveWorkspaceOnly}
                          onChangeSource={clearAutoFiles}
                          locale={locale}
                        />
                      )}

                      {!dataPreview && !isDataPreviewing && (
                        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 p-5 text-center text-xs text-slate-500">
                          {locale === "vi"
                            ? "Sau khi đọc file hoặc link thành công, hệ thống sẽ hiển thị danh sách sheet và khung nhập yêu cầu phân tích tại đây."
                            : "After reading file or link, sheets and analysis prompt panel will appear here."}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}


            </div>

              {!(isDataWorkflow && dataAnalysisBranch === "interactive") && (
              <aside className="space-y-4 xl:sticky xl:top-6 xl:self-start">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        {locale === "vi" ? "Tóm tắt thiết lập" : "Setup summary"}
                      </p>
                      <h3 className="mt-1 text-sm font-bold text-slate-900">{selectedModuleScreen.title}</h3>
                    </div>
                    <span className="rounded-md bg-white px-2 py-1 text-[11px] font-bold text-slate-600 ring-1 ring-slate-200">
                      {selectedTypeGuide.badge}
                    </span>
                  </div>

                  <div className="mt-4 space-y-2">
                    {readinessItems.map((item) => (
                      <div key={item.label} className="flex items-center gap-2 text-xs">
                        <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
                          item.done ? "bg-emerald-100 text-emerald-700" : "bg-white text-slate-400 ring-1 ring-slate-200"
                        }`}>
                          {item.done ? <Check className="h-3 w-3" /> : <AlertCircle className="h-3 w-3" />}
                        </span>
                        <span className={item.done ? "font-semibold text-slate-800" : "text-slate-500"}>{item.label}</span>
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 border-t border-slate-200 pt-4 text-xs leading-5 text-slate-500">
                    <p>
                      {locale === "vi" ? "Đầu ra:" : "Output:"}{" "}
                      <span className="font-semibold text-slate-700">
                        {isDataWorkflow && dataAnalysisBranch === "interactive"
                          ? (locale === "vi" ? "Bảng tính tương tác & AI Copilot" : "Interactive Spreadsheet & AI Copilot")
                          : selectedTypeGuide.output}
                      </span>
                    </p>
                    <p className="mt-1">
                      {locale === "vi" ? "File đã chọn:" : "Selected files:"} <span className="font-semibold text-slate-700">{autoFiles.length + (autoTemplateFile ? 1 : 0)}</span>
                    </p>
                  </div>
                </div>

                {isDataWorkflow && dataAnalysisBranch === "interactive" ? (
                  <div className="rounded-lg border border-emerald-100 bg-emerald-50/70 p-4">
                    <p className="text-xs font-bold text-emerald-950">
                      {locale === "vi" ? "Luồng phân tích trực tiếp" : "Direct Analysis Flow"}
                    </p>
                    <div className="mt-3 space-y-2 text-xs text-emerald-800">
                      <div className="flex gap-2">
                        <span className="font-bold text-emerald-700">1.</span>
                        <span>{locale === "vi" ? "Đọc dữ liệu thật từ bảng tính" : "Read real spreadsheet data"}</span>
                      </div>
                      <div className="flex gap-2">
                        <span className="font-bold text-emerald-700">2.</span>
                        <span>{locale === "vi" ? "Phân tích theo yêu cầu" : "Analyze based on prompt"}</span>
                      </div>
                      <div className="flex gap-2">
                        <span className="font-bold text-emerald-700">3.</span>
                        <span>{locale === "vi" ? "Hiển thị kết quả trong Workspace" : "Display results in Workspace"}</span>
                      </div>
                      <div className="flex gap-2">
                        <span className="font-bold text-emerald-700">4.</span>
                        <span>{locale === "vi" ? "Hỏi AI, lọc và tô màu trực tiếp" : "Interactive AI chat, filter, highlight"}</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4">
                    <p className="text-xs font-bold text-indigo-950">
                      {locale === "vi" ? "Luồng tạo tài liệu" : "Creation flow"}
                    </p>
                    <div className="mt-3 space-y-2 text-xs text-indigo-800">
                      <div className="flex gap-2">
                        <span className="font-bold">1.</span>
                        <span>{isDataWorkflow ? (locale === "vi" ? "Đọc dữ liệu thật từ bảng tính" : "Read real spreadsheet data") : (locale === "vi" ? "Hiểu yêu cầu và lập cấu trúc" : "Understand the request and plan")}</span>
                      </div>
                      <div className="flex gap-2">
                        <span className="font-bold">2.</span>
                        <span>{locale === "vi" ? "Sinh nội dung, bảng và bố cục" : "Generate content, tables, and layout"}</span>
                      </div>
                      <div className="flex gap-2">
                        <span className="font-bold">3.</span>
                        <span>{locale === "vi" ? "Xuất Word và mở Studio chỉnh sửa" : "Export Word and open editing Studio"}</span>
                      </div>
                    </div>
                  </div>
                )}

                {isDataWorkflow && dataAnalysisBranch === "interactive" ? (
                  <div className="space-y-2">
                    {dataPreview && !dataPreview.error ? (
                      <button
                        type="button"
                        onClick={() => {
                          if (dataAnalysisRequest.trim()) {
                            handleRunSpreadsheetAnalysis(dataAnalysisRequest.trim(), selectedDataSheetName);
                          } else {
                            handleOpenInteractiveWorkspaceOnly();
                          }
                        }}
                        disabled={isRunningInitialAnalysis}
                        className="flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 text-sm font-bold text-white shadow-sm transition hover:bg-emerald-700 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                      >
                        <Sparkles className={`h-4 w-4 ${isRunningInitialAnalysis ? "animate-spin" : ""}`} />
                        <span>
                          {isRunningInitialAnalysis
                            ? (locale === "vi" ? "Đang phân tích..." : "Analyzing...")
                            : dataAnalysisRequest.trim()
                            ? (locale === "vi" ? "✨ Phân tích ngay" : "✨ Analyze now")
                            : (locale === "vi" ? "Mở Workspace bảng tính" : "Open Workspace")}
                        </span>
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => setDataAnalysisBranch("report")}
                      className="flex h-11 w-full items-center justify-center gap-2 rounded-lg border border-emerald-300 bg-white text-xs font-bold text-emerald-800 shadow-2xs transition hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                    >
                      <FileText className="h-4 w-4 text-emerald-600" />
                      <span>{locale === "vi" ? "Chuyển sang Tạo báo cáo DOCX" : "Switch to DOCX Report"}</span>
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    id="auto-create-submit-btn"
                    onClick={(e) => handleAutoCreateSubmit(e)}
                    disabled={!canSubmitAuto}
                    className="flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 text-sm font-bold text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
                  >
                    {isAutoSubmitting ? (
                      <>
                        <Sparkles className="h-4 w-4 animate-spin" />
                        <span>{copy.startingAuto}</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4" />
                        <span>{moduleAutoFields.primaryAction}</span>
                      </>
                    )}
                  </button>
                )}
              </aside>
              )}
            </div>
          ) : (
            /* REALTIME PIPELINE PROGRESS */
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
              <div className="space-y-6">
              <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-5 text-center">
                <div className="inline-flex p-3 rounded-lg bg-indigo-50 text-indigo-600">
                  {jobStatus === "completed" && !isExportingDocx ? (
                    <CheckCircle2 className="h-8 w-8" />
                  ) : jobStatus === "failed" ? (
                    <AlertCircle className="h-8 w-8 text-red-600" />
                  ) : (
                    <Sparkles className="h-8 w-8 animate-spin" />
                  )}
                </div>
                <h3 className="text-base font-bold text-slate-900">
                  {jobStatus === "completed" && autoExportResult ? copy.completedTitle : copy.autoRunningTitle}
                </h3>
                <p className="text-xs text-slate-500 max-w-md mx-auto">{jobStatusMsg}</p>
                {jobErrorMessage && (
                  <p className="mx-auto mt-2 max-w-xl rounded-md border border-red-200 bg-red-50 px-3 py-2 text-left text-xs font-medium text-red-700">
                    {jobErrorMessage}
                  </p>
                )}
              </div>

              {/* Progress Bar */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-bold text-slate-700">
                  <span>{copy.progress}</span>
                  <span className="text-indigo-600">{jobProgress}%</span>
                </div>
                <div className="h-3 w-full bg-slate-100 rounded-full overflow-hidden border border-slate-200">
                  <div
                    className="h-full bg-gradient-to-r from-indigo-500 to-indigo-600 transition-all duration-500 rounded-full"
                    style={{ width: `${jobProgress}%` }}
                  />
                </div>
              </div>

              {autoExportResult && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-sm font-bold text-emerald-900">{copy.completedTitle}</p>
                      <p className="mt-1 text-xs text-emerald-700">{copy.completedDesc}</p>
                    </div>
                    <a
                      href={resolveDownloadUrl(autoExportResult.download_url)}
                      download
                      className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white transition hover:bg-emerald-700"
                    >
                      <FileText className="h-3.5 w-3.5" />
                      <span>{copy.downloadDocx}</span>
                    </a>
                  </div>
                </div>
              )}
              </div>

              <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        {locale === "vi" ? "Nhật ký thực thi" : "Execution log"}
                      </p>
                      <p className="mt-1 text-sm font-bold text-slate-900">
                        {locale === "vi" ? "Các bước AI đã chạy" : "AI workflow steps"}
                      </p>
                    </div>
                    <span className="rounded-md bg-slate-50 px-2 py-1 text-[11px] font-bold text-slate-600 ring-1 ring-slate-200">
                      {jobStatus || "queued"}
                    </span>
                  </div>
                  <div className="mt-4 max-h-80 space-y-3 overflow-y-auto pr-1">
                    {(jobTimeline.length ? jobTimeline : [{ stage: "queued", progress: jobProgress, message: jobStatusMsg }]).map((item, idx) => {
                      const isLast = idx === (jobTimeline.length ? jobTimeline.length : 1) - 1;
                      return (
                        <div key={`${item.stage || "stage"}-${idx}`} className="flex gap-3 text-xs">
                          <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
                            isLast && jobStatus !== "completed" && jobStatus !== "failed"
                              ? "bg-indigo-100 text-indigo-700"
                              : jobStatus === "failed" && isLast
                                ? "bg-red-100 text-red-700"
                                : "bg-emerald-100 text-emerald-700"
                          }`}>
                            {jobStatus === "failed" && isLast ? <AlertCircle className="h-3 w-3" /> : <Check className="h-3 w-3" />}
                          </span>
                          <div className="min-w-0">
                            <div className="font-bold text-slate-800">{item.stage || (locale === "vi" ? "Đang xử lý" : "Processing")}</div>
                            <div className="mt-0.5 leading-5 text-slate-500">{item.message || "-"}</div>
                            <div className="mt-0.5 text-[11px] font-semibold text-slate-400">{item.progress ?? 0}%</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {jobNextAction && (
                  <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4 text-xs text-indigo-800">
                    <p className="font-bold text-indigo-950">{locale === "vi" ? "Hành động tiếp theo" : "Next action"}</p>
                    <p className="mt-1 leading-5">
                      {jobNextAction === "open_report"
                        ? locale === "vi" ? "Báo cáo đã sẵn sàng, bạn có thể mở Studio để chỉnh sửa." : "The report is ready. Open Studio to edit."
                        : jobNextAction === "retry"
                          ? locale === "vi" ? "Quy trình lỗi. Có thể chạy lại sau khi xem thông báo lỗi." : "The workflow failed. You can retry after reviewing the error."
                          : jobNextAction === "resume"
                            ? locale === "vi" ? "Quy trình đang tạm dừng, bấm Tiếp tục để chạy tiếp." : "The workflow is paused. Resume it to continue."
                            : locale === "vi" ? "Tiếp tục chờ hệ thống xử lý." : "Keep waiting for the workflow to proceed."}
                    </p>
                  </div>
                )}
              </aside>

              {/* Controls */}
              <div className="lg:col-span-2 flex flex-wrap items-center justify-center gap-3 border-t border-slate-100 pt-4">
                {isExportingDocx && (
                  <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs font-bold text-slate-600">
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    <span>{copy.exportingTemplate}</span>
                  </div>
                )}

                {createdReportId && (
                  <button
                    onClick={() => router.push(`/reports/${createdReportId}/editor`)}
                    className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition-colors"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    <span>{copy.openStudioNow}</span>
                  </button>
                )}

                {jobStatus === "running" && (
                  <button
                    onClick={handlePauseJob}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold transition-colors"
                  >
                    <Pause className="h-3.5 w-3.5" />
                    <span>{copy.pause}</span>
                  </button>
                )}

                {jobStatus === "paused" && (
                  <button
                    onClick={handleResumeJob}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition-colors"
                  >
                    <Play className="h-3.5 w-3.5" />
                    <span>{copy.resume}</span>
                  </button>
                )}

                {jobStatus === "failed" && (
                  <button
                    onClick={handleRetryJob}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition-colors"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    <span>{locale === "vi" ? "Chạy lại" : "Retry"}</span>
                  </button>
                )}

                {jobStatus !== "completed" && (
                  <button
                    onClick={handleCancelJob}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg text-xs font-bold transition-colors"
                  >
                    <XCircle className="h-3.5 w-3.5" />
                    <span>{copy.cancel}</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* MODE 3: BULK BATCH GENERATION */}
      {mode === "bulk" && (
        <div className="bg-white p-6 sm:p-8 rounded-3xl border border-slate-200 shadow-xs space-y-6">
          {!bulkBatchResult ? (
            <div className="space-y-6">
              <div>
                <h3 className="text-base font-bold text-slate-900">{copy.bulkTitle}</h3>
                <p className="text-xs text-slate-500 mt-1">
                  {copy.bulkSubtitle}
                </p>
              </div>

              <div className="border-2 border-dashed border-indigo-200 bg-indigo-50/20 rounded-2xl p-8 text-center hover:bg-indigo-50/40 transition">
                <Table className="h-10 w-10 text-indigo-500 mx-auto mb-2" />
                <p className="text-xs font-bold text-slate-800">{copy.uploadTopics}</p>
                <p className="text-[11px] text-slate-400 mt-0.5">{copy.suggestedColumns}</p>
                <input
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  onChange={handleBulkFileChange}
                  className="hidden"
                  id="bulk-file-input"
                />
                <label
                  htmlFor="bulk-file-input"
                  className="mt-4 inline-block px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold cursor-pointer transition shadow-sm"
                >
                  {bulkFile ? `${copy.selectedFile}: ${bulkFile.name}` : copy.chooseSheet}
                </label>
              </div>

              {/* Preview Table */}
              {bulkPreviewRows.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs font-bold text-slate-800">
                    <span>{copy.previewRows} ({bulkPreviewRows.length})</span>
                  </div>
                  <div className="border border-slate-200 rounded-xl overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold">
                        <tr>
                          <th className="p-2.5">#</th>
                          <th className="p-2.5">{copy.topicTitle}</th>
                          <th className="p-2.5">{copy.requirement}</th>
                          <th className="p-2.5">{copy.type}</th>
                          <th className="p-2.5">{copy.audience}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 text-slate-700">
                        {bulkPreviewRows.map((r, i) => (
                          <tr key={i} className="hover:bg-slate-50/50">
                            <td className="p-2.5 font-bold text-slate-400">{r.row_index}</td>
                            <td className="p-2.5 font-semibold text-slate-900">{r.title}</td>
                            <td className="p-2.5 text-slate-500 truncate max-w-xs">{r.prompt}</td>
                            <td className="p-2.5 capitalize">{r.type}</td>
                            <td className="p-2.5 text-slate-500">{r.audience}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <button
                    onClick={handleLaunchBulk}
                    disabled={isBulkSubmitting}
                    className="w-full h-12 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-bold shadow-md transition flex items-center justify-center gap-2"
                  >
                    {isBulkSubmitting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                    <span>{copy.launchBulkPrefix} {bulkPreviewRows.length} {copy.launchBulkSuffix}</span>
                  </button>
                </div>
              )}
            </div>
          ) : (
            /* Bulk Batch Progress */
            <div className="space-y-6 py-4 text-center">
              <div className="inline-flex p-3 rounded-2xl bg-emerald-50 text-emerald-600">
                <Check className="h-8 w-8" />
              </div>
              <h3 className="text-base font-bold text-slate-900">{copy.bulkSuccessTitle}</h3>
              <p className="text-xs text-slate-500">
                {bulkBatchResult.total_items} {copy.bulkSuccessDesc}
              </p>

              <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 max-h-60 overflow-y-auto space-y-2 text-left">
                {bulkBatchResult.jobs?.map((j: any, idx: number) => (
                  <div key={idx} className="flex items-center justify-between p-2.5 bg-white rounded-xl border border-slate-200 text-xs">
                    <span className="font-bold text-slate-800 truncate max-w-md">{j.title}</span>
                    <button
                      onClick={() => router.push(`/reports/${j.report_id}/editor`)}
                      className="text-indigo-600 font-bold hover:underline flex items-center gap-1 shrink-0"
                    >
                      <span>{copy.openStudio}</span>
                      <ExternalLink className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* MODE 2: ADVANCED WIZARD */}
      {mode === "advanced" && (
        <div className="space-y-6">
          {step === 1 && (
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
              <div className="border-b border-slate-200 bg-slate-50 px-5 py-4 sm:px-6">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <h2 className="text-base font-bold text-slate-900">{copy.step1Title}</h2>
                    <p className="mt-1 text-sm text-slate-500">{copy.step1Desc}</p>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs font-bold">
                    {[
                      locale === "vi" ? "1. Chọn module" : "1. Choose module",
                      locale === "vi" ? "2. Kiểm tra đầu vào" : "2. Check inputs",
                      locale === "vi" ? "3. Mở màn tạo" : "3. Open screen",
                    ].map((item, idx) => (
                      <span
                        key={item}
                        className={`rounded-md px-2.5 py-1.5 ring-1 ${
                          idx === 0 ? "bg-indigo-600 text-white ring-indigo-600" : "bg-white text-slate-500 ring-slate-200"
                        }`}
                      >
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="mt-4 rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs leading-relaxed text-indigo-700">
                  {locale === "vi"
                    ? "Mỗi module có màn riêng, trường nhập riêng và cách xử lý file riêng."
                    : "Each module has its own screen, inputs, and file handling."}
                </div>
              </div>

              <div className="grid min-h-[650px] gap-0 xl:grid-cols-[380px_1fr]">
                <div className="border-b border-slate-200 bg-slate-50 p-4 xl:border-b-0 xl:border-r">
                  <div className="mb-3 flex items-center justify-between gap-3 px-1">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        {locale === "vi" ? "Chọn module" : "Choose module"}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {locale === "vi" ? "Chọn đúng loại để hiện màn nhập phù hợp." : "Pick the right type to show the matching input screen."}
                      </p>
                    </div>
                  </div>
                  <div className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
                    {PROJECT_TYPE_META.map((t) => {
                      const Icon = t.icon;
                      const isSelected = projectType === t.id;
                      const isSuggested = suggestedProjectType === t.id;
                      const [name, desc] = copy.projectTypes[t.id as keyof typeof copy.projectTypes];
                      return (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => {
                            setProjectType(t.id);
                            if (t.id === "data_analysis") {
                              setDescription("");
                            }
                          }}
                          className={`flex w-full items-center gap-3 rounded-lg border px-3 py-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                            isSelected ? "border-indigo-300 bg-white text-indigo-700" : "border-transparent bg-transparent text-slate-600 hover:border-slate-200 hover:bg-white hover:text-slate-900"
                          }`}
                        >
                          <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${t.color}`}>
                            <Icon className="h-4 w-4" />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="flex items-center gap-2">
                              <span className="truncate text-sm font-bold">{name}</span>
                              {isSuggested && (
                                <span className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700 ring-1 ring-emerald-100">
                                  {locale === "vi" ? "Gợi ý" : "Suggested"}
                                </span>
                              )}
                            </span>
                            <span className="mt-0.5 line-clamp-2 block text-xs leading-5 text-slate-500">{desc}</span>
                          </span>
                          {isSelected && <CheckCircle2 className="h-4 w-4 shrink-0 text-indigo-600" />}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="p-5 sm:p-6">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        {locale === "vi" ? "Màn đang xem" : "Current screen"}
                      </p>
                      <h3 className="mt-1 text-2xl font-bold text-slate-900">{selectedModuleScreen.title}</h3>
                      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{selectedModuleScreen.desc}</p>
                    </div>
                    <span className="inline-flex shrink-0 rounded-md bg-slate-50 px-3 py-2 text-xs font-bold text-slate-600 ring-1 ring-slate-200">
                      {selectedTypeGuide.badge}
                    </span>
                  </div>

                  <div className="mt-6 grid gap-3 md:grid-cols-3">
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                      <p className="text-sm font-bold text-slate-900">{locale === "vi" ? "Dùng khi" : "Use for"}</p>
                      <p className="mt-2 text-sm leading-6 text-slate-600">{selectedTypeGuide.bestFor}</p>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                      <p className="text-sm font-bold text-slate-900">{locale === "vi" ? "Nhập gì" : "Inputs"}</p>
                      <p className="mt-2 text-sm leading-6 text-slate-600">{selectedModuleScreen.input}</p>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                      <p className="text-sm font-bold text-slate-900">{locale === "vi" ? "File cần dùng" : "Files"}</p>
                      <p className="mt-2 text-sm leading-6 text-slate-600">{selectedModuleScreen.files}</p>
                    </div>
                  </div>

                  <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_320px]">
                    <div className="rounded-lg border border-slate-200 p-4">
                      <p className="text-sm font-bold text-slate-900">
                        {locale === "vi" ? "Luồng xử lý của module" : "Module workflow"}
                      </p>
                      <div className="mt-4 grid gap-3 sm:grid-cols-3">
                        {[
                          isDataWorkflow
                            ? locale === "vi" ? "Đọc file dữ liệu" : "Read dataset"
                            : locale === "vi" ? "Hiểu yêu cầu" : "Understand request",
                          locale === "vi" ? "Lập cấu trúc phù hợp" : "Build structure",
                          locale === "vi" ? "Sinh tài liệu hoàn chỉnh" : "Generate final document",
                        ].map((item, idx) => (
                          <div key={item} className="rounded-md bg-slate-50 p-3 text-xs text-slate-600 ring-1 ring-slate-200">
                            <span className="mb-2 flex h-6 w-6 items-center justify-center rounded-full bg-white text-[11px] font-bold text-indigo-600 ring-1 ring-indigo-100">
                              {idx + 1}
                            </span>
                            <span className="font-semibold text-slate-800">{item}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4">
                      <p className="text-sm font-bold text-indigo-950">{locale === "vi" ? "Đầu ra" : "Output"}</p>
                      <p className="mt-2 text-sm leading-6 text-indigo-800">{selectedTypeGuide.output}</p>
                      <button
                        type="button"
                        onClick={() => openModuleScreen(projectType)}
                        className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-indigo-600 px-4 text-sm font-bold text-white transition hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
                      >
                        <span>{selectedModuleScreen.primary}</span>
                        <ArrowRight className="h-4 w-4" />
                      </button>
                    </div>
                  </div>

                  <div className="mt-6 rounded-lg border border-slate-200 p-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <label className="text-sm font-bold text-slate-900">
                          {projectType === "data_analysis"
                            ? locale === "vi" ? "Câu hỏi phân tích ban đầu" : "Initial analysis question"
                            : copy.ideaLabel}
                        </label>
                        <p className="mt-1 text-xs text-slate-500">
                          {projectType === "data_analysis"
                            ? locale === "vi" ? "Tùy chọn. Bạn có thể bỏ trống và tải Excel/CSV ở màn tiếp theo." : "Optional. You can leave it blank and upload Excel/CSV on the next screen."
                            : locale === "vi" ? "Nhập ngắn để AI gợi ý đúng module và cấu trúc." : "Enter a short brief so AI can suggest the right module and structure."}
                        </p>
                      </div>
                      {projectType !== "data_analysis" && (
                        <button
                          onClick={handleAnalyzeIntent}
                          disabled={isAnalyzingIntent}
                          className="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-indigo-50 px-3 py-2 text-xs font-bold text-indigo-700 transition hover:bg-indigo-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
                        >
                          {isAnalyzingIntent ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
                          <span>{copy.analyzeIdea}</span>
                        </button>
                      )}
                    </div>
                    <textarea
                      rows={3}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder={projectType === "data_analysis"
                        ? locale === "vi"
                          ? "Ví dụ: tập trung vào doanh thu, KPI, chi phí bất thường hoặc so sánh theo phòng ban..."
                          : "Example: focus on revenue, KPIs, cost anomalies, or department comparison..."
                        : copy.ideaPlaceholder}
                      className="mt-3 w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm leading-6 outline-none focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-100"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-6 bg-white p-6 sm:p-8 rounded-3xl border border-slate-200 shadow-xs">
              <div>
                <h2 className="text-sm font-bold text-slate-900">{copy.step2Title}</h2>
                <p className="text-xs text-slate-500 mt-1">{copy.step2Desc}</p>
              </div>

              <div className="border-2 border-dashed border-slate-200 rounded-2xl p-8 text-center hover:bg-slate-50">
                <Upload className="h-8 w-8 text-slate-400 mx-auto mb-2" />
                <p className="text-xs font-bold text-slate-700">{copy.uploadData}</p>
                <input
                  type="file"
                  multiple
                  accept=".pdf,.docx,.xlsx,.csv,.txt"
                  onChange={(e) => {
                    if (e.target.files) setKnowledgeFiles(Array.from(e.target.files));
                  }}
                  className="hidden"
                  id="adv-file-in"
                />
                <label htmlFor="adv-file-in" className="mt-3 inline-block px-4 py-2 bg-slate-100 hover:bg-slate-200 rounded-xl text-xs font-semibold cursor-pointer">
                  {copy.chooseDataFile}
                </label>
              </div>

              <div className="flex justify-between pt-4 border-t border-slate-100">
                <button onClick={() => setStep(1)} className="px-4 py-2 text-xs text-slate-600 font-semibold">{copy.back}</button>
                <button
                  onClick={handleGenerateOutline}
                  disabled={isGeneratingOutline}
                  className="flex items-center gap-1.5 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow-sm transition"
                >
                  {isGeneratingOutline ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                  <span>{copy.generateOutline}</span>
                </button>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-6 bg-white p-6 sm:p-8 rounded-3xl border border-slate-200 shadow-xs">
              <div>
                <h2 className="text-sm font-bold text-slate-900">{copy.step4Title}</h2>
                <p className="text-xs text-slate-500 mt-1">{copy.step4Desc}</p>
              </div>

              <div className="space-y-2">
                {outline.map((item, idx) => (
                  <div key={idx} className="p-3.5 bg-slate-50 rounded-2xl border border-slate-200 text-xs font-bold text-slate-800">
                    {copy.chapter} {idx + 1}: {item.title}
                  </div>
                ))}
              </div>

              <div className="flex justify-between pt-4 border-t border-slate-100">
                <button onClick={() => setStep(2)} className="px-4 py-2 text-xs text-slate-600 font-semibold">{copy.back}</button>
                <button
                  onClick={handleCreateAndOpenStudio}
                  disabled={isCreatingReport}
                  className="flex items-center gap-1.5 px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold shadow-md shadow-emerald-200 transition"
                >
                  {isCreatingReport ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                  <span>{copy.finishAndOpen}</span>
                </button>
              </div>
            </div>
          )}
        </div>
      )}

    </div>
  );
}

export default function UniversalProjectWizardPage() {
  return (
    <Suspense fallback={<ProjectWizardFallback />}>
      <UniversalProjectWizardContent />
    </Suspense>
  );
}

function ProjectWizardFallback() {
  const { locale } = useTranslation();
  return (
    <div className="p-8 text-center text-xs text-slate-500">
      {WIZARD_COPY[locale].loadingWizard}
    </div>
  );
}
