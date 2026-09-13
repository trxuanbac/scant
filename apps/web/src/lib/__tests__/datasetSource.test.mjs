import test from "node:test";
import assert from "node:assert/strict";
import { buildDatasetSourcePromptParts, hasDatasetSource } from "../datasetSource.js";

test("accepts either uploaded file or data source url", () => {
  assert.equal(hasDatasetSource({ mode: "file", files: [{ name: "a.xlsx" }], url: "" }), true);
  assert.equal(hasDatasetSource({ mode: "url", files: [], url: "https://example.com/data.csv" }), true);
  assert.equal(hasDatasetSource({ mode: "url", files: [{ name: "a.xlsx" }], url: "" }), false);
  assert.equal(hasDatasetSource({ mode: "file", files: [], url: "", fileId: "file-123" }), true);
});

test("describes an existing stored dataset without a browser File", () => {
  const parts = buildDatasetSourcePromptParts({
    locale: "vi",
    mode: "file",
    files: [],
    url: "",
    fileId: "file-123",
    fileName: "Doanh_thu.xlsx",
    sheetRange: "",
    analysisRequest: "",
  });

  assert.ok(parts.includes("Nguồn dữ liệu bắt buộc: Doanh_thu.xlsx"));
});

test("builds prompt parts for selected sheet range and analysis request", () => {
  const parts = buildDatasetSourcePromptParts({
    locale: "vi",
    mode: "url",
    files: [],
    url: "https://example.com/data.csv",
    sheetRange: "BangLuong!A1:H200",
    analysisRequest: "Phân tích lương theo phòng ban",
  });

  assert.ok(parts.includes("Nguồn dữ liệu bắt buộc: https://example.com/data.csv"));
  assert.ok(parts.includes("Sheet/range cần đọc: BangLuong!A1:H200"));
  assert.ok(parts.includes("Nội dung yêu cầu phân tích: Phân tích lương theo phòng ban"));
});
