"use client";

import { useEffect, useRef, useState } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import { Node, mergeAttributes } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
import { TextStyle } from "@tiptap/extension-text-style";
import Image from "@tiptap/extension-image";
import Placeholder from "@tiptap/extension-placeholder";
import { Table } from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import CharacterCount from "@tiptap/extension-character-count";
import {
  Bold,
  Italic,
  Underline as UnderlineIcon,
  AlignLeft,
  AlignCenter,
  AlignRight,
  AlignJustify,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Table as TableIcon,
  Sparkles,
  Sigma,
  GitBranch,
  Wand2,
  Undo2,
  Redo2,
  Strikethrough,
  Clipboard,
  Scissors,
  Copy,
  Type,
  Image as ImageIcon,
  Link,
  Minus,
  Search,
  Replace,
  ZoomIn,
  ZoomOut,
  Save,
  Rows3,
  Columns3,
  Trash2,
  UploadCloud,
  Images,
  Globe2,
  Loader2,
  X,
} from "lucide-react";
import { MermaidViewer } from "@/components/MermaidViewer";
import { HumanizeModal } from "@/components/HumanizeModal";
import { API_BASE, api } from "@/lib/api";

type ImagePanelMode = "upload" | "web" | "library" | null;
type ImageAsset = {
  id: string;
  file_name: string;
  mime_type: string;
  file_size: number;
  width?: number | null;
  height?: number | null;
  source_type: string;
  original_url?: string | null;
  source_domain?: string | null;
  source_title?: string | null;
  source_page_url?: string | null;
  license?: string | null;
  attribution?: string | null;
  content_url: string;
};
type WebImageResult = {
  id: string;
  thumbnailUrl: string;
  imageUrl: string;
  title: string;
  sourcePageUrl?: string | null;
  sourceDomain?: string | null;
  width?: number | null;
  height?: number | null;
  license?: string | null;
  attribution?: string | null;
};

const StudioImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      id: { default: null },
      assetId: { default: null },
      originalUrl: { default: null },
      width: { default: 520 },
      height: { default: null },
      alignment: { default: "center" },
      caption: { default: "" },
      alt: { default: "" },
      sourceType: { default: "upload" },
      sourceName: { default: null },
      sourceUrl: { default: null },
      license: { default: null },
      attribution: { default: null },
    };
  },
  renderHTML({ HTMLAttributes }) {
    const {
      caption,
      alignment,
      width,
      height,
      assetId,
      sourceType,
      sourceName,
      sourceUrl,
      license,
      attribution,
      ...imgAttrs
    } = HTMLAttributes;
    const figureAttrs = {
      "data-type": "image",
      "data-asset-id": assetId || "",
      "data-alignment": alignment || "center",
      "data-source-type": sourceType || "",
      "data-source-name": sourceName || "",
      "data-source-url": sourceUrl || "",
      "data-license": license || "",
      "data-attribution": attribution || "",
      class: "studio-image-node",
    };
    const imgStyle = [
      width ? `width:${Number(width)}px` : "",
      height ? `height:${Number(height)}px` : "",
      "max-width:100%",
      "height:auto",
    ].filter(Boolean).join(";");
    return [
      "figure",
      figureAttrs,
      ["img", mergeAttributes(imgAttrs, { width, height, style: imgStyle })],
      caption ? ["figcaption", {}, caption] : ["figcaption", { "data-placeholder": "true" }, ""],
    ];
  },
});

const PageBreak = Node.create({
  name: "pageBreak",
  group: "block",
  atom: true,
  parseHTML() {
    return [{ tag: "div[data-page-break]" }];
  },
  renderHTML() {
    return ["div", { "data-page-break": "true", class: "docx-page-break" }, ["span", "Ngắt trang"]];
  },
});

interface TiptapEditorProps {
  content: any;
  onChange: (plainText: string, json: any) => void;
  onAskAi?: (selectedText: string) => void;
  onSaveNow?: () => void | Promise<void>;
  projectId?: string;
  reportId?: string;
  reportTitle?: string;
  sectionTitle?: string;
}

