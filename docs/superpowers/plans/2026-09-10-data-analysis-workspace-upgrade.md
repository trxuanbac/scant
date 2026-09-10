# Data Analysis Workspace Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect saved datasets to the existing spreadsheet workspace and DOCX flow, add complete library states, preserve confirmed spreadsheet actions, and close the signed-download authorization gap.

**Architecture:** Keep `/data` as the dataset library and `/projects/new` as the analysis/report workspace. Pass a stable `dataset` query parameter, bootstrap the existing profile by `file_id`, and extend report creation with an owned `dataset_file_id`. Keep shared behavior in small JavaScript helpers and use the existing backend `owned_dataset` authorization function.

**Tech Stack:** Next.js App Router, React, TypeScript, Tailwind CSS, Node test runner, FastAPI, SQLAlchemy async, pytest.

**Spec:** `docs/superpowers/specs/2026-09-10-data-analysis-workspace-upgrade-design.md`

## Global Constraints

- Reuse `ExcelAnalysisWorkspace`; do not create a second analysis engine or workspace.
- Use one primary dataset source: stored dataset, uploaded spreadsheet, or public URL.
- Keep highlight and clear operations in `pending_actions` until explicit confirmation.
- Unknown and foreign dataset identifiers return 404.
- Supported datasets are `.xlsx`, `.xlsm`, `.xls`, and `.csv`, with a 50 MB limit.
- Use white/slate surfaces and indigo primary actions; amber and red are semantic states only.
- Preserve all pre-existing working-tree changes and stage only files deliberately changed by this plan.

---

### Task 1: Dataset Navigation and Filtering Contracts

**Files:**
- Modify: `apps/web/src/lib/dataAnalysisNavigation.js`
- Modify: `apps/web/src/lib/datasetGroups.js`
- Modify: `apps/web/src/lib/datasetSource.js`
- Test: `apps/web/src/lib/__tests__/dataAnalysisNavigation.test.mjs`
- Test: `apps/web/src/lib/__tests__/datasetGroups.test.mjs`
- Test: `apps/web/src/lib/__tests__/datasetSource.test.mjs`

**Interfaces:**
- Produces: `readDatasetId(params): string | null`
- Produces: `dataAnalysisUrl(query, { analysis, dataset }): string`
- Produces: `filterDatasetGroups(groups, query): DatasetGroup[]`
- Extends: `hasDatasetSource({ mode, files, url, fileId }): boolean`
- Extends: `buildDatasetSourcePromptParts({ ..., fileId, fileName }): string[]`

- [ ] **Step 1: Write failing navigation tests**

```js
test("saved dataset navigation preserves workflow context", () => {
  const url = dataAnalysisUrl("mode=auto&type=data_analysis&workflow=data", {
    analysis: "direct-analysis",
    dataset: "file-123",
  });
  const params = new URL(url, "http://localhost").searchParams;
  assert.equal(readAnalysisMode(params), "direct-analysis");
  assert.equal(readDatasetId(params), "file-123");
});

test("invalid dataset identifiers are ignored", () => {
  assert.equal(readDatasetId(new URLSearchParams("dataset=../secret")), null);
});
```

- [ ] **Step 2: Write failing filter and stored-source tests**

```js
test("filters groups by primary or variant file name", () => {
  const groups = groupDatasetsForDisplay([
    { id: "1", original_name: "Doanh_thu.xlsx", metadata_json: {} },
    { id: "2", original_name: "Bang_luong.csv", metadata_json: {} },
  ]);
  assert.deepEqual(filterDatasetGroups(groups, "LƯƠNG").map((group) => group.primary.id), ["2"]);
});

test("accepts an existing dataset id as a file source", () => {
  assert.equal(hasDatasetSource({ mode: "file", files: [], url: "", fileId: "file-123" }), true);
});
```

- [ ] **Step 3: Run tests and confirm the missing exports fail**

Run:

```bash
node --test apps/web/src/lib/__tests__/dataAnalysisNavigation.test.mjs apps/web/src/lib/__tests__/datasetGroups.test.mjs apps/web/src/lib/__tests__/datasetSource.test.mjs
```

Expected: FAIL because `readDatasetId`, `dataAnalysisUrl`, and `filterDatasetGroups` do not exist and `fileId` is not accepted.

- [ ] **Step 4: Implement the pure helpers**

