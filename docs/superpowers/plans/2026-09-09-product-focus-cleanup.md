# SCANT Product Focus Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce SCANT to a polished report, data, research, editing, and export product while preserving existing user data and links.

**Architecture:** Consolidate duplicated frontend destinations through reusable workspace components and compatibility redirects. Remove misleading or unwired runtime capabilities at the UI, API, and service boundaries while leaving historical database tables untouched.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, FastAPI, SQLAlchemy, Node test runner, pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-product-focus-cleanup-design.md`

## Global Constraints

- Preserve all database tables, migrations, uploaded files, projects, reports, sources, comments, members, automation records, and billing records.
- Preserve existing project type values and direct project/report-editor/download links.
- Use one indigo accent with neutral, compact workspace surfaces and visible keyboard focus.
- Removed providers and endpoints must fail honestly; no fabricated success fallback.
- Do not overwrite the user's unrelated workbook, spreadsheet, or research-scraper changes already present in the working tree.

---

### Task 1: Focused navigation contract

**Files:**
- Create: `apps/web/src/lib/productFocus.ts`
- Create: `apps/web/src/lib/__tests__/productFocus.test.mjs`
- Modify: `apps/web/src/components/Sidebar.tsx`
- Modify: `apps/web/src/components/CommandPalette.tsx`

**Interfaces:**
- Produces: `getWorkspaceNavigation(isAdmin: boolean)` returning route descriptors for Home, Create new, Projects, Data, Research, Templates, Settings, plus Admin only for admins.
- Consumes: existing translation keys and icon mapping in each component.

- [ ] Write a Node test importing `getWorkspaceNavigation` and assert literal href arrays for ordinary and admin users. The test must fail because the helper does not exist.
- [ ] Run `npm --prefix apps/web test -- --test-name-pattern="focused workspace navigation"` and confirm the expected module-not-found failure.
- [ ] Implement the typed route helper and update Sidebar and CommandPalette to consume it. Remove Documents, Automations, Sources, and Brand Kit top-level commands. Ensure CommandPalette Admin visibility uses the same role decision as Sidebar.
- [ ] Run the focused test and the full frontend Node suite.

### Task 2: Unified Projects and reports library

**Files:**
- Create: `apps/web/src/components/ReportLibraryView.tsx`
- Modify: `apps/web/src/app/(dashboard)/projects/page.tsx`
- Replace: `apps/web/src/app/(dashboard)/documents/page.tsx`
- Test: `apps/web/src/lib/__tests__/productFocus.test.mjs`

**Interfaces:**
- Consumes: `api.reports.list`, `api.reports.get`, `api.exports.previewReportHtml`, and report editor route `/reports/:id/editor`.
- Produces: `/projects?view=reports` and compatibility redirect `/documents -> /projects?view=reports`.

- [ ] Add a Playwright-free route smoke assertion through the running Next server after implementation; use the production build as the pre-implementation failure boundary because `/documents` currently renders a standalone page instead of redirecting.
- [ ] Extract the existing report list/preview behavior into `ReportLibraryView`, with loading, empty, error, preview, mobile cards, and editor links.
- [ ] Add accessible Projects/Reports segmented tabs to `/projects`; synchronize the active view with the `view` query parameter.
- [ ] Replace `/documents` with a server redirect to `/projects?view=reports`.
- [ ] Verify the redirect with `curl -I`, then run frontend tests, typecheck, and build.

### Task 3: Unified Research workspace

**Files:**
- Move: `apps/web/src/app/(dashboard)/sources/page.tsx` to `apps/web/src/components/SourceLibraryWorkspace.tsx`
- Modify: `apps/web/src/app/(dashboard)/research/page.tsx`
- Create: `apps/web/src/app/(dashboard)/sources/page.tsx`
- Test: `apps/web/src/lib/__tests__/productFocus.test.mjs`

**Interfaces:**
- Consumes: existing `api.research` discovery/citation calls and `api.sources` persisted-library calls.
- Produces: `/research` Discover view, `/research?view=library` Library view, and `/sources` compatibility redirect.

- [ ] Add a route smoke expectation that `/sources` redirects to `/research?view=library`; confirm it fails against the current running application.
- [ ] Move the source-library client component without changing its data operations.
- [ ] Add a compact Discover/Library switcher to Research and render `SourceLibraryWorkspace` for the library query view.
- [ ] Add the `/sources` server redirect and verify direct search, saved-source loading, source management, and citation export remain reachable.
- [ ] Run frontend tests, typecheck, build, and HTTP redirect checks.

### Task 4: Brand settings and focused project types

**Files:**
- Move: `apps/web/src/app/(dashboard)/brand-kit/page.tsx` to `apps/web/src/components/BrandSettingsPanel.tsx`
- Modify: `apps/web/src/app/(dashboard)/settings/page.tsx`
- Create: `apps/web/src/app/(dashboard)/brand-kit/page.tsx`
- Modify: `apps/web/src/app/projects/new/page.tsx`
- Test: `apps/web/src/lib/__tests__/productFocus.test.mjs`

**Interfaces:**
- Produces: Settings `brand` tab, `/brand-kit -> /settings?tab=brand`, and four visible new-project choices using values `business_report`, `data_analysis`, `research`, and `custom`.
- Preserves: rendering and opening existing projects with legacy type values.

- [ ] Add pure tests for `getVisibleProjectTypes()` with the four hand-derived values and route smoke coverage for the brand redirect; verify RED.
- [ ] Embed the existing brand form into Settings, initialize the active tab from `?tab=`, and replace the old route with a redirect.
- [ ] Replace the eight new-project cards with four choices. Present proposal, financial, technical, and market research as template/preset guidance rather than persisted top-level choices.
- [ ] Run focused and full frontend checks.

### Task 5: Remove misleading AI capabilities

**Files:**
- Modify: `apps/web/src/features/editor/TiptapEditor.tsx`
- Modify: `apps/web/src/features/editor/AiAssistantPanel.tsx`
- Modify: `apps/web/src/app/projects/new/page.tsx`
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/api/app/api/v1/ai.py`
- Delete: `apps/web/src/components/StylometryCheckerModal.tsx`
- Delete: `apps/web/src/components/VoiceRecorderModal.tsx`
- Delete: `apps/api/app/services/quality/plagiarism_stylometry_engine.py`
- Delete: `apps/api/app/services/ai/voice_service.py`
- Test: `apps/api/tests/test_final_product_completion.py`

