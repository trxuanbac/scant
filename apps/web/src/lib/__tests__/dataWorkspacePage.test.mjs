import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../../app/(dashboard)/data/page.tsx", import.meta.url), "utf8");

test("dataset page exposes search and exact saved-dataset navigation", () => {
  assert.match(source, /aria-label="Tìm tập dữ liệu"/);
  assert.match(source, /filterDatasetGroups/);
  assert.match(source, /dataAnalysisUrl/);
  assert.match(source, /dataset:\s*d\.id/);
  assert.match(source, /analysis:\s*"direct-analysis"/);
});

test("dataset page distinguishes loading, empty, error, and no search results", () => {
  assert.match(source, /Không thể tải thư viện dữ liệu/);
  assert.match(source, /role="alert"/);
  assert.match(source, /Không tìm thấy tập dữ liệu phù hợp/);
  assert.match(source, /Chưa có tập dữ liệu CSV\/Excel nào/);
  assert.match(source, /Thử lại/);
});

test("dataset preview has retry and accessible interactive states", () => {
  assert.match(source, /Tải lại bản xem trước/);
  assert.match(source, /focus-visible:ring-2/);
  assert.match(source, /bg-indigo-600/);
});
