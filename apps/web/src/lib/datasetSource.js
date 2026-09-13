export function hasDatasetSource({ mode, files, url, fileId }) {
  if (mode === "url") return Boolean((url || "").trim());
  return Boolean((fileId || "").trim()) || (files || []).some((file) => /\.(xlsx|xls|xlsm|csv)$/i.test(file.name || ""));
}

export function buildDatasetSourcePromptParts({ locale, mode, files, url, fileId, fileName, sheetRange, analysisRequest }) {
  const vi = locale === "vi";
  const source = mode === "url"
    ? (url || "").trim()
    : (files || []).map((file) => file.name).filter(Boolean).join(", ") || (fileName || fileId || "").trim();

  return [
    vi ? `Nguồn dữ liệu bắt buộc: ${source}` : `Required data source: ${source}`,
    (sheetRange || "").trim()
      ? vi
        ? `Sheet/range cần đọc: ${(sheetRange || "").trim()}`
        : `Sheet/range to read: ${(sheetRange || "").trim()}`
      : "",
    (analysisRequest || "").trim()
      ? vi
        ? `Nội dung yêu cầu phân tích: ${(analysisRequest || "").trim()}`
        : `Analysis request: ${(analysisRequest || "").trim()}`
      : "",
  ].filter(Boolean);
}
