"use client";

import { useEffect, useState } from "react";
import { Palette, Save } from "lucide-react";
import { useTranslation } from "@/i18n/I18nContext";
import { useToast } from "@/components/Toast";
import { API_BASE } from "@/lib/api";

export function BrandSettingsPanel({ embedded = false }: { embedded?: boolean }) {
  const { t } = useTranslation();
  const toast = useToast();

  const [primaryColor, setPrimaryColor] = useState("#1E3A8A");
  const [secondaryColor, setSecondaryColor] = useState("#0D9488");
  const [fontFamily, setFontFamily] = useState("Inter");
  const [headerText, setHeaderText] = useState("DOANH NGHIỆP • BÁO CÁO CHIẾN LƯỢC");
  const [confidentiality, setConfidentiality] = useState("STRICTLY CONFIDENTIAL");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    async function loadBrandKit() {
      try {
        const token = localStorage.getItem("auth_token");
        const res = await fetch(`${API_BASE}/brand-kit`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          if (data.primary_color) setPrimaryColor(data.primary_color);
          if (data.secondary_color) setSecondaryColor(data.secondary_color);
          if (data.primary_font) setFontFamily(data.primary_font);
          if (data.header_text) setHeaderText(data.header_text);
          if (data.confidentiality_notice) setConfidentiality(data.confidentiality_notice);
        }
      } catch {
      } finally {
        setLoading(false);
      }
    }
    loadBrandKit();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const token = localStorage.getItem("auth_token");
      const res = await fetch(`${API_BASE}/brand-kit`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          primary_color: primaryColor,
          secondary_color: secondaryColor,
          primary_font: fontFamily,
          heading_font: fontFamily,
          header_text: headerText,
          confidentiality_notice: confidentiality,
        })
      });

      if (!res.ok) throw new Error("Save failed");
      toast.success(t("brandKit.brandKitSaved"));
    } catch {
      toast.error(t("common.errorOccurred"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl py-2">
      {!embedded && <div>
        <h1 className="text-xl font-bold text-slate-900">{t("brandKit.title")}</h1>
        <p className="text-xs text-slate-500">{t("brandKit.subtitle")}</p>
      </div>}

      <div aria-busy={loading} className={`bg-white p-6 rounded-2xl border border-slate-200 shadow-2xs space-y-6 text-xs transition-opacity ${loading ? "opacity-60" : "opacity-100"}`}>
        {/* Colors */}
        <div className="space-y-3">
          <h3 className="font-bold text-slate-800 text-sm flex items-center gap-2">
            <Palette className="h-4 w-4 text-indigo-600" />
            <span>{t("brandKit.title")}</span>
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-slate-600 mb-1 font-medium">{t("brandKit.primaryColor")}</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  className="h-9 w-9 rounded-lg border border-slate-200 cursor-pointer p-0.5"
                />
                <input
                  type="text"
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  className="flex-1 h-9 px-3 bg-slate-50 border border-slate-200 rounded-lg outline-none uppercase font-mono"
                />
              </div>
            </div>

            <div>
              <label className="block text-slate-600 mb-1 font-medium">{t("brandKit.secondaryColor")}</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={secondaryColor}
                  onChange={(e) => setSecondaryColor(e.target.value)}
                  className="h-9 w-9 rounded-lg border border-slate-200 cursor-pointer p-0.5"
                />
                <input
                  type="text"
                  value={secondaryColor}
                  onChange={(e) => setSecondaryColor(e.target.value)}
                  className="flex-1 h-9 px-3 bg-slate-50 border border-slate-200 rounded-lg outline-none uppercase font-mono"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Typography */}
        <div className="space-y-3 pt-4 border-t border-slate-100">
          <h3 className="font-bold text-slate-800 text-sm">{t("brandKit.primaryFont")}</h3>
          <div className="max-w-xs">
            <select
              value={fontFamily}
              onChange={(e) => setFontFamily(e.target.value)}
              className="w-full h-9 px-3 bg-slate-50 border border-slate-200 rounded-lg outline-none"
            >
              <option value="Inter">Inter (Hiện đại & Tối giản)</option>
              <option value="Calibri">Calibri (Tư vấn quản trị)</option>
              <option value="Times New Roman">Times New Roman (Hàn lâm / Tài chính)</option>
              <option value="Roboto">Roboto (Kỹ thuật)</option>
              <option value="Plus Jakarta Sans">Plus Jakarta Sans (Tạp chí cao cấp)</option>
            </select>
          </div>
        </div>

        {/* Header & Footer */}
        <div className="space-y-3 pt-4 border-t border-slate-100">
          <h3 className="font-bold text-slate-800 text-sm">{t("brandKit.headerText")} & Footer</h3>
          <div>
            <label className="block text-slate-600 mb-1 font-medium">{t("brandKit.headerText")}:</label>
            <input
              type="text"
              value={headerText}
              onChange={(e) => setHeaderText(e.target.value)}
              className="w-full h-9 px-3 bg-slate-50 border border-slate-200 rounded-lg outline-none"
            />
          </div>

          <div>
            <label className="block text-slate-600 mb-1 font-medium">{t("brandKit.confidentialityNotice")}:</label>
            <input
              type="text"
              value={confidentiality}
              onChange={(e) => setConfidentiality(e.target.value)}
              className="w-full h-9 px-3 bg-slate-50 border border-slate-200 rounded-lg outline-none"
            />
          </div>
        </div>

        <div className="pt-4 border-t border-slate-100 flex items-center justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-bold shadow-xs transition-colors disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            <span>{saving ? t("common.saving") : t("brandKit.saveBrandKit")}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