**Interfaces:**
- Removes: `/ai/inspect-stylometry`, `/ai/voice-to-report`, `api.ai.inspectStylometry`, and `api.ai.voiceToReport`.
- Preserves: AI rewrite/humanize and browser-only spreadsheet dictation.

- [ ] Add an API test that inspects the FastAPI route table and asserts the two retired paths are absent. Confirm it fails because both routes are mounted.
- [ ] Remove the frontend entry points, imports, state, API methods, request models used only by the retired endpoints, backend handlers, and services.
- [ ] Update billing copy so plans no longer promise stylometry or uploaded-audio report generation.
- [ ] Run focused API tests, frontend tests, typecheck, and build.

### Task 6: Retire unfinished runtime subsystems and orphan engines

**Files:**
- Modify: `apps/api/app/api/v1/__init__.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/api/v1/admin_operations.py`
- Modify: `apps/api/app/services/admin/operations_service.py`
- Modify: `apps/web/src/components/admin/AdminShell.tsx`
- Modify: `apps/web/src/components/admin/AdminScreen.tsx`
- Delete: `apps/web/src/app/(dashboard)/automations/page.tsx`
- Delete: `apps/api/app/api/v1/automations.py`
- Delete: `apps/api/app/api/v1/collaboration.py`
- Delete: `apps/api/app/services/automation/automation_engine.py`
- Delete: `apps/api/app/services/automation/automation_scheduler.py`
- Delete: `apps/api/app/services/collaboration/collaboration_service.py`
- Delete: `apps/api/app/services/presentation/presentation_engine.py`
- Delete: `apps/api/app/services/codebase/codebase_intelligence_engine.py`
- Delete: `apps/api/app/services/designer/document_designer_engine.py`
- Delete: `apps/api/app/services/documents/ocr/ocr_layout_engine.py`
- Delete: `apps/api/app/services/research/deep_research_v2.py`
- Delete isolated phase tests for the removed modules; remove only their cases from mixed launch-readiness tests.

**Interfaces:**
- Removes mounted `/automations` and `/collaboration` routes plus API startup scheduler side effects.
- Preserves automation/collaboration ORM models and database tables for historical data.

- [ ] Extend the FastAPI route-table test to assert `/automations` and `/collaboration` paths are absent while core `/projects`, `/reports`, `/research`, `/sources`, `/data`, and `/exports` routes remain. Confirm RED.
- [ ] Unmount retired routers and remove startup scheduler lifecycle calls.
- [ ] Remove admin controls and health claims that depend on the retired scheduler.
- [ ] Delete runtime-only files and isolated tests after `rg` proves no non-test consumer remains.
- [ ] Import `app.main`, generate OpenAPI, and run focused backend tests.

### Task 7: Documentation and final verification

**Files:**
- Modify: `README.md`
- Modify: `docs/SCANT_PRODUCTION_UPGRADE_PLAN.md` only where its current-state inventory becomes inaccurate.

**Interfaces:**
- Documents the seven-destination information architecture and explicitly retired capabilities.

- [ ] Update product description, navigation, and local-development notes without editing unrelated upgrade history.
- [ ] Run `git diff --check`.
- [ ] Run `npm --prefix apps/web test`.
- [ ] Run `npm --prefix apps/web run typecheck`.
- [ ] Run `npm --prefix apps/web run lint` and report warnings separately from errors.
- [ ] Run `npm --prefix apps/web run build`.
- [ ] Run focused backend tests covering app startup, route table, auth/projects/reports/research/sources/data/exports, and existing workbook safety changes.
- [ ] Start the app and smoke-test Home, Projects, Reports view, Research, Source Library, Templates, Settings/Brand, API health, and OpenAPI.
- [ ] Review the final diff to confirm no database model, migration, user file, or unrelated dirty change was removed.

