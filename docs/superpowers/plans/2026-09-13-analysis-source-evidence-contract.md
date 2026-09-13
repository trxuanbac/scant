# Analysis Source and Evidence Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every owned workbook analysis request one validated source version, one explicit scope, and evidence that identifies the exact source version it supports.

**Architecture:** Add a small contract module for source identity, scope, and evidence binding, then add one source resolver that owns file lookup, size checks, safe temporary storage, content hashing, and workbook sheet discovery. Existing data routes keep their paths and legacy response fields while gaining an additive `analysis_context`; chat and deterministic analysis evidence is copied and bound to that context before it crosses the API boundary. No database table or visible workspace flow changes in this increment.

**Tech Stack:** FastAPI, Pydantic v2, Python dataclasses, hashlib SHA-256, openpyxl/pandas through the existing workbook scanner, pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-existing-function-completion-program-design.md` — Phase 1A.

## Global Constraints

- Preserve `/data/preview-upload`, `/data/profile/{file_id}`, `/data/analyze-sheet`, `/data/workbook-chat`, and `/data/workbook-analysis-action` request paths and existing response fields.
- A source version is the lowercase SHA-256 of the exact bytes analyzed; stored-file metadata never substitutes for hashing the bytes read.
- Stored file IDs remain owner-scoped and foreign resources return 404.
- Scope modes are exactly `workbook`, `sheets`, `sheet`, and `range`; sheet names must exist and Excel A1 ranges must be valid.
- Legacy clients may omit scope; the server derives a scope from `selected_range`, `sheet_name`, or the workbook sheet set in that order.
- Evidence binding is additive and does not relabel AI narrative as verified deterministic evidence.
- Do not add persistence; durable sessions and findings belong to Phase 1B.

---

### Task 1: Typed source, scope, and evidence contracts

**Files:**

- Create: `apps/api/app/services/data/analysis_contracts.py`
- Create: `apps/api/tests/test_analysis_contracts.py`

**Interfaces:**

- Produces: immutable `SourceVersion(source_id, source_kind, version, display_name, mime_type, size_bytes)` with `as_dict()`.
- Produces: immutable `AnalysisScope(mode, sheets, cell_range)` with `as_dict()`.
- Produces: `normalize_analysis_scope(raw_scope, *, available_sheets, sheet_name=None, selected_range=None) -> AnalysisScope`.
- Produces: `bind_analysis_evidence(payload, *, source_version, scope) -> dict`, returning a copy with additive `analysis_context` and bound dictionary evidence nodes.

- [ ] **Step 1: Write contract tests first**

Cover exact source serialization; workbook, multi-sheet, sheet, and range normalization; legacy scope derivation; rejection of unknown/duplicate sheets, malformed JSON, unsupported keys, invalid A1 ranges, and reversed ranges; and recursive evidence binding without mutating the input. Assert narrative fields stay unchanged and string evidence remains a display string.

- [ ] **Step 2: Run the contract tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_contracts.py`

Expected: collection fails because `app.services.data.analysis_contracts` does not exist.

- [ ] **Step 3: Implement the minimal immutable contracts**

Use `@dataclass(frozen=True, slots=True)`. Parse JSON strings before Pydantic-style validation, allow only the four documented shapes, resolve sheet names with the existing `resolve_sheet_name`, and validate A1 coordinates against Excel's 16,384-column and 1,048,576-row limits. `bind_analysis_evidence` must use `copy.deepcopy`, add `source_version` and `scope` to dictionary values stored under an `evidence` key, and always add the same objects under top-level `analysis_context`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_contracts.py tests/test_workbook_core_safety.py`

Expected: all tests pass.

- [ ] **Step 5: Commit the contract**

```bash
git add apps/api/app/services/data/analysis_contracts.py apps/api/tests/test_analysis_contracts.py
git commit -m "feat: define analysis evidence contract"
```

### Task 2: One owned analysis-source resolver

**Files:**

- Create: `apps/api/app/services/data/analysis_source.py`
- Create: `apps/api/tests/test_analysis_source.py`
- Modify: `apps/api/app/api/v1/data.py`
- Modify: `apps/api/app/api/v1/workbook_actions.py`

**Interfaces:**

- Consumes: `SourceVersion` from Task 1 and existing `owned_dataset`, `safe_dataset_name`, `save_dataset`, and `url_dataset_loader` boundaries.
- Produces: `ResolvedAnalysisSource(path, content, source_version, sheet_names)` and `resolve_analysis_source(db, user, *, file=None, file_id=None, data_source_url=None) -> ResolvedAnalysisSource`.
- Adds `source_version` and a derived workbook scope to preview/profile responses and returns the complete version object from `/data/workbook-actions/source` while retaining `source_hash`.

- [ ] **Step 1: Write resolver and API tests first**