export function TiptapEditor({
  content,
  onChange,
  onAskAi,
  onSaveNow,
  projectId,
  reportId,
  reportTitle = "",
  sectionTitle = "",
}: TiptapEditorProps) {
  const [isHumanizeOpen, setIsHumanizeOpen] = useState(false);
  const [activeSelectedText, setActiveSelectedText] = useState("");
  const [activeRibbon, setActiveRibbon] = useState<"home" | "insert" | "layout" | "review" | "view">("home");
  const [zoom, setZoom] = useState(100);
  const [fontFamily, setFontFamily] = useState("Times New Roman");
  const [fontSize, setFontSize] = useState("13");
  const [findOpen, setFindOpen] = useState(false);
  const [findQuery, setFindQuery] = useState("");
  const [replaceText, setReplaceText] = useState("");
  const [currentMatch, setCurrentMatch] = useState(0);
  const [imagePanelMode, setImagePanelMode] = useState<ImagePanelMode>(null);
  const [imageUploadError, setImageUploadError] = useState("");
  const [imageBusy, setImageBusy] = useState(false);
  const [projectImages, setProjectImages] = useState<ImageAsset[]>([]);
  const [webQuery, setWebQuery] = useState("");
  const [webLicenseMode, setWebLicenseMode] = useState("all");
  const [webResults, setWebResults] = useState<WebImageResult[]>([]);
  const [dropActive, setDropActive] = useState(false);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const editorRef = useRef<any>(null);

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3],
        },
      }),
      Underline,
      TextStyle,
      StudioImage.configure({
        inline: false,
        allowBase64: false,
      }),
      TextAlign.configure({
        types: ["heading", "paragraph"],
      }),
      PageBreak,
      Placeholder.configure({
        placeholder: "Nhập nội dung học thuật hoặc dùng AI để soạn thảo tự động...",
      }),
      Table.configure({
        resizable: true,
      }),
      TableRow,
      TableHeader,
      TableCell,
      CharacterCount,
    ],
    content: content || "",
    onUpdate: ({ editor }) => {
      const text = editor.getText();
      const json = editor.getJSON();
      onChange(text, json);
    },
    editorProps: {
      attributes: {
        class: "template-prosemirror prose prose-slate max-w-none focus:outline-none min-h-[760px] text-slate-900 font-serif",
      },
      handlePaste: (_view, event) => {
        const files = Array.from(event.clipboardData?.files || []).filter((file) => file.type.startsWith("image/"));
        if (!files.length) return false;
        event.preventDefault();
        void uploadAndInsertImage(files[0], "paste");
        return true;
      },
      handleDrop: (_view, event) => {
        const files = Array.from(event.dataTransfer?.files || []).filter((file) => file.type.startsWith("image/"));
        setDropActive(false);
        if (!files.length) return false;
        event.preventDefault();
        void uploadAndInsertImage(files[0], "drag_drop");
        return true;
      },
    },
  });

  useEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  const assetSrc = (asset: ImageAsset) => {
    if (asset.content_url?.startsWith("http")) return asset.content_url;
    const apiOrigin = API_BASE.replace(/\/api\/v1$/, "");
    return `${apiOrigin}${asset.content_url}`;
  };

  const insertImageAsset = (asset: ImageAsset) => {
    const instance = editorRef.current;
    if (!instance) return;
    instance.chain().focus().setImage({
      id: `img_${asset.id}`,
      assetId: asset.id,
      src: assetSrc(asset),
      originalUrl: asset.original_url || null,
      width: Math.min(asset.width || 520, 620),
      height: null,
      alignment: "center",
      caption: "",
      alt: asset.source_title || asset.file_name || "",
      sourceType: asset.source_type,
      sourceName: asset.source_domain || asset.file_name || null,
      sourceUrl: asset.source_page_url || asset.original_url || null,
      license: asset.license || null,
      attribution: asset.attribution || null,
    }).run();
  };

  const uploadAndInsertImage = async (file: File, sourceType: "upload" | "paste" | "drag_drop" = "upload") => {
    if (!projectId) {
      setImageUploadError("Không tìm thấy project để lưu ảnh.");
      return;
    }
    setImageBusy(true);
    setImageUploadError("");
    try {
      const formData = new FormData();
      formData.append("project_id", projectId);
      if (reportId) formData.append("report_id", reportId);
      formData.append("source_type", sourceType);
      formData.append("file", file);
      const asset = await api.assets.uploadImage(formData);
      insertImageAsset(asset);
      setProjectImages((prev) => [asset, ...prev.filter((item) => item.id !== asset.id)]);
      setImagePanelMode(null);
    } catch (err: any) {
      setImageUploadError(err.message || "Không thể tải ảnh lên.");
    } finally {
      setImageBusy(false);
    }
  };

  const loadProjectImages = async () => {
    if (!projectId) return;
    setImageBusy(true);
    setImageUploadError("");
    try {
      const assets = await api.assets.listProjectImages(projectId, reportId);
      setProjectImages(assets);
    } catch (err: any) {
      setImageUploadError(err.message || "Không thể tải thư viện ảnh.");
    } finally {
      setImageBusy(false);
    }
  };

  const searchWebImages = async (query?: string) => {
    const finalQuery = (query || webQuery).trim();
    if (!finalQuery) return;
    setImageBusy(true);
    setImageUploadError("");
    try {
      const res = await api.assets.searchImages({
        query: finalQuery,
        license_mode: webLicenseMode,
        max_results: 12,
      });
      setWebResults(res.results || []);
      if (query) setWebQuery(finalQuery);
    } catch (err: any) {
      setImageUploadError(err.message || "Không thể tìm ảnh web.");
    } finally {
      setImageBusy(false);
    }
  };

  const importWebImage = async (result: WebImageResult) => {
    if (!projectId) return;
    setImageBusy(true);
    setImageUploadError("");
    try {
      const asset = await api.assets.importWebImage({
        project_id: projectId,
        report_id: reportId,
        image_url: result.imageUrl,
        source_page_url: result.sourcePageUrl,
        title: result.title,
        license: result.license,
        attribution: result.attribution,
      });
      insertImageAsset(asset);
      setProjectImages((prev) => [asset, ...prev.filter((item) => item.id !== asset.id)]);
      setImagePanelMode(null);
    } catch (err: any) {
      setImageUploadError(err.message || "Không thể nhập ảnh web.");
    } finally {
      setImageBusy(false);
    }
  };

  const suggestImageSearch = async () => {
    setImagePanelMode("web");
    setImageBusy(true);
    setImageUploadError("");
    try {
      const res = await api.assets.suggestImageQueries({
        section_title: sectionTitle,
        section_text: editorRef.current?.getText() || "",
        report_title: reportTitle,
        max_queries: 3,
      });
      const query = res.queries?.[0] || sectionTitle || reportTitle;
      await searchWebImages(query);
    } catch (err: any) {
      setImageUploadError(err.message || "Không thể gợi ý ảnh.");
      setImageBusy(false);
    }
  };

  // Sync external content update (e.g. from AI generation)
  useEffect(() => {
    if (editor && content) {
      const currentJson = JSON.stringify(editor.getJSON());
      const newJson = typeof content === "object" ? JSON.stringify(content) : null;
      if (newJson && currentJson !== newJson) {
        editor.commands.setContent(content);
      } else if (typeof content === "string" && editor.getText() !== content) {
        editor.commands.setContent(content);
      }
    }
  }, [content, editor]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey;
      if (!mod) return;
      const key = event.key.toLowerCase();
      if (key === "s") {
        event.preventDefault();
        onSaveNow?.();
      }
      if (key === "f") {
        event.preventDefault();
        setFindOpen(true);
      }
      if (key === "h") {
        event.preventDefault();
        setFindOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onSaveNow]);

  if (!editor) {
    return (
      <div className="flex min-h-[calc(100vh-12rem)] items-center justify-center rounded-xl border border-slate-200 bg-slate-50">
        <div className="text-center">
          <Loader2 className="mx-auto mb-3 h-6 w-6 animate-spin text-indigo-600" />
          <p className="text-sm font-bold text-slate-800">Đang mở trình soạn thảo...</p>
          <p className="mt-1 text-xs text-slate-500">Hệ thống đang dựng trang A4 và thanh công cụ.</p>
        </div>
      </div>
    );
  }

  const fontFamilies = ["Times New Roman", "Arial", "Calibri", "Cambria", "Roboto", "Georgia"];
  const fontSizes = ["8", "9", "10", "11", "12", "13", "14", "16", "18", "20", "22", "24", "28", "32", "36", "48", "72"];
  const zoomLevels = [50, 75, 90, 100, 110, 125, 150, 200];
  const wordCount = editor.storage.characterCount.words();
  const charCount = editor.storage.characterCount.characters();
  const estimatedPages = Math.max(1, Math.ceil(wordCount / 300));

  const setTextStyle = (style: string) => {
    editor.chain().focus().setMark("textStyle", { style }).run();
  };

  const applyFontFamily = (value: string) => {
    setFontFamily(value);
    setTextStyle(`font-family:'${value}', serif; font-size:${fontSize}pt`);
  };

  const applyFontSize = (value: string) => {
    const clean = String(value || "13").replace(/[^\d.]/g, "") || "13";
    setFontSize(clean);
    setTextStyle(`font-family:'${fontFamily}', serif; font-size:${clean}pt`);
  };

  const insertPageBreak = () => {
    editor.chain().focus().insertContent({ type: "pageBreak" }).run();
  };

  const insertHorizontalRule = () => {
    editor.chain().focus().setHorizontalRule().run();
  };

  const insertLink = () => {
    const url = window.prompt("Nhập liên kết URL:", "https://");
    if (!url) return;
    const selected = editor.state.doc.textBetween(editor.state.selection.from, editor.state.selection.to);
    editor.chain().focus().insertContent(`<a href="${url}" target="_blank" rel="noopener noreferrer">${selected || url}</a>`).run();
  };

  const handleImageUpload = (file: File | null) => {
    if (!file || !file.type.startsWith("image/")) return;
    void uploadAndInsertImage(file, "upload");
  };

  const imageAttrs = editor.getAttributes("image") as any;
  const selectedImageAssetId = imageAttrs?.assetId as string | undefined;
  const updateSelectedImageAttrs = (attrs: Record<string, any>) => {
    if (!editor.isActive("image")) return;
    editor.chain().focus().updateAttributes("image", attrs).run();
  };

  const findMatches = () => {
    const query = findQuery.trim().toLowerCase();
    if (!query) return [] as Array<{ from: number; to: number }>;
    const matches: Array<{ from: number; to: number }> = [];
    editor.state.doc.descendants((node, pos) => {
      if (!node.isText) return;
      const text = (node.text || "").toLowerCase();
      let index = text.indexOf(query);
      while (index >= 0) {
        matches.push({ from: pos + index, to: pos + index + query.length });
        index = text.indexOf(query, index + query.length);
      }
    });
    return matches;
  };

  const goToMatch = (direction: 1 | -1) => {
    const matches = findMatches();
    if (!matches.length) return;
    const next = (currentMatch + direction + matches.length) % matches.length;
    setCurrentMatch(next);
    editor.chain().focus().setTextSelection(matches[next]).run();
  };

  const replaceCurrent = () => {
    const matches = findMatches();
    const match = matches[currentMatch];
    if (!match) return;
    editor.chain().focus().deleteRange(match).insertContentAt(match.from, replaceText).run();
  };

  const replaceAll = () => {
    const matches = findMatches();
    if (!matches.length) return;
    matches.reverse().forEach((match) => {
      editor.chain().focus().deleteRange(match).insertContentAt(match.from, replaceText).run();
    });
  };

  const toolbarButton = (active = false) =>
    `inline-flex h-8 min-w-8 items-center justify-center gap-1 rounded-md px-2 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-40 ${
      active ? "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-100" : "text-slate-700 hover:bg-slate-100"
    }`;

  const toolbarGroup = "flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-1 shadow-xs";

  const handleInsertFormula = () => {
    const formula = prompt("Nhập công thức toán học LaTeX (ví dụ: E = mc^2 hoặc \\sum_{i=1}^n x_i):", "E = mc^2");
    if (formula) {
      editor.chain().focus().insertContent(`$$${formula}$$ `).run();
    }
  };

  const handleInsertMermaid = () => {
    const code = `flowchart TD\n    A[Bắt đầu] --> B{Kiểm tra điều kiện}\n    B -->|Đúng| C[Xử lý logic AI]\n    B -->|Sai| D[Thông báo lỗi]\n    C --> E[Hoàn tất]`;
    editor.chain().focus().insertContent(`\n\`\`\`mermaid\n${code}\n\`\`\`\n`).run();
  };

  const handleOpenHumanize = () => {
    const sel = editor.state.doc.textBetween(
      editor.state.selection.from,
      editor.state.selection.to
    ) || editor.getText();
    setActiveSelectedText(sel);
    setIsHumanizeOpen(true);
  };

  const handleApplyHumanized = (newText: string) => {
    const { from, to } = editor.state.selection;
    if (from !== to) {
      editor.chain().focus().deleteRange({ from, to }).insertContent(newText).run();
    } else {
      editor.chain().focus().setContent(newText).run();
    }
  };

  // Detect any Mermaid diagrams or LaTeX blocks in raw text for dynamic rendering preview
  const currentText = editor.getText();
  const hasMermaid = currentText.includes("```mermaid");
  const mermaidMatches = currentText.match(/```mermaid([\s\S]*?)```/g);

  return (
	    <div className="flex min-h-[calc(100vh-12rem)] flex-col overflow-hidden rounded-lg border border-slate-200 bg-slate-100">
      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(event) => handleImageUpload(event.target.files?.[0] || null)}
      />

      <div className="word-processor-ribbon border-b border-slate-200 bg-white">
	        <div className="flex flex-wrap items-center gap-1 border-b border-slate-100 bg-white px-2 py-1 text-xs font-bold">
          {[
            ["home", "Trang chủ"],
            ["insert", "Chèn"],
            ["layout", "Bố cục"],
            ["review", "Rà soát"],
            ["view", "Hiển thị"],
          ].map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveRibbon(id as typeof activeRibbon)}
              className={`rounded-md px-3 py-1.5 transition ${
                activeRibbon === id ? "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-100" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => onSaveNow?.()}
            className="ml-auto inline-flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-indigo-700"
            title="Lưu ngay (Ctrl/Cmd+S)"
            aria-label="Lưu ngay"
          >
            <Save className="h-3.5 w-3.5" />
            Lưu
          </button>
        </div>

      {/* Word-like Ribbon */}
      <div className="sticky top-16 z-20 flex flex-wrap items-center gap-2 bg-white p-2 text-slate-700 shadow-xs">
        {activeRibbon === "home" && (
          <>
        <div className={toolbarGroup}>
          <button onClick={() => navigator.clipboard?.writeText(editor.state.doc.textBetween(editor.state.selection.from, editor.state.selection.to))} className={toolbarButton()} title="Sao chép" aria-label="Sao chép">
            <Copy className="h-4 w-4" />
          </button>
          <button onClick={() => document.execCommand("cut")} className={toolbarButton()} title="Cắt" aria-label="Cắt">
            <Scissors className="h-4 w-4" />
          </button>
          <button onClick={() => editor.chain().focus().insertContent(window.prompt("Dán nội dung:", "") || "").run()} className={toolbarButton()} title="Dán văn bản" aria-label="Dán văn bản">
            <Clipboard className="h-4 w-4" />
          </button>
        </div>

        <div className={toolbarGroup}>
          <button onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().undo()} className={toolbarButton()} title="Undo" aria-label="Undo">
            <Undo2 className="h-4 w-4" />
          </button>
          <button onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().redo()} className={toolbarButton()} title="Redo" aria-label="Redo">
            <Redo2 className="h-4 w-4" />
          </button>
        </div>

        <div className={toolbarGroup}>
          <Type className="mx-1 h-4 w-4 text-slate-400" />
          <select value={fontFamily} onChange={(e) => applyFontFamily(e.target.value)} className="h-8 max-w-[150px] rounded-md border border-slate-200 bg-white px-2 text-xs font-semibold outline-none">
            {fontFamilies.map((font) => <option key={font} value={font}>{font}</option>)}
          </select>
          <select value={fontSize} onChange={(e) => applyFontSize(e.target.value)} className="h-8 w-16 rounded-md border border-slate-200 bg-white px-2 text-xs font-semibold outline-none">
            {fontSizes.map((size) => <option key={size} value={size}>{size}</option>)}
          </select>
        </div>

        <div className={toolbarGroup}>
        <button
          onClick={() => editor.chain().focus().toggleBold().run()}
          className={toolbarButton(editor.isActive("bold"))}
          title="In đậm (⌘B)"
          aria-label="In đậm"
        >
          <Bold className="h-4 w-4" />
        </button>

        <button
          onClick={() => editor.chain().focus().toggleItalic().run()}
          className={toolbarButton(editor.isActive("italic"))}
          title="In nghiêng (⌘I)"
          aria-label="In nghiêng"
        >
          <Italic className="h-4 w-4" />
        </button>

        <button
          onClick={() => editor.chain().focus().toggleUnderline().run()}
          className={toolbarButton(editor.isActive("underline"))}
          title="Gạch chân (⌘U)"
          aria-label="Gạch chân"
        >
          <UnderlineIcon className="h-4 w-4" />
        </button>

        <button
          onClick={() => editor.chain().focus().toggleStrike().run()}
          className={toolbarButton(editor.isActive("strike"))}
          title="Gạch ngang"
          aria-label="Gạch ngang"
        >
          <Strikethrough className="h-4 w-4" />
        </button>
        <button onClick={() => editor.chain().focus().unsetAllMarks().clearNodes().run()} className={toolbarButton()} title="Xóa định dạng" aria-label="Xóa định dạng">Xóa</button>
        </div>

        <div className={toolbarGroup}>
        <button
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
          className={toolbarButton(editor.isActive("heading", { level: 1 }))}
          title="Heading 1 (Chương)"
          aria-label="Heading 1"
        >
          <Heading1 className="h-4 w-4" />
        </button>

        <button
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
          className={toolbarButton(editor.isActive("heading", { level: 2 }))}
          title="Heading 2 (Mục 1.1)"
          aria-label="Heading 2"
        >
          <Heading2 className="h-4 w-4" />
        </button>

        <button
          onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
          className={toolbarButton(editor.isActive("heading", { level: 3 }))}
          title="Heading 3 (Mục 1.1.1)"
          aria-label="Heading 3"
        >
          <Heading3 className="h-4 w-4" />
        </button>
	        <button onClick={() => editor.chain().focus().setParagraph().setTextAlign("justify").run()} className={toolbarButton(editor.isActive("paragraph"))} title="Văn bản thường" aria-label="Văn bản thường">Thường</button>
        </div>

        <div className={toolbarGroup}>
        <button
          onClick={() => editor.chain().focus().setTextAlign("left").run()}
          className={toolbarButton(editor.isActive({ textAlign: "left" }))}
          title="Căn trái"
          aria-label="Căn trái"
        >
          <AlignLeft className="h-4 w-4" />
        </button>

        <button
          onClick={() => editor.chain().focus().setTextAlign("center").run()}
          className={toolbarButton(editor.isActive({ textAlign: "center" }))}
          title="Căn giữa"
          aria-label="Căn giữa"
        >
          <AlignCenter className="h-4 w-4" />
        </button>

        <button
          onClick={() => editor.chain().focus().setTextAlign("right").run()}
          className={toolbarButton(editor.isActive({ textAlign: "right" }))}
          title="Căn phải"
          aria-label="Căn phải"
        >
          <AlignRight className="h-4 w-4" />
        </button>

        <button
          onClick={() => editor.chain().focus().setTextAlign("justify").run()}
          className={toolbarButton(editor.isActive({ textAlign: "justify" }))}
          title="Căn đều 2 bên (Học thuật)"
          aria-label="Căn đều"
        >
          <AlignJustify className="h-4 w-4" />
        </button>
        </div>

        <div className={toolbarGroup}>
        <button
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          className={toolbarButton(editor.isActive("bulletList"))}
          title="Danh sách dấu chấm"
          aria-label="Danh sách dấu chấm"
        >
          <List className="h-4 w-4" />
        </button>

        <button
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          className={toolbarButton(editor.isActive("orderedList"))}
          title="Danh sách số"
          aria-label="Danh sách số"
        >
          <ListOrdered className="h-4 w-4" />
        </button>
        </div>
          </>
        )}

        {activeRibbon === "insert" && (
          <>
        <div className={toolbarGroup}>
        <button
          onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}
          className={toolbarButton()}
          title="Chèn bảng (Table)"
          aria-label="Chèn bảng"
        >
          <TableIcon className="h-4 w-4" />
          <span>Bảng</span>
        </button>
        <button onClick={() => imageInputRef.current?.click()} disabled={imageBusy} className={toolbarButton()} title="Tải ảnh từ máy" aria-label="Tải ảnh từ máy">
          <ImageIcon className="h-4 w-4" />
          <span>Tải ảnh</span>
        </button>
        <button onClick={() => { setImagePanelMode("web"); if (!webResults.length) void suggestImageSearch(); }} disabled={imageBusy} className={toolbarButton()} title="Tìm ảnh thật từ web" aria-label="Tìm ảnh thật từ web">
          <Globe2 className="h-4 w-4" />
          <span>Tìm web</span>
        </button>
        <button onClick={() => { setImagePanelMode("library"); void loadProjectImages(); }} disabled={imageBusy} className={toolbarButton()} title="Thư viện ảnh dự án" aria-label="Thư viện ảnh dự án">
          <Images className="h-4 w-4" />
          <span>Thư viện</span>
        </button>
        <button onClick={suggestImageSearch} disabled={imageBusy} className={toolbarButton()} title="AI gợi ý truy vấn ảnh cho mục này" aria-label="AI gợi ý ảnh">
          <Sparkles className="h-4 w-4" />
          <span>Gợi ý ảnh</span>
        </button>
        <button onClick={insertPageBreak} className={toolbarButton()} title="Ngắt trang" aria-label="Ngắt trang">Ngắt trang</button>
        <button onClick={insertHorizontalRule} className={toolbarButton()} title="Đường kẻ ngang" aria-label="Đường kẻ ngang">
          <Minus className="h-4 w-4" />
        </button>
        <button onClick={insertLink} className={toolbarButton()} title="Chèn liên kết" aria-label="Chèn liên kết">
          <Link className="h-4 w-4" />
        </button>
        </div>

        {/* LaTeX Math Formula Button */}
        <button
          onClick={handleInsertFormula}
          className={toolbarButton()}
          title="Chèn Công thức Toán học LaTeX"
          aria-label="Chèn công thức"
        >
          <Sigma className="h-4 w-4" />
          <span>Công thức</span>
        </button>

        {/* Mermaid Diagram Button */}
        <button
          onClick={handleInsertMermaid}
          className={toolbarButton()}
          title="Chèn Sơ đồ Mermaid"
          aria-label="Chèn sơ đồ Mermaid"
        >
          <GitBranch className="h-4 w-4" />
          <span>Sơ đồ</span>
        </button>
          </>
        )}

        {activeRibbon === "layout" && (
          <div className={toolbarGroup}>
            <button onClick={() => setZoom(90)} className={toolbarButton(zoom === 90)} title="Vừa chiều rộng" aria-label="Vừa chiều rộng">Vừa rộng</button>
            <button onClick={() => setZoom(100)} className={toolbarButton(zoom === 100)} title="Zoom 100%" aria-label="Zoom 100%">100%</button>
            <button onClick={insertPageBreak} className={toolbarButton()} title="Ngắt trang" aria-label="Ngắt trang">Ngắt trang</button>
          </div>
        )}

        {activeRibbon === "review" && (
          <>
        {/* AI Humanize Button */}
        <button
          onClick={handleOpenHumanize}
          className={toolbarButton()}
          title="AI Text Humanizer (Tối ưu hóa văn phong)"
          aria-label="Tối ưu văn phong"
        >
          <Wand2 className="h-4 w-4" />
          <span>Mượt văn</span>
        </button>

        {onAskAi && (
          <button
            onClick={() => {
              const selection = editor.state.doc.textBetween(
                editor.state.selection.from,
                editor.state.selection.to
              );
              if (selection) onAskAi(selection);
            }}
            className={toolbarButton()}
            title="Gửi đoạn chọn sang AI"
            aria-label="Gửi đoạn chọn sang AI"
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span>Sửa bằng AI</span>
          </button>
        )}
          </>
        )}

        {activeRibbon === "view" && (
          <div className={toolbarGroup}>
            <button onClick={() => setZoom((value) => Math.max(50, value - 10))} className={toolbarButton()} title="Thu nhỏ" aria-label="Thu nhỏ">
              <ZoomOut className="h-4 w-4" />
            </button>
            <select value={zoom} onChange={(e) => setZoom(Number(e.target.value))} className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs font-semibold">
              {zoomLevels.map((level) => <option key={level} value={level}>{level}%</option>)}
            </select>
            <button onClick={() => setZoom((value) => Math.min(200, value + 10))} className={toolbarButton()} title="Phóng to" aria-label="Phóng to">
              <ZoomIn className="h-4 w-4" />
            </button>
            <button onClick={() => setFindOpen((value) => !value)} className={toolbarButton(findOpen)} title="Find/Replace" aria-label="Find/Replace">
              <Search className="h-4 w-4" />
              Tìm
            </button>
          </div>
        )}
      </div>
      </div>

      {findOpen && (
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs">
          <Search className="h-4 w-4 text-slate-400" />
          <input value={findQuery} onChange={(e) => { setFindQuery(e.target.value); setCurrentMatch(0); }} placeholder="Tìm kiếm..." className="h-8 w-48 rounded-md border border-slate-200 px-2 outline-none focus:border-indigo-500" />
          <input value={replaceText} onChange={(e) => setReplaceText(e.target.value)} placeholder="Thay bằng..." className="h-8 w-48 rounded-md border border-slate-200 px-2 outline-none focus:border-indigo-500" />
          <button onClick={() => goToMatch(-1)} className={toolbarButton()} type="button">Trước</button>
          <button onClick={() => goToMatch(1)} className={toolbarButton()} type="button">Tiếp</button>
          <button onClick={replaceCurrent} className={toolbarButton()} type="button"><Replace className="h-4 w-4" />Thay</button>
          <button onClick={replaceAll} className={toolbarButton()} type="button">Thay tất cả</button>
          <span className="ml-auto text-[11px] font-semibold text-slate-500">{findMatches().length} kết quả</span>
        </div>
      )}

      {imageUploadError && (
        <div className="border-b border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">
          {imageUploadError}
        </div>
      )}

      {imagePanelMode && (
        <div className="border-b border-slate-200 bg-white px-3 py-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Kho ảnh</p>
              <p className="text-sm font-bold text-slate-900">
                {imagePanelMode === "web" ? "Tìm ảnh thật từ web" : imagePanelMode === "library" ? "Thư viện ảnh dự án" : "Tải ảnh từ máy"}
              </p>
            </div>
            <button onClick={() => setImagePanelMode(null)} className={toolbarButton()} type="button" aria-label="Đóng panel ảnh">
              <X className="h-4 w-4" />
            </button>
          </div>

          {imagePanelMode === "upload" && (
            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-center">
              <UploadCloud className="mx-auto h-6 w-6 text-slate-400" />
              <p className="mt-2 text-sm font-bold text-slate-800">Kéo thả PNG, JPG, WEBP hoặc GIF vào trang soạn thảo</p>
              <p className="mt-1 text-xs text-slate-500">Ảnh sẽ được lưu thành ImageAsset thật trong hệ thống.</p>
              <button onClick={() => imageInputRef.current?.click()} className="mt-3 rounded-md bg-indigo-600 px-3 py-2 text-xs font-bold text-white hover:bg-indigo-700" type="button">
                Chọn ảnh từ máy
              </button>
            </div>
          )}

          {imagePanelMode === "web" && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={webQuery}
                  onChange={(event) => setWebQuery(event.target.value)}
                  onKeyDown={(event) => { if (event.key === "Enter") void searchWebImages(); }}
                  placeholder="Ví dụ: sơ đồ kiến trúc máy tính, dashboard doanh thu..."
                  className="h-9 min-w-64 flex-1 rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-indigo-500"
                />
                <select value={webLicenseMode} onChange={(event) => setWebLicenseMode(event.target.value)} className="h-9 rounded-md border border-slate-200 px-2 text-xs font-semibold">
                  <option value="all">Tất cả</option>
                  <option value="free_to_use">Miễn phí sử dụng</option>
                  <option value="creative_commons">Creative Commons</option>
                  <option value="stock_free">Ảnh stock miễn phí</option>
                </select>
                <button onClick={() => void searchWebImages()} disabled={imageBusy || !webQuery.trim()} className="inline-flex h-9 items-center gap-2 rounded-md bg-indigo-600 px-3 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-60" type="button">
                  {imageBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  Tìm
                </button>
              </div>
              <div className="grid max-h-72 grid-cols-2 gap-2 overflow-auto md:grid-cols-4">
                {webResults.map((result) => (
                  <button key={result.id} onClick={() => void importWebImage(result)} className="overflow-hidden rounded-lg border border-slate-200 bg-white text-left hover:border-indigo-300 hover:bg-indigo-50/40" type="button">
                    <img src={result.thumbnailUrl} alt={result.title} className="h-24 w-full object-cover" />
                    <div className="space-y-1 p-2">
                      <p className="line-clamp-2 text-xs font-bold text-slate-800">{result.title}</p>
                      <p className="truncate text-[11px] text-slate-500">{result.sourceDomain || "Nguồn web"}</p>
                      <p className="truncate text-[11px] text-slate-500">{result.license || "Chưa có metadata license"}</p>
                    </div>
                  </button>
                ))}
                {!imageBusy && !webResults.length && (
                  <div className="col-span-full rounded-lg border border-dashed border-slate-300 p-4 text-center text-xs text-slate-500">
                    Nhập từ khóa để tìm ảnh qua provider chính thức. Ảnh chọn sẽ được import và lưu local.
                  </div>
                )}
              </div>
            </div>
          )}

          {imagePanelMode === "library" && (
            <div className="grid max-h-72 grid-cols-2 gap-2 overflow-auto md:grid-cols-5">
              {projectImages.map((asset) => (
                <button key={asset.id} onClick={() => { insertImageAsset(asset); setImagePanelMode(null); }} className="overflow-hidden rounded-lg border border-slate-200 bg-white text-left hover:border-indigo-300 hover:bg-indigo-50/40" type="button">
                  <img src={assetSrc(asset)} alt={asset.file_name} className="h-24 w-full object-cover" />
                  <div className="space-y-1 p-2">
                    <p className="truncate text-xs font-bold text-slate-800">{asset.file_name}</p>
                    <p className="truncate text-[11px] text-slate-500">{asset.source_domain || asset.source_type}</p>
                  </div>
                </button>
              ))}
              {!imageBusy && !projectImages.length && (
                <div className="col-span-full rounded-lg border border-dashed border-slate-300 p-4 text-center text-xs text-slate-500">
                  Dự án chưa có ảnh nào. Hãy upload, paste hoặc tìm ảnh web trước.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Editor Content Area */}
	      <div
	        className={`relative flex-1 overflow-auto bg-[#e5ebf3] px-3 py-6 sm:px-6 sm:py-8 ${dropActive ? "ring-2 ring-inset ring-indigo-400" : ""}`}
        onDragEnter={() => setDropActive(true)}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDropActive(false)}
      >
        {dropActive && (
          <div className="pointer-events-none absolute inset-4 z-30 flex items-center justify-center rounded-xl border-2 border-dashed border-indigo-400 bg-indigo-50/80 text-sm font-bold text-indigo-700">
            Thả ảnh vào đây để lưu và chèn vào tài liệu
          </div>
        )}
        <div
          className="mx-auto origin-top transition-transform"
          style={{ width: "210mm", transform: `scale(${zoom / 100})`, marginBottom: `${Math.max(0, (zoom - 100) * 2)}px` }}
        >
	          <div className="word-page min-h-[297mm] bg-white px-[20mm] py-[20mm] shadow-sm ring-1 ring-slate-300/80">
	            <EditorContent editor={editor} />
	          </div>
	        </div>
	      </div>

      {editor.isActive("image") && (
        <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 bg-white px-3 py-2 text-xs">
          <span className="font-bold text-slate-500">Ảnh</span>
          <button onClick={() => updateSelectedImageAttrs({ alignment: "left" })} className={toolbarButton(imageAttrs.alignment === "left")} type="button" title="Căn trái">
            <AlignLeft className="h-4 w-4" />
          </button>
          <button onClick={() => updateSelectedImageAttrs({ alignment: "center" })} className={toolbarButton(imageAttrs.alignment === "center")} type="button" title="Căn giữa">
            <AlignCenter className="h-4 w-4" />
          </button>
          <button onClick={() => updateSelectedImageAttrs({ alignment: "right" })} className={toolbarButton(imageAttrs.alignment === "right")} type="button" title="Căn phải">
            <AlignRight className="h-4 w-4" />
          </button>
          <label className="flex items-center gap-1 text-[11px] font-semibold text-slate-500">
            W
            <input
              value={imageAttrs.width || 520}
              onChange={(event) => updateSelectedImageAttrs({ width: Math.max(80, Math.min(680, Number(event.target.value) || 520)) })}
              className="h-8 w-20 rounded-md border border-slate-200 px-2 text-xs"
              type="number"
              min={80}
              max={680}
            />
          </label>
          <input
            value={imageAttrs.caption || ""}
            onChange={(event) => updateSelectedImageAttrs({ caption: event.target.value })}
            placeholder="Caption: Hình 1.1. ..."
            className="h-8 min-w-56 flex-1 rounded-md border border-slate-200 px-2 text-xs"
          />
          <input
            value={imageAttrs.alt || ""}
            onChange={(event) => updateSelectedImageAttrs({ alt: event.target.value })}
            placeholder="Alt text"
            className="h-8 min-w-40 rounded-md border border-slate-200 px-2 text-xs"
          />
          <button onClick={() => imageInputRef.current?.click()} className={toolbarButton()} type="button">
            Đổi ảnh
          </button>
          {selectedImageAssetId && (
            imageAttrs.sourceUrl ? (
              <a
                href={imageAttrs.sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="truncate text-[11px] font-semibold text-indigo-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
              >
                Nguồn: {imageAttrs.sourceName || imageAttrs.sourceType || "asset"} {imageAttrs.license ? `· ${imageAttrs.license}` : ""}
              </a>
            ) : (
              <span className="truncate text-[11px] font-semibold text-amber-700">Ảnh chưa có liên kết nguồn</span>
            )
          )}
          {selectedImageAssetId && imageAttrs.attribution && (
            <span className="max-w-72 truncate text-[11px] text-slate-500" title={imageAttrs.attribution}>
              Ghi công: {imageAttrs.attribution}
            </span>
          )}
        </div>
      )}

      {editor.isActive("table") && (
        <div className="flex flex-wrap items-center gap-1 border-t border-slate-200 bg-white px-3 py-2 text-xs">
          <span className="mr-2 font-bold text-slate-500">Bảng</span>
          <button onClick={() => editor.chain().focus().addRowBefore().run()} className={toolbarButton()}><Rows3 className="h-4 w-4" />Row trên</button>
          <button onClick={() => editor.chain().focus().addRowAfter().run()} className={toolbarButton()}><Rows3 className="h-4 w-4" />Row dưới</button>
          <button onClick={() => editor.chain().focus().addColumnBefore().run()} className={toolbarButton()}><Columns3 className="h-4 w-4" />Cột trái</button>
          <button onClick={() => editor.chain().focus().addColumnAfter().run()} className={toolbarButton()}><Columns3 className="h-4 w-4" />Cột phải</button>
          <button onClick={() => editor.chain().focus().deleteRow().run()} className={toolbarButton()}><Trash2 className="h-4 w-4" />Xóa row</button>
          <button onClick={() => editor.chain().focus().deleteColumn().run()} className={toolbarButton()}><Trash2 className="h-4 w-4" />Xóa cột</button>
          <button onClick={() => editor.chain().focus().deleteTable().run()} className={toolbarButton()}><Trash2 className="h-4 w-4" />Xóa bảng</button>
          <button onClick={() => editor.chain().focus().mergeCells().run()} className={toolbarButton()}>Gộp ô</button>
          <button onClick={() => editor.chain().focus().splitCell().run()} className={toolbarButton()}>Tách ô</button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-500">
        <span>Trang 1 / {estimatedPages}</span>
        <span>Từ: {wordCount.toLocaleString("vi-VN")}</span>
        <span>Ký tự: {charCount.toLocaleString("vi-VN")}</span>
	        <span>Ngôn ngữ: Tiếng Việt</span>
	        <span className="hidden items-center gap-1 rounded bg-slate-50 px-1.5 py-0.5 text-slate-600 ring-1 ring-slate-200 sm:inline-flex">
	          <AlignJustify className="h-3 w-3" />
	          Căn đều hai bên
	        </span>
        <span className="ml-auto flex items-center gap-1">
          <button onClick={() => setZoom((value) => Math.max(50, value - 10))} className="rounded px-1.5 py-0.5 hover:bg-slate-100" type="button">-</button>
          {zoom}%
          <button onClick={() => setZoom((value) => Math.min(200, value + 10))} className="rounded px-1.5 py-0.5 hover:bg-slate-100" type="button">+</button>
        </span>
      </div>

      {/* Live Mermaid Diagrams Rendered Section (if present in doc) */}
      {hasMermaid && mermaidMatches && (
        <div className="p-6 border-t border-slate-100 bg-slate-50/50 space-y-4">
          <div className="flex items-center space-x-2 text-xs font-bold text-slate-700">
            <GitBranch className="h-4 w-4 text-purple-600" />
            <span>Xem trước Sơ đồ Mermaid trong tài liệu:</span>
          </div>
          {mermaidMatches.map((block, idx) => {
            const raw = block.replace(/```mermaid/g, "").replace(/```/g, "").trim();
            return <MermaidViewer key={idx} code={raw} title={`Sơ đồ #${idx + 1}`} />;
          })}
        </div>
      )}

      {/* Humanize Modal */}
      <HumanizeModal
        initialText={activeSelectedText}
        isOpen={isHumanizeOpen}
        onClose={() => setIsHumanizeOpen(false)}
        onApply={handleApplyHumanized}
      />

    </div>
  );
}
