import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const componentDir = resolve(testDir, "../../components");
const libDir = resolve(testDir, "..");

test("workspace separates analysis action from Ask AI chat", () => {
  const source = readFileSync(resolve(componentDir, "ExcelAnalysisWorkspace.tsx"), "utf8");

  assert.match(source, /Phân tích dữ liệu/);
  assert.match(source, /Phân tích/);
  assert.match(source, /api\.data\.workbookAnalysisAction/);
  assert.match(source, /analysisHistory/);
  assert.match(source, /lastAnalysisResult/);
  assert.doesNotMatch(source, /initialPrompt=\{initialAnalysisPrompt\}/);
});

test("chat panel renders workbook context, source chips, and pending actions", () => {
  const source = readFileSync(resolve(componentDir, "ExcelAIChatPanel.tsx"), "utf8");

  assert.match(source, /AI Copilot/);
  assert.match(source, /Hỏi về dữ liệu/);
  assert.match(source, /Nguồn:/);
  assert.match(source, /pending_actions/);
  assert.match(source, /requires_confirmation/);
  assert.match(source, /Đang hỏi về/);
  assert.match(source, /onClose/);
});

test("chat panel hides on outside click without losing conversation state", () => {
  const source = readFileSync(resolve(componentDir, "ExcelAnalysisWorkspace.tsx"), "utf8");

  assert.match(source, /const chatPanelRef = useRef<HTMLDivElement \| null>\(null\)/);
  assert.match(source, /const \[hasOpenedChat, setHasOpenedChat\] = useState<boolean>\(false\)/);
  assert.match(source, /document\.addEventListener\("mousedown", handleClickOutside\)/);
  assert.match(source, /chatPanelRef\.current\.contains\(event\.target as Node\)/);
  assert.match(source, /hasOpenedChat && \(/);
  assert.doesNotMatch(source, /\) : \(\s*<div className="fixed bottom-6 right-6 z-50[\s\S]*<ExcelAIChatPanel/);
});

test("AI button avoids the analysis prompt bar and prompt text can choose highlight color", () => {
  const source = readFileSync(resolve(componentDir, "ExcelAnalysisWorkspace.tsx"), "utf8");

  assert.match(source, /const floatingChatButtonOffsetClass = "bottom-44 right-6"/);
  assert.match(source, /className=\{`fixed \$\{floatingChatButtonOffsetClass\} z-40`\}/);
  assert.doesNotMatch(source, /fixed bottom-28 right-6 z-40/);
  assert.match(source, /function resolvePromptHighlightColor/);
  assert.match(source, /màu đỏ|mau do|tô đỏ|to do/);
  assert.match(source, /màu vàng|mau vang|tô vàng|to vang/);
  assert.match(source, /const resolvedHighlightColor = resolvePromptHighlightColor\(prompt, activeHighlightColor\)/);
  assert.match(source, /formData\.append\("highlight_color", resolvedHighlightColor\)/);
  assert.match(source, /setActiveHighlightColor\(resolvedHighlightColor\)/);
});

test("floating AI and analysis controls use concise labels without duplicate icons", () => {
  const source = readFileSync(resolve(componentDir, "ExcelAnalysisWorkspace.tsx"), "utf8");

  assert.match(source, /locale === "vi" \? "Phân tích" : "Analyze"/);
  assert.doesNotMatch(source, /locale === "vi" \? "Chạy phân tích" : "Analyze"/);
  assert.match(source, /<Sparkles className="h-4 w-4 text-amber-300/);
  assert.match(source, /locale === "vi" \? "Hỏi AI" : "Ask AI"/);
  assert.doesNotMatch(source, /locale === "vi" \? "✨ Hỏi AI" : "✨ Ask AI"/);
});

test("analysis result banners render markdown emphasis instead of raw asterisks", () => {
  const source = readFileSync(resolve(componentDir, "ExcelAnalysisWorkspace.tsx"), "utf8");

  assert.match(source, /function renderInlineMarkdown/);
  assert.match(source, /part\.startsWith\("\*\*"\) && part\.endsWith\("\*\*"\)/);
  assert.match(source, /\{renderInlineMarkdown\(lastAnalysisResult\.answer\)\}/);
  assert.match(source, /\{renderInlineMarkdown\(analysisActionStatus\)\}/);
  assert.doesNotMatch(source, /\n\s*\{lastAnalysisResult\.answer\}\n/);
  assert.doesNotMatch(source, /⚡ \{analysisActionStatus\}/);
});

test("manual analysis prompts do not get constrained to a single selected cell", () => {
  const source = readFileSync(resolve(componentDir, "ExcelAnalysisWorkspace.tsx"), "utf8");

  assert.match(source, /function shouldUseSelectedRangeForAnalysis/);
  assert.match(source, /selectedRange\.includes\(":"\)/);
  assert.match(source, /vùng chọn|vung chon|ô đang chọn|o dang chon/);
  assert.match(source, /const shouldUseSelectedRange = .*shouldUseSelectedRangeForAnalysis\(prompt, selectedRange\)/);
  assert.match(source, /if \(shouldUseSelectedRange\) formData\.append\("selected_range", selectedRange as string\)/);
  assert.doesNotMatch(source, /if \(selectedRange\) formData\.append\("selected_range", selectedRange\)/);
});

test("chat prompts also avoid accidental single-cell selected range constraints", () => {
  const source = readFileSync(resolve(componentDir, "ExcelAIChatPanel.tsx"), "utf8");

  assert.match(source, /function shouldUseSelectedRangeForChat/);
  assert.match(source, /selectedRange\.includes\(":"\)/);
  assert.match(source, /const shouldUseSelectedRange = .*shouldUseSelectedRangeForChat\(query, selectedRange\)/);
  assert.match(source, /if \(shouldUseSelectedRange\) \{/);
  assert.doesNotMatch(source, /if \(selectedRange\) \{\s*formData\.append\("selected_range", selectedRange\)/);
});

test("chat highlights honor colors requested in the user's message", () => {
  const source = readFileSync(resolve(componentDir, "ExcelAIChatPanel.tsx"), "utf8");

  assert.match(source, /activeHighlightColor\?\: string/);
  assert.match(source, /onHighlightColorChange\?\: \(color: string\) => void/);
  assert.match(source, /function resolveChatPromptHighlightColor/);
  assert.match(source, /xanh nhạt|xanh nhat/);
  assert.match(source, /const requestedHighlightColor = resolveChatPromptHighlightColor\(query, activeHighlightColor\)/);
  assert.match(source, /requestedHighlightColor\.isExplicit/);
  assert.match(source, /onHighlightColorChange\?\.\(requestedHighlightColor\.color\)/);
  assert.match(source, /highlightColor: requestedHighlightColor\.color/);
  assert.doesNotMatch(source, /onHighlightCells\(\s*activeSheetName,\s*msg\.result\.matched_cells\.map\(\(c: any\) => c\.address\),\s*"#FEF08A"/);
});

test("frontend api exposes separate workbook analysis action endpoint", () => {
  const source = readFileSync(resolve(libDir, "api.ts"), "utf8");

  assert.match(source, /workbookAnalysisAction/);
  assert.match(source, /\/data\/workbook-analysis-action/);
});

test("highlighted workbook downloads resolve API-relative URLs against the API origin", () => {
  const apiSource = readFileSync(resolve(libDir, "api.ts"), "utf8");
  const workspaceSource = readFileSync(resolve(componentDir, "ExcelAnalysisWorkspace.tsx"), "utf8");
  const chatSource = readFileSync(resolve(componentDir, "ExcelAIChatPanel.tsx"), "utf8");

  assert.match(apiSource, /export function resolveApiDownloadUrl/);
  assert.match(apiSource, /const apiOrigin = API_BASE\.replace/);
  assert.match(apiSource, /api\\\/v1\\\/\?\$/);
  assert.match(workspaceSource, /import \{ api, resolveApiDownloadUrl \} from "@\/lib\/api"/);
  assert.match(workspaceSource, /const fullUrl = resolveApiDownloadUrl\(res\.download_url\)/);
  assert.match(chatSource, /import \{ api, resolveApiDownloadUrl \} from "@\/lib\/api"/);
  assert.match(chatSource, /setDownloadSuccessUrl\(resolveApiDownloadUrl\(res\.download_url\)\)/);
  assert.doesNotMatch(workspaceSource, /NEXT_PUBLIC_API_URL[\s\S]*res\.download_url/);
});

test("matched cell actions use normalized cell addresses for scroll highlight and xlsx export", () => {
  const workspaceSource = readFileSync(resolve(componentDir, "ExcelAnalysisWorkspace.tsx"), "utf8");
  const chatSource = readFileSync(resolve(componentDir, "ExcelAIChatPanel.tsx"), "utf8");

  assert.match(workspaceSource, /function getMatchedCellAddress/);
  assert.match(chatSource, /function getMatchedCellAddress/);
  assert.doesNotMatch(workspaceSource, /matched_cells[\s\S]{0,120}\.address/);
  assert.doesNotMatch(chatSource, /matched_cells[\s\S]{0,120}\.address/);
  assert.doesNotMatch(chatSource, /matched_cells\.map\(\(c: any\) => c\.address\)/);
});

test("new project data workspace is not nested inside the auto-create submit form", () => {
  const source = readFileSync(resolve(testDir, "../../app/projects/new/page.tsx"), "utf8");

  assert.doesNotMatch(source, /<form\s+onSubmit=\{handleAutoCreateSubmit\}[\s\S]*<ExcelAnalysisWorkspace/);
  assert.match(source, /data-auto-create-shell/);
  assert.doesNotMatch(source, /type="submit"\s+id="auto-create-submit-btn"/);
});

test("Ask AI chat submit events cannot bubble into parent analysis forms", () => {
  const source = readFileSync(resolve(componentDir, "ExcelAIChatPanel.tsx"), "utf8");

  assert.match(source, /handleSendMessage[\s\S]*event\?\.preventDefault\(\)/);
  assert.match(source, /handleSendMessage[\s\S]*event\?\.stopPropagation\(\)/);
  assert.match(source, /onKeyDown=\{\(e\) => \{[\s\S]*e\.preventDefault\(\);[\s\S]*e\.stopPropagation\(\);[\s\S]*handleSendMessage\(undefined, e\)/);
  assert.match(source, /onClick=\{\(e\) => handleSendMessage\(undefined, e\)\}/);
  assert.match(source, /onClick=\{\(e\) => handleSendMessage\(qp\.prompt, e\)\}/);
});

test("setup analysis prompt calls Analysis Engine instead of seeding Chat AI", () => {
  const pageSource = readFileSync(resolve(testDir, "../../app/projects/new/page.tsx"), "utf8");
  const workspaceSource = readFileSync(resolve(componentDir, "ExcelAnalysisWorkspace.tsx"), "utf8");

  assert.match(pageSource, /const handleRunSpreadsheetAnalysis/);
  assert.match(pageSource, /api\.data\.workbookAnalysisAction/);
  assert.match(pageSource, /formData\.append\("scope", JSON\.stringify\(\{ type: "workbook" \}\)\)/);
  assert.match(pageSource, /initialAnalysisResult=\{interactiveAnalysisResult\}/);
  assert.doesNotMatch(pageSource, /setInteractiveInitialPrompt\(prompt\)/);
  assert.doesNotMatch(pageSource, /initialAnalysisPrompt=\{interactiveInitialPrompt\}/);
  assert.match(workspaceSource, /initialAnalysisResult/);
  assert.match(workspaceSource, /useState<"overview" \| "stats" \| "charts" \| "quality" \| "ai">\("overview"\)/);
  assert.match(workspaceSource, /const \[isChatOpen, setIsChatOpen\] = useState<boolean>\(false\)/);
  assert.match(workspaceSource, /Floating AI Copilot/);
});

test("push to Word uses the latest workbook analysis result as the report request", () => {
  const pageSource = readFileSync(resolve(testDir, "../../app/projects/new/page.tsx"), "utf8");
  const workspaceSource = readFileSync(resolve(componentDir, "ExcelAnalysisWorkspace.tsx"), "utf8");

  assert.match(workspaceSource, /onGenerateDocx\?\:\s*\(analysisResult\?\:\s*any\)\s*=>\s*void/);
  assert.match(workspaceSource, /onGenerateDocx\(currentRes\)/);
  assert.doesNotMatch(workspaceSource, /if \(onGenerateDocx\) \{\s*onGenerateDocx\(\);\s*return;\s*\}/);
  assert.match(pageSource, /const buildInteractiveReportAnalysisRequest/);
  assert.match(pageSource, /analysisRequestOverride/);
  assert.match(pageSource, /handleCreateDocxFromInteractiveFinding/);
  assert.match(pageSource, /onGenerateDocx=\{handleCreateDocxFromInteractiveFinding\}/);
});

test("scope selection lives in the analysis workspace, not upload setup", () => {
  const setup = readFileSync(resolve(componentDir, "DirectAnalysisPromptPanel.tsx"), "utf8");
  const workspace = readFileSync(resolve(componentDir, "ExcelAnalysisWorkspace.tsx"), "utf8");
  assert.doesNotMatch(setup, /Phạm vi phân tích|analysisScopeMode|analysisRange/);
  assert.match(workspace, /Bảng cần phân tích/);
  assert.match(workspace, /Chọn tất cả/);
  assert.match(workspace, /formData\.append\("scope", JSON\.stringify\(analysisScope\)\)/);
});
