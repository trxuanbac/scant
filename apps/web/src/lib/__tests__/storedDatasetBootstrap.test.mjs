import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../../app/projects/new/page.tsx", import.meta.url), "utf8");

test("project creator bootstraps and propagates a saved dataset id", () => {
  assert.match(source, /readDatasetId/);
  assert.match(source, /api\.data\.profile\(storedDatasetId\)/);
  assert.match(source, /fileId=\{storedDatasetId/);
  assert.match(source, /formData\.append\("file_id", storedDatasetId\)/);
  assert.match(source, /formData\.append\("dataset_file_id", storedDatasetId\)/);
});

test("stored dataset bootstrap exposes loading and recovery states", () => {
  assert.match(source, /Đang mở tập dữ liệu đã lưu/);
  assert.match(source, /Không thể mở tập dữ liệu đã lưu/);
  assert.match(source, /Thử tải lại/);
  assert.match(source, /href="\/data"/);
});

test("choosing a new source clears the stored dataset selection", () => {
  assert.match(source, /setStoredDatasetId\(null\)/);
  assert.match(source, /fileId:\s*storedDatasetId/);
  assert.match(source, /fileName:\s*storedDatasetName/);
});