Test stored files, direct uploads, and supported linked content. Assert exact-byte hashing, stable stored `source_id`, opaque transient `source_id`, normalized display name/MIME/size, discovered sheets, 50 MiB enforcement, exactly-one-source validation, missing stored paths, and owner isolation. Extend saved-dataset and workbook-action tests to assert the additive version object.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_source.py tests/test_saved_dataset_analysis_flow.py tests/test_workbook_action_ledger.py`

Expected: failure because the resolver and additive response fields do not exist.

- [ ] **Step 3: Implement and adopt the resolver**

Hash the bytes once, derive transient source IDs from source kind plus version, inspect workbook sheets through the existing scanner/parser boundary, and retain a safe temporary path only for upload/link inputs. Replace repeated source loading in preview, profile, analyze-sheet, workbook-chat, workbook-analysis-action, and workbook-action source-version handling. Map `ValueError`/validation failures to actionable 4xx responses without wrapping an existing `HTTPException` as a generic 400.

- [ ] **Step 4: Run focused API and safety tests**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_source.py tests/test_analysis_contracts.py tests/test_saved_dataset_analysis_flow.py tests/test_data_access_safety.py tests/test_workbook_action_ledger.py tests/test_workbook_core_safety.py`

Expected: all tests pass and foreign file IDs still return 404.

- [ ] **Step 5: Commit the resolver**

```bash
git add apps/api/app/services/data/analysis_source.py apps/api/app/api/v1/data.py apps/api/app/api/v1/workbook_actions.py apps/api/tests/test_analysis_source.py apps/api/tests/test_saved_dataset_analysis_flow.py apps/api/tests/test_workbook_action_ledger.py
git commit -m "feat: resolve versioned analysis sources"
```

### Task 3: Bind scope and evidence at the API boundary

**Files:**

- Modify: `apps/api/app/api/v1/data.py`
- Create: `apps/api/tests/test_analysis_evidence_api.py`
- Modify: `apps/api/TESTING.md`
- Modify: `docs/superpowers/plans/2026-09-13-analysis-source-evidence-contract.md`

**Interfaces:**

- Consumes: `normalize_analysis_scope` and `bind_analysis_evidence` from Task 1 plus `ResolvedAnalysisSource` from Task 2.
- Produces: additive `analysis_context: {source_version, scope}` on preview, profile, analyze-sheet, workbook-chat, and workbook-analysis-action responses.
- Every dictionary evidence node returned by chat or deterministic action carries the same source version and scope as the response; existing `sheet`, `ranges`, `operation`, and `rowCount` fields remain.

- [ ] **Step 1: Write API-boundary tests first**

Use a two-sheet workbook. Assert explicit `workbook`, `sheets`, `sheet`, and `range` scopes round-trip; omitted scope derives from selected range/sheet; unknown sheets and invalid ranges return 422; malformed scope JSON returns 422; response context uses the exact source hash; and nested deterministic evidence uses the identical source/scope objects. Assert a foreign stored source remains 404.

- [ ] **Step 2: Run the boundary tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_evidence_api.py`

Expected: assertions fail because routes do not yet expose normalized analysis context.

- [ ] **Step 3: Bind the contracts without changing the visible workflow**

Normalize scope only after discovering available sheets. Pass the normalized legacy dictionary to `workbook_chat_service`, then bind its response through `bind_analysis_evidence`. Apply the same boundary to preview, profile, analyze-sheet, and analysis-action responses. Re-raise `HTTPException`; map contract errors to status 422 with Vietnamese actionable messages.

- [ ] **Step 4: Run Phase 1A verification**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_analysis_contracts.py tests/test_analysis_source.py tests/test_analysis_evidence_api.py tests/test_saved_dataset_analysis_flow.py tests/test_data_access_safety.py tests/test_workbook_action_ledger.py tests/test_workbook_core_safety.py tests/test_excel_ai_workspace_upgrade.py tests/test_phase_u7_data_analysis.py`

Run: `cd apps/api && venv/bin/python -m pytest -q`

Run: `npm --prefix apps/web test && npm --prefix apps/web run typecheck && npm --prefix apps/web run lint && npm --prefix apps/web run build`

Expected: focused and full backend suites pass with live tests skipped; 95 frontend tests pass; typecheck/build pass; lint has zero errors.

- [ ] **Step 5: Record evidence and commit**

Update `apps/api/TESTING.md` with exact totals and mark this plan's completed checkboxes. Run `git diff --check` and `bash scripts/check-secrets.sh`, then commit:

```bash
git add apps/api/app/api/v1/data.py apps/api/tests/test_analysis_evidence_api.py apps/api/TESTING.md docs/superpowers/plans/2026-09-13-analysis-source-evidence-contract.md
git commit -m "feat: bind analysis scope to evidence"
```