```js
const DATASET_ID = /^[A-Za-z0-9_-]{1,128}$/;

export function readDatasetId(params) {
  const value = (params.get("dataset") || "").trim();
  return DATASET_ID.test(value) ? value : null;
}

export function dataAnalysisUrl(query, { analysis = null, dataset = null } = {}) {
  const params = new URLSearchParams(query);
  if (analysis) params.set("analysis", analysis); else params.delete("analysis");
  if (dataset) params.set("dataset", dataset); else params.delete("dataset");
  return `/projects/new?${params.toString()}`;
}

export function filterDatasetGroups(groups, query) {
  const needle = String(query || "").trim().toLocaleLowerCase("vi");
  if (!needle) return groups;
  return groups.filter((group) => [group.primary, ...group.variants]
    .some((item) => String(item?.original_name || "").toLocaleLowerCase("vi").includes(needle)));
}
```

Update `hasDatasetSource` to return true for a non-empty `fileId` in file mode, and use `fileName || fileId` as the stored-source label in prompt parts.

- [ ] **Step 5: Run the focused helper tests**

Run the Step 3 command.

Expected: all helper tests PASS.

---

### Task 2: Production Dataset Library UI

**Files:**
- Modify: `apps/web/src/app/(dashboard)/data/page.tsx`
- Create: `apps/web/src/lib/__tests__/dataWorkspacePage.test.mjs`

**Interfaces:**
- Consumes: `dataAnalysisUrl`, `filterDatasetGroups`, `groupDatasetsForDisplay`
- Produces: retryable list/preview states and exact saved-dataset analysis links

- [ ] **Step 1: Write the page contract test**

```js
test("dataset page exposes search, retry, and exact analysis navigation", () => {
  const source = readFileSync(new URL("../../app/(dashboard)/data/page.tsx", import.meta.url), "utf8");
  assert.match(source, /aria-label="Tìm tập dữ liệu"/);
  assert.match(source, /Không thể tải thư viện dữ liệu/);
  assert.match(source, /Thử lại/);
  assert.match(source, /dataAnalysisUrl/);
  assert.match(source, /dataset:\s*d\.id/);
});
```

Add assertions for `role="alert"`, no-results copy, preview retry, focus-visible styles, and indigo primary actions.

- [ ] **Step 2: Run the page test and confirm it fails**

Run:

```bash
node --test apps/web/src/lib/__tests__/dataWorkspacePage.test.mjs
```

Expected: FAIL because the current page silently swallows list failures and uses generic analysis links.

- [ ] **Step 3: Implement page state and structure**

Add typed local `DatasetFile`/`DatasetProfile` interfaces, `listError`, `searchQuery`, and a reusable `loadData` callback. Replace the silent catch with a formatted error and retry button. Render stable loading rows, explicit empty/no-results states, and compact grouped rows.

Build analysis links with:

```tsx
href={dataAnalysisUrl("mode=auto&type=data_analysis&workflow=data", {
  analysis: "direct-analysis",
  dataset: dataset.id,
})}
```

Use a labeled search input, responsive action placement, indigo primary controls, semantic quality badges, and `focus-visible` rings.

- [ ] **Step 4: Add preview retry and remove dead data**

Call `openDatasetPreview(previewDataset)` from a retry button while retaining the selected row. Remove the unused `rows` variable and guard zero/undefined file sizes and profile arrays.

- [ ] **Step 5: Run the page and helper tests**

Run:

```bash
node --test apps/web/src/lib/__tests__/dataWorkspacePage.test.mjs apps/web/src/lib/__tests__/dataAnalysisNavigation.test.mjs apps/web/src/lib/__tests__/datasetGroups.test.mjs
```

Expected: PASS.

---

### Task 3: Bootstrap the Existing Dataset in Direct Analysis

**Files:**
- Modify: `apps/web/src/app/projects/new/page.tsx`
- Modify: `apps/web/src/lib/api.ts`
- Create: `apps/web/src/lib/__tests__/storedDatasetBootstrap.test.mjs`

**Interfaces:**
- Consumes: `readDatasetId(searchParams)` and `api.data.profile(fileId)`
- Produces: `storedDatasetId: string | null`, profile bootstrap state, and `fileId` propagation to `ExcelAnalysisWorkspace`

- [ ] **Step 1: Write the failing source contract test**

