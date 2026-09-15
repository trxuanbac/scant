# Analysis Quality and Clarification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete deterministic workbook quality detection and return one structured clarification contract whenever a sheet, column, date field, or unit cannot be selected safely.

**Architecture:** Introduce a small clarification contract beside the existing Phase 1A source/scope/evidence contracts and a focused quality service that scans resolved workbook bytes without persisting preview rows. The current sheet analysis and workbook chat services call these focused components; data routes expose a versioned quality response and preserve successful authenticated exchanges in Phase 1B sessions. Phase 1D will render the resulting queue and clarification panel, so this increment changes no navigation or top-level UI.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic v2, pandas, openpyxl, pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-existing-function-completion-program-design.md` — Phase 1C.

## Global Constraints

- Quality results are deterministic and derive only from the exact resolved source version and validated scope.
- Supported issue types are missing values, duplicate rows, IQR outliers, invalid dates, mixed types, formula errors, and existing whitespace findings.
- Every issue includes a stable ID, severity, count, affected sheet/column, bounded cell or range evidence, method, and safe recommendation; raw preview rows and source bytes are never persisted.
- Exact sheet and column names remain valid. Multiple plausible candidates return clarification instead of selecting the first or falling back to the first numeric column.
- Clarification uses one response shape for `sheet`, `column`, `date`, and `unit`, with candidates and the original question. It performs no workbook mutation and creates no analysis finding.
- CSV supports all applicable tabular checks and reports formula checks as unsupported rather than inferred. XLSX/XLSM formula errors are read through openpyxl without recalculating formulas.
- Existing successful response fields remain additive and backwards compatible. Guest requests remain non-persistent; authenticated clarification messages may be retained as messages but never as findings.
- Cross-user isolation, 50 MB limits, path containment, source hashing, and Phase 1B session semantics remain unchanged.

---

### Task 1: Structured clarification contract and ambiguity-aware resolvers

**Files:**

- Create: `apps/api/app/services/data/analysis_clarification.py`
- Modify: `apps/api/app/services/data/sheet_resolvers.py`
- Create: `apps/api/tests/test_analysis_clarification.py`

**Interfaces:**

- Produces `ClarificationKind = Literal["sheet", "column", "date", "unit"]` and `build_clarification(kind, question, candidates, context) -> dict`.
- Clarification responses contain `status="needs_clarification"`, `clarification.kind`, `question`, ordered unique candidates, safe context, empty result/actions, and no numeric evidence claim.
- `ColumnResolver.rank_candidates(...)` returns deterministic scores and reasons; `resolve_column(...)` returns `ambiguous=True` when the top supported candidates are tied or within the defined confidence margin.
- Sheet ambiguity uses the same response contract while retaining the existing `error.code` compatibility field.

- [x] **Step 1: Write failing contract/resolver tests**

Assert schema stability, candidate de-duplication, exact-match precedence, accent-insensitive matching, near-tie ambiguity, low-confidence not-found behavior, and safe JSON output. Include Vietnamese examples such as `Doanh thu`, `Doanh thu thuần`, `Ngày tạo`, and `Ngày thanh toán`.

- [x] **Step 2: Run tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_clarification.py`

Expected: collection fails because the clarification module and ranking interface do not exist.

- [x] **Step 3: Implement contract and resolver ranking**

Preserve exact and no-diacritic exact matches as unambiguous. Rank containment, token overlap, and semantic synonyms deterministically, then require clarification when two supported candidates are within `0.08` and neither is exact. Return no workbook data values in candidate metadata.

- [x] **Step 4: Verify resolver regressions**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_clarification.py tests/test_analysis_contracts.py tests/test_excel_ai_workspace_upgrade.py tests/test_phase_u7_data_analysis.py`

Expected: new tests pass and existing exact column/sheet behavior remains available.

- [x] **Step 5: Commit clarification foundation**

```bash
git add apps/api/app/services/data/analysis_clarification.py apps/api/app/services/data/sheet_resolvers.py apps/api/tests/test_analysis_clarification.py
git commit -m "feat: define analysis clarification contract"
```

### Task 2: Evidence-backed deterministic quality scanner

**Files:**

- Create: `apps/api/app/services/data/data_quality_service.py`
- Modify: `apps/api/app/services/data/sheet_analysis_service.py`
- Create: `apps/api/tests/test_data_quality_service.py`

**Interfaces:**

- Produces `scan_quality(file_path, scope) -> dict` with a summary and ordered issue list.
- Each issue exposes `id`, `type`, `severity`, `title`, `message`, `affected_count`, `sheet`, `column`, `cells`, `ranges`, `method`, `recommendation`, and `supported`.
- Stable issue IDs hash source-local coordinates and issue type rather than depending on discovery order.
- Evidence cell lists are capped at 200 entries while `affected_count` retains the exact full count.

- [x] **Step 1: Write failing scanner tests**

Build XLSX/XLSM and CSV fixtures containing missing values, duplicate rows, numeric outliers, partial invalid date columns, mixed scalar types, literal/formula error cells, whitespace, clean controls, and multi-sheet scopes. Assert exact counts, stable order/IDs, bounded coordinates, no preview rows, and no false formula claim for CSV.

- [x] **Step 2: Run tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_data_quality_service.py`