```js
test("project creator bootstraps and propagates a saved dataset id", () => {
  const source = readFileSync(new URL("../../app/projects/new/page.tsx", import.meta.url), "utf8");
  assert.match(source, /readDatasetId/);
  assert.match(source, /api\.data\.profile\(storedDatasetId\)/);
  assert.match(source, /fileId=\{storedDatasetId/);
  assert.match(source, /formData\.append\("file_id", storedDatasetId\)/);
  assert.match(source, /formData\.append\("dataset_file_id", storedDatasetId\)/);
});
```

Add an assertion that a visible bootstrap failure offers a link back to `/data`.

- [ ] **Step 2: Run the bootstrap test and confirm it fails**

Run:

```bash
node --test apps/web/src/lib/__tests__/storedDatasetBootstrap.test.mjs
```

Expected: FAIL because the page does not read or propagate `dataset`.

- [ ] **Step 3: Add stored dataset bootstrap state**

Read the query parameter once through `readDatasetId`. Add `storedDatasetId`, `storedDatasetLoading`, and `storedDatasetError`. In an effect, call `api.data.profile(storedDatasetId)`, ignore stale completion after cleanup, initialize `dataPreview`, select the first sheet, mark the preview confirmed, and open the interactive workspace.

Use `formatUnknownError` for failures and render a recovery panel with **Try again** and **Back to data library**.

- [ ] **Step 4: Propagate the stored source**

When no browser `File` exists and `storedDatasetId` is set:

```ts
formData.append("file_id", storedDatasetId);
```

Pass `fileId={storedDatasetId || undefined}` to every mounted `ExcelAnalysisWorkspace`. Extend `hasActiveDatasetSource` and prompt construction with stored file identity. Preserve the query parameter when changing direct/report analysis mode.

- [ ] **Step 5: Propagate the stored source into report creation**

Before calling `api.reports.autoCreate`, add:

```ts
if (isDataWorkflow && storedDatasetId) {
  formData.append("dataset_file_id", storedDatasetId);
}
```

Do not append the same spreadsheet again through `files`.

- [ ] **Step 6: Run bootstrap, navigation, and source tests**

Run:

```bash
node --test apps/web/src/lib/__tests__/storedDatasetBootstrap.test.mjs apps/web/src/lib/__tests__/dataAnalysisNavigation.test.mjs apps/web/src/lib/__tests__/datasetSource.test.mjs
```

Expected: PASS.

---

### Task 4: Authorize Signed Links and Stored-Dataset Reports

**Files:**
- Modify: `apps/api/app/api/v1/files.py`
- Modify: `apps/api/app/api/v1/reports.py`
- Create: `apps/api/tests/test_saved_dataset_analysis_flow.py`

**Interfaces:**
- Consumes: `owned_dataset(db, file_id, current_user)`
- Extends: `POST /reports/auto-create` with optional `dataset_file_id: str`
- Tightens: `POST /files/{file_id}/signed-url` ownership behavior

- [ ] **Step 1: Write failing authorization tests**

Create two users and projects, upload a dataset for user A, then assert user B receives 404 from:

```python
foreign_signed = await client.post(f"/api/v1/files/{file_id}/signed-url", headers=user_b_headers)
assert foreign_signed.status_code == 404

foreign_report = await client.post(
    "/api/v1/reports/auto-create",
    headers=user_b_headers,
    data={"prompt": "Phân tích", "dataset_file_id": file_id},
)
assert foreign_report.status_code == 404
```

Patch the intent/orchestrator boundary for the owned-report success test only; assert the owned dataset profile is attached to the new project.

- [ ] **Step 2: Run the new backend tests and confirm failure**

Run:

```bash
cd apps/api && ../../venv/bin/python -m pytest tests/test_saved_dataset_analysis_flow.py -q
```

Expected: signed-link foreign access is not 404 and report form does not accept `dataset_file_id`.

- [ ] **Step 3: Fix signed-link ownership**

Replace the unrestricted repository lookup with:

```python
f = await owned_dataset(db, file_id, current_user)
```

Import the shared helper and keep the 404 behavior for unknown/foreign identifiers.

- [ ] **Step 4: Validate a stored dataset before project creation**

Add `dataset_file_id: Optional[str] = Form(None)` to `one_click_auto_create`. Before intent analysis or project creation:

```python
stored_dataset = None
if dataset_file_id:
    stored_dataset = await owned_dataset(db, dataset_file_id, current_user)
    stored_path = Path(stored_dataset.file_path).resolve()
    upload_root = settings.UPLOAD_DIR.resolve()
    if upload_root not in stored_path.parents or not stored_path.is_file():
        raise HTTPException(404, "Không tìm thấy tệp dữ liệu.")
    if stored_path.suffix.lower() not in {".xlsx", ".xlsm", ".xls", ".csv"}:
        raise HTTPException(422, "Tệp đã chọn không phải dữ liệu bảng tính được hỗ trợ.")
    if stored_path.stat().st_size > 50 * 1024 * 1024:
        raise HTTPException(413, "Tệp vượt quá giới hạn dung lượng 50MB.")
```

Reject requests that combine `dataset_file_id` with `data_source_url` or an uploaded spreadsheet.

- [ ] **Step 5: Feed owned bytes through the existing report path**

After `store_dataset_from_bytes` is defined, call it with `stored_path.read_bytes()`, `stored_dataset.original_name`, and `stored_dataset.mime_type`. Template uploads remain allowed and do not count as a second dataset source.

- [ ] **Step 6: Run focused backend tests**

Run:

```bash
cd apps/api && ../../venv/bin/python -m pytest tests/test_saved_dataset_analysis_flow.py tests/test_data_access_safety.py tests/test_workbook_action_ledger.py -q
```

Expected: PASS.

---

### Task 5: Align Spreadsheet Action Contract Tests

**Files:**
- Modify: `apps/api/tests/test_audit_upgrade_analysis_flow.py`
- Modify: `apps/web/src/lib/__tests__/auditUpgradeAnalysisFlow.test.mjs`

**Interfaces:**
- Consumes: backend `pending_actions` response contract
- Guarantees: highlight/clear proposals are never treated as immediate writes

- [ ] **Step 1: Change the failing assertions to the safe contract**

For max/search tests use:

```python
assert res["pending_actions"]
assert not any(action["type"] in {"HIGHLIGHT_CELLS", "HIGHLIGHT_ROWS", "CLEAR_HIGHLIGHTS"} for action in res["actions"])
assert all(action.get("requires_confirmation") is True for action in res["pending_actions"])
```

Update the frontend contract test to require rendering `pending_actions` through `SpreadsheetActionCard` and no automatic highlight loop.

- [ ] **Step 2: Run the focused contract tests**

Run:

```bash
cd apps/api && ../../venv/bin/python -m pytest tests/test_audit_upgrade_analysis_flow.py -q
cd ../web && node --test src/lib/__tests__/auditUpgradeAnalysisFlow.test.mjs src/lib/__tests__/localActionConfirmation.test.mjs
```

Expected: PASS while production code retains explicit confirmation.

---

### Task 6: Full Verification and Runtime Check

**Files:**
- Modify only files required to fix failures introduced by Tasks 1-5

**Interfaces:**
- Verifies the complete spec acceptance criteria

- [ ] **Step 1: Run all frontend source tests**

```bash
cd apps/web && npm test
```

- [ ] **Step 2: Run frontend static checks**

```bash
cd apps/web && npm run typecheck
cd apps/web && npm run lint
cd apps/web && npm run build
```

- [ ] **Step 3: Run the focused backend data suite**

```bash
cd apps/api && ../../venv/bin/python -m pytest \
  tests/test_saved_dataset_analysis_flow.py \
  tests/test_audit_upgrade_analysis_flow.py \
  tests/test_phase_u7_data_analysis.py \
  tests/test_data_access_safety.py \
  tests/test_workbook_core_safety.py \
  tests/test_workbook_action_ledger.py \
  tests/test_google_sheets_live_sync.py -q
```

- [ ] **Step 4: Inspect the final diff**

```bash
git diff --check
git status --short
git diff -- apps/web/src/app/\(dashboard\)/data/page.tsx apps/web/src/app/projects/new/page.tsx apps/api/app/api/v1/files.py apps/api/app/api/v1/reports.py
```

Confirm no unrelated working-tree file was overwritten or staged.

- [ ] **Step 5: Verify the running application**

Confirm the existing frontend and API processes are listening. Request `/data`, the API health route, and an authenticated dataset list. Inspect runtime logs for render or API errors after loading the upgraded route.

- [ ] **Step 6: Apply the acceptance checklist**

Verify each acceptance criterion in the spec against test output and the runtime flow. Report external-provider failures separately from local regressions.