Expected: collection fails because the focused scanner does not exist.

- [x] **Step 3: Implement one-pass quality scans**

Use pandas for table-level missing/duplicate/type/date/outlier checks and openpyxl `data_only=False` for verifiable cell/formula errors. Reuse detected headers and row offsets from the current query engine, normalize numpy/pandas scalars, and keep recommendations deterministic Vietnamese strings. Make `sheet_analysis_service` consume the shared issue shape while preserving `data_quality_issues`.

- [x] **Step 4: Verify quality and sheet-analysis regressions**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_data_quality_service.py tests/test_phase_u7_data_analysis.py tests/test_excel_ai_workspace_upgrade.py`

Expected: all quality categories pass for supported formats and existing analysis summaries remain compatible.

- [x] **Step 5: Commit quality service**

```bash
git add apps/api/app/services/data/data_quality_service.py apps/api/app/services/data/sheet_analysis_service.py apps/api/tests/test_data_quality_service.py
git commit -m "feat: add evidence-backed data quality scan"
```

### Task 3: Versioned quality API and no-guess chat clarification

**Files:**

- Modify: `apps/api/app/api/v1/data.py`
- Modify: `apps/api/app/services/data/workbook_chat_service.py`
- Modify: `apps/api/app/services/data/analysis_session_service.py`
- Create: `apps/api/tests/test_analysis_quality_api.py`

**Interfaces:**

- Produces `POST /data/quality-scan` for upload, stored file, or supported linked source plus Phase 1A scope.
- Quality responses include `analysis_context`, summary, ordered issues, and evidence bound to the exact source version/scope.
- Workbook chat/action returns structured clarification before calculation when sheet/column/date/unit resolution is ambiguous.
- Clarification responses retain `analysis_session_id` for authenticated users but produce no `AnalysisFinding`.

- [ ] **Step 1: Write failing API/session tests**

Assert equal quality contracts for saved/uploaded/linked inputs, owner isolation, exact source hashing, scope filtering, and no preview payload. Exercise ambiguous sheet, similarly named columns, multiple date fields, and mixed currency/unit columns; assert no deterministic tool call, no pending action, ordered candidates, persisted messages, and zero findings.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_quality_api.py`

Expected: quality endpoint is absent and current ambiguous column/date/unit paths either guess or fall back.

- [ ] **Step 3: Integrate quality and clarification**

Resolve source and scope before scanning. Bind issue evidence through Phase 1A, use the shared clarification builder in both chat and analysis-action paths, and stop dispatch before any calculation or mutation when clarification is needed. Update finding extraction to explicitly ignore `status="needs_clarification"`.

- [ ] **Step 4: Run analysis/session/access regressions**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_quality_api.py tests/test_analysis_session_flow.py tests/test_analysis_sessions.py tests/test_analysis_evidence_api.py tests/test_data_access_safety.py tests/test_workbook_action_ledger.py`

Expected: all tests pass, successful responses remain additive, and clarification creates messages without findings/actions.

- [ ] **Step 5: Commit API integration**

```bash
git add apps/api/app/api/v1/data.py apps/api/app/services/data/workbook_chat_service.py apps/api/app/services/data/analysis_session_service.py apps/api/tests/test_analysis_quality_api.py
git commit -m "feat: expose quality and clarification responses"
```

### Task 4: Format matrix, documentation, and phase verification

**Files:**

- Modify: `apps/api/TESTING.md`
- Modify: `docs/superpowers/plans/2026-09-15-analysis-quality-clarification.md`

**Interfaces:**

- Records the exact quality support matrix and clarification behavior for operators and Phase 1D frontend work.
- Records focused and complete backend/frontend regression totals without hiding skips or warnings.

- [ ] **Step 1: Run focused format and authorization gates**

Run all Phase 1A–1C source, scope, session, quality, clarification, workbook-action, XLSX/XLSM/CSV, and data-access tests.

- [ ] **Step 2: Run complete release regressions**

Run the full backend suite in normal and reversed node-ID order, followed sequentially by frontend test, typecheck, lint, and production build.

- [ ] **Step 3: Document the support boundary**

Document which checks apply to CSV/XLSX/XLSM, the 200-cell evidence cap, the meaning of `supported=false`, and the four clarification kinds. Mark completed plan checkboxes and record exact pass/skip/warning totals.

- [ ] **Step 4: Final safety checks and commit**

Run `git diff --check` and `bash scripts/check-secrets.sh`, then commit documentation only:

```bash
git add apps/api/TESTING.md docs/superpowers/plans/2026-09-15-analysis-quality-clarification.md
git commit -m "docs: record quality clarification verification"
```
