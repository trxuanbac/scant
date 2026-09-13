# SCANT production upgrade plan

Audit date: 2026-09-06. Source of requirements: the supplied “MASTER PROMPT: NÂNG CẤP TOÀN DIỆN SCANT” (sections 0–82). This is an implementation roadmap and evidence record, not a production-readiness certificate. Existing admin and Google OAuth separation work at baseline `fd8e05d` must be preserved. Implementation is proceeding alongside this audit; Phase 1 changes need their own verification before being described as complete.

## Architecture and reuse map

Paths below are relative to the repository. API paths have the `/api/v1` prefix. Model tables are defined in `apps/api/app/models/entities.py` unless indicated otherwise.

| Module | Existing implementation, API and data | Reuse decision and remaining work |
|---|---|---|
| Frontend | `apps/web/src/app`, `components`, `features/editor`; Next App Router, React, TypeScript, Tailwind, Zustand, TanStack Query, Tiptap. `src/lib/api.ts` and `adminApi.ts` connect runtime APIs. | Preserve app shell, analysis workspace and editor. README says Next 15; package.json actually specifies Next 16, React 19, Tailwind 4 and TypeScript 7. Update docs against installed stack. Current tests are Node helper/source tests, not browser interaction coverage. |
| Backend/API | FastAPI modular monolith in `apps/api/app/main.py`, `api/v1`, `repositories`, `schemas`; async SQLAlchemy and Pydantic. | Extend existing routes and service interfaces. Large `data.py`, `reports.py`, workbook services and workspace components need incremental extraction at behavior boundaries, not a rewrite. Error envelopes and resource authorization remain inconsistent. |
| Authentication | `api/v1/auth.py`, `google_connection.py`, `api/deps.py`, `core/security.py`, `core/admin_access.py`, `services/auth/google_auth_service.py`; frontend `app/api/auth` and `GoogleDataConnection.tsx`. Tables: `users`, `auth_accounts`. | Preserve password/JWT login and separate Google identity/data consent. Test invalid/expired state, inactive accounts, token refresh and read/write scopes. OAuth credentials and access/refresh tokens need a documented encryption/rotation policy. |
| AI gateway | `services/ai/{base,gateway,types,provider_factory,model_router,gemini_provider,openai_provider}.py`; `api/v1/ai.py`. Tables: `ai_generations`, `ai_usage_events`, `user_quotas`, `admin_configuration`. | Reuse provider abstraction, bounded timeout/retry/fallback and usage persistence. `services/templates/template_reverse_engineering_service.py` still calls factory directly. Gateway lacks streaming orchestration, typed error classification and circuit breaker. Token estimates must be distinguished from provider measurements. |
| Context / intent / analysis | `services/data/{workbook_chat_service,analysis_intent_parser,sheet_analysis_service,spreadsheet_query_engine,workbook_scanner,sheet_resolvers}.py`, `services/agent/report_context_builder.py`, knowledge retrieval. APIs: `/data/workbook-chat`, `/data/analyze-sheet`, `/data/aggregate`, `/ai/analyze-intent`. Tables: `datasets`, `dataset_columns`, `uploaded_files`, `documents`. | Reuse structured workbook scope and deterministic computation. Consolidate intent/context contracts incrementally; cover greetings, dataset QA, actions, research and report requests without routing everything through one prompt. Clarify ambiguous sheets and preserve provenance. |
| Spreadsheet | `services/documents/excel_parser.py`, data `action_engine.py`, `adapters.py`, `google_sheets_service.py`; frontend `ExcelAnalysisWorkspace.tsx`, `ExcelAIChatPanel.tsx`, `SpreadsheetPreview.tsx`. APIs: preview-upload, workbook-analysis-action, apply-modifications, action-undo, google-sync-retry. | Keep current editor/preview; no evidence justifies replacement with Univer. Pending action UI exists but baseline action cards primarily trigger local highlighting. Baseline action routing has a failing pending-confirmation regression. Undo stacks are process-local; some action methods silently choose first sheet when name is missing. Add durable validated actions, real diff, confirmation, read-back verification and bounded undo. |
| Research | `services/research/{deep_research_pipeline,query_analyzer,research_search_service,search_engine,web_search,scraper,source_verifier,source_ranker,evidence_extractor,synthesis_agent}.py`, academic providers; `api/v1/research.py`; the unified research/source-library page and editor ResearchPanel. Tables: `research_jobs`, `research_results`, `sources`, `evidences`, `claims`, `citations`, `claim_sources`. | Reuse evidence/citation services and actual providers. The standalone Deep Research V2 experiment was retired. Multiple remaining search/pipeline layers require call-graph consolidation before removal. False scraper evidence and unsafe redirects must remain covered by regression tests. |
| Report Studio | `services/editor`, `services/agent/agentic_report_orchestrator.py`, `services/quality`, `api/v1/reports.py`; `features/editor/TiptapEditor.tsx`, outline, research, AI and export panels. Tables: `reports`, `report_sections`, `report_versions`, changesets. | Preserve section storage, quality gates and rich editor. Verify autosave conflict handling, explicit AI edits, regeneration/version semantics and citation round trips. Long report dispatch currently uses `asyncio.create_task`; persistence alone does not make execution durable. |
| Export | `services/exports/{docx_exporter,pdf_exporter}.py`, `api/v1/exports.py`, `features/editor/ExportModal.tsx`; `exports` table. | Reuse DOCX layout engine/tests. Verify PDF runtime prerequisites and formatted editor-to-export fidelity with headings, tables, images, captions, TOC and references. Add durable, authorized, idempotent large exports before advanced formats. |
| Jobs | `services/worker/{queue_manager,checkpoint_engine}.py`, report job endpoints and frontend `lib/autoJobState.js`; `jobs`, historical `automation_runs`, and `research_jobs`. | The standalone automation runtime and scheduler were retired while their historical tables were preserved. `ProductionTaskQueue` still uses an asyncio.Queue plus dictionaries, including idempotency state. Reuse state/handler contracts with Redis-backed dispatch and SQL job lifecycle. Separate worker process, retry lease/heartbeat and restart recovery are missing. |
| Storage | `services/storage/{storage_provider,signed_url_service,deduplication_service}.py`, upload validator, `api/v1/files.py`, data download endpoint; `uploaded_files`, `exports`, `image_assets`. | Local storage and signed tokens exist. S3 adapter is an in-memory dictionary, not S3; factory always returns local. Direct filesystem paths remain in business logic. Implement actual configured S3/MinIO and root containment, ownership, MIME/size checks, metadata and retention. |
| Billing | `services/billing/{billing_provider,entitlement_service,plan_definitions}.py`, `services/admin/plan_service.py`, `services/usage/quota_engine.py`, `api/v1/{billing,admin_billing,usage}.py`, `VietQRPaymentModal.tsx`. `billing_payments` and `billing_subscriptions` in `models/admin_billing.py`. | Preserve real PayOS server adapter, configured prices, server payment verification and ledger. Add verified idempotent webhook lifecycle and consistent subscription-based entitlement/quota enforcement. Do not restore old mock checkout assumptions to make legacy tests pass. |
| Admin | `app/admin`, `components/admin`, `lib/adminApi.ts`; `api/v1/{admin,admin_operations,admin_billing}.py`, `services/admin`; `audit_logs`, usage, job, billing and `admin_configuration` tables. | Existing dedicated console, role enforcement, server-backed operations, provider settings and audit are substantial reuse. Add missing circuit-state/job/storage accuracy once underlying systems are real; do not hardcode health or charts. Preserve protected last-admin rules and security tests. |
| Database / tenancy | `core/database.py`, `models`, `migrations/admin_console.py`. `workspaces` belong to users; projects optionally reference workspace; `project_members` exists. | There is no general Alembic migration chain. Startup calls create_all and SQLite PRAGMA/ALTER with swallowed exceptions. Existing admin migration is not a substitute for full schema management. Add a compatible baseline, PostgreSQL integration and actual organization/workspace membership model later. |
| Observability | `services/observability/{structured_logger,metrics_collector}.py`, middleware in main, `/metrics`, `/health`, `/health/live`, `/health/ready`; persistent AI usage and admin audit. | Request counters exist; full request-ID/error envelope and durable job metrics do not. Readiness uses `storage_provider.exists("") or True`, labels storage writable without write verification, always says AI online and does not probe Redis. Make health evidence-based. |
| Infrastructure | `.env.example`, `docker-compose.yml`, `scripts/dev.sh`, smoke scripts and secret scanner. Compose declares PostgreSQL, Redis, API and web. | Referenced `apps/api/Dockerfile` and `apps/web/Dockerfile` are absent in audited inventory; `.github` is absent. No worker or MinIO service. Compose is not demonstrated deployable. Add images, health dependencies, runtime env and deterministic CI. Keep local/test SQLite. |

## Baseline verification and limits

Parent-run baseline before Phase 1 edits:

- Backend: **216 passed, 36 failed, 1 skipped**. Failure evidence: `/private/tmp/scant-upgrade-baseline-api.log` (local ephemeral artifact, not a repository dependency).
- Frontend: **74 passed**.
- Typecheck/build: being checked by the implementation owner; do not infer current success from earlier passing runs. Lint and Docker/migration checks must be reported independently.

Failure classification is provisional until each case is isolated. Many AI/research tests call live Gemini/OpenAI, Crossref/arXiv or search endpoints and fail because of unavailable network/configuration. This is also a test isolation defect. The pending-action test `test_excel_ai_workspace_upgrade.py::test_workbook_chat_action_request_returns_pending_confirmation` is an observed product regression and must be fixed, not labeled an environment issue. The older VietQR billing-generation test expects behavior incompatible with the newly verified server payment flow and needs a contract review. Source-library assertions and all remaining failures require individual diagnosis; no claim is made that all 35 other failures are environmental.

Existing focused coverage includes auth/projects, Google connection/live-sync contracts, admin permissions/billing/configuration, workbook scope/analysis, citations/grounding, DOCX layout, queue snapshots, storage tokens and production configuration. Tests named “production”, “live”, “e2e” or “final completion” do not establish production readiness: several only test in-memory implementations or depend on live services. No browser E2E runner or CI workflow was found.

## Immediate findings and cleanup policy

1. Treat broken ownership/path validation and unconfirmed workbook writes as release blockers even though broad security appears later in the requested priority list. Scope authorization to the stored resource owner before accepting local path, project, session or Google target. Verify download, apply, undo and retry separately.
2. Research failure must produce unavailable evidence, never a fabricated citation. Validate original and redirect destinations against SSRF protections, enforce response size/time limits and reject private/link-local/metadata destinations. The existing validator alone does not prove every fetch is safe.
3. Replace names that imply production durability with actual durable behavior before deployment: queue, S3, readiness and undo are currently incomplete. Do not add a second queue/storage/gateway architecture alongside them.
4. `core/database.py` has silent migration failures; workbook scanner/action paths and research fallbacks also contain broad exception swallowing. Preserve legitimate parsing fallbacks only when their result explicitly records degraded confidence/error and cannot report a false write success.
5. Potential overlap: data schema/scanning between `data_engine`, `sheet_analysis_service`, `workbook_scanner` and `spreadsheet_query_engine`; research v1/v2/search wrappers; template factory calls bypassing gateway; JS/TS companion helpers `excelAnalysisSession` and `excelSheetSignals`. These are candidates for call-graph review, not proven dead code. Do not delete based on filename similarity. No whole-repository dead-code certification was performed.
6. Existing source comments such as “Production”, “fallback” and “Phase U…” are not acceptance evidence. Prioritize observed runtime behavior over TODO count. Avoid expanding low-priority diagram/presentation/collaboration work while core and reliability gates fail.

## Phased implementation and acceptance gates

The sequence below follows specification section 79. Security and honesty gates apply to every phase, including core work. P0/P1/etc in section 2 are priority labels; they are not evidence that similarly numbered historical U-phase tests completed these requirements.

### Phase 0 — Audit

Deliver this architecture map, baseline classification and a reviewable implementation sequence. Keep baseline failures visible. Audit completion does not imply feature completion; focused source review must continue as each module changes.

### Phase 1 — Excel + AI core (current implementation slice)

Reuse workbook chat, parsers, analysis workspace and action adapters. First fix pending-action intent routing, ambiguous Vietnamese sheet resolution, endpoint ownership/path checks and explicit frontend preview/confirm/cancel. Then introduce a shared validated action contract covering allowed action types, cells/ranges, value/formula/style payloads and affected counts. Reject unsupported mutations rather than pretend to apply them.

Persist pending/executed/cancelled/failed actions with actor, workbook identity/version, preview diff and confirmation state; evaluate reuse of `AIChangeSet`/`AIChange` plus `AuditLog` before introducing tables. Use idempotency and optimistic version checks to prevent double confirmation/stale previews. Scope undo to the authorized actor/resource, persist efficient diffs, preserve original styles/formulas, and state supported undo limits. Google mutations require separate explicit remote target, valid OAuth scope, batch response verification and read-back; local preview must not claim remote success.

Acceptance: scenarios A–D; Vietnamese greeting remains chat; payroll sum excludes IDs/STT/totals and does not modify source; highlight and duplicate-delete requests create pending actions; ambiguous accent-normalized names ask for clarification; preview does not write; cancel does not write; confirm writes exactly once; unauthorized resource/session/path and stale confirmation are rejected; read-back matches expected cells; undo/audit survives the supported lifecycle. Include real XLSX fixtures for merged/hidden/formula/date/currency/duplicate headers and source checksum assertions. Browser coverage must confirm the actual buttons and workbook refresh. A Phase 1 safety patch alone does not satisfy all of this gate.

### Phase 2 — AI gateway and streaming

Route remaining factory users through existing gateway. Add typed provider failures (429, timeout, 5xx, auth, invalid request, context length), bounded retry and circuit states with configured fallback only. Reuse provider `stream` interface through real SSE endpoints and an incremental frontend reader with abort, terminal events and clear retry behavior. Define structured intent/action/report outputs with schema validation and bounded repair. Record usage once per paid execution, including streaming failures, distinguishing measured/estimated tokens.

Acceptance: scenario G with mocked providers; no retries for permanent errors, breaker opens/recovers deterministically, cancellation propagates, no duplicate paid execution from telemetry failure, first delta precedes completion, errors terminate stream. Chat/report/research clients consume the real stream. Provider status and circuit state reflect actual data.

### Phase 3 — Reliability, migrations and workers

Introduce Alembic baseline compatible with existing databases and the admin migration. Back up and test upgrade/downgrade, fresh PostgreSQL and populated SQLite/PostgreSQL; retain explicit test/bootstrap support. Remove production auto-patching only after migration paths work. Review actual foreign-key/index/pagination queries.

Adopt Redis-backed async workers (ARQ is a candidate consistent with the async backend; finalize after dependency/runtime validation). Keep existing job API/state model, add persistent attempt/lease/idempotency data, separate worker startup, bounded retry and cancellation checkpoints. Migrate report/research/parse/export dispatch away from `asyncio.create_task`. Replace readiness assertions with DB/Redis/storage probes and appropriate unavailable status.

Acceptance: kill/restart API and worker mid-job, job recovers without duplicate externally visible effects; retry/cancel/progress survive restart; jobs and resources are owner-scoped; migrations are repeatable and preserve records; readiness fails when required dependencies fail. Docker includes worker and health checks.

### Phase 4 — Deterministic tests and CI

Separate unit, integration, browser E2E and explicitly opt-in live-provider tests. Mock HTTP/provider boundaries with realistic schema/error fixtures, not whole business modules. Fix underlying assertions/regressions rather than disable tests. Add GitHub Actions with install, frontend lint/typecheck/test/build, backend lint/unit/integration, migration and image checks using safe test env and no production secrets. Pin reproducible dependencies appropriate to existing package tooling.

Acceptance: default suite runs without external provider quota/network; all failures classified and fixed or explicitly tracked with a supported live-test prerequisite; cross-owner API and real browser pending/confirm flows pass. Report baseline vs new failures and command outputs after each slice.

### Phase 5 — Observability, audit and usage

Wire structured logger and request IDs through API/errors/provider/worker boundaries. Extend existing usage and audit tables only where needed for request/workspace, feature, token source, configured pricing and resource version. Define retention/redaction; avoid storing raw sensitive prompt content by default. Add provider/model/job metrics and measured latency distributions.

Acceptance: one request can be traced through job/provider/action/audit; secrets are redacted; usage persists once; unavailable metrics display unknown rather than invented zero/healthy values. Benchmark API p50/p95, AI TTFT and job duration before making performance claims.

### Phase 6 — Storage

Implement actual S3-compatible client and config-selected provider; fail closed if selected backend is unavailable. Move uploads/exports through adapter without breaking existing local file metadata. Add owner/workspace object keys, checksum, MIME/size, traversal/symlink containment, expiring access and lifecycle cleanup. Migrate local metadata/data with verification instead of deleting files.

Acceptance: local and MinIO integration tests exercise upload/download/delete across process restarts; malformed path, MIME, oversized upload and foreign/expired token are rejected; DB references resolve to identical checksums after migration. No dictionary-backed S3 in production.

### Phase 7 — Billing and quota

Extend current PayOS integration with signature-verified webhook ingestion and unique provider event/transaction deduplication, atomic payment/subscription/entitlement updates and audit. Preserve server-side amount/currency/order checks. Centralize all feature gates, reconcile legacy `User.plan` defaults and new-user free entitlement, enforce monthly token/research/report/export/storage quotas with concurrency-safe accounting and reset dates in UI.

Acceptance: scenario H, invalid signature/amount/owner rejected, duplicate and reordered webhook harmless, failed transactions do not activate Pro, server reconciliation recovers missed delivery, UI reflects backend quota, parallel requests cannot overspend reservation. No purchase required for automated tests.

### Phase 8 — Admin completion

Build on shipped console and API tests. Surface real durable jobs, payments/subscriptions, AI cost/token/provider health, files/audit and paginated user/resource data. Mark unavailable integrations clearly. Verify sensitive confirmations, audit and secret redaction; connect existing feature flags to runtime routes.

Acceptance: scenario I, ordinary-user admin API calls return 403, every displayed aggregate derives from persisted/runtime evidence, mutation audit includes actor and before/after, pagination holds at scale. No full API keys are returned.

### Phase 9 — Workspace / organization

Extend existing workspaces/project members with organization and workspace membership/RBAC only after core gates. Backfill personal workspaces without changing current owners. Centralize OWNER/ADMIN/EDITOR/VIEWER resource policy and shared quota.

Acceptance: cross-tenant integration matrix covers all resource reads/writes/downloads/jobs/citations; role changes invalidate access; invitation/revocation and quota sharing are audited; old personal projects remain accessible to their owners.

### Phase 10 — Advanced and final hardening

After stable single-user report/export/workbook workflows, evaluate LaTeX/Typst and enterprise features. Collaborative editing is outside the focused product scope and requires a new product decision before implementation. Complete measured pagination/index tuning, retention/recovery and OWASP review (XSS/CSRF/injection/SSRF/uploads/rate limits/OAuth/secrets). Add distributed user/IP/AI endpoint limits without limiting health probes. Do not introduce Kubernetes, microservices or streaming infrastructure without demonstrated need.

Acceptance: advanced export preserves source content. Run full focused-product scenarios using real runtime integrations in a configured staging environment plus deterministic automated contract tests. Verify DOCX/PDF formatted round trips and report edits/citation mapping. Document actual limits and remaining risks before release.

## Required verification for each implementation slice

Run focused backend regression tests first, then relevant integration tests and frontend tests, typecheck, lint and build. Run full backend suite at phase boundaries with baseline comparison. Run migration and Docker checks whenever affected; do not claim an unrun check passed. New failures must be distinguished from existing failures, environment issues and external-service failures. Capture commands, pass/fail totals, schema changes, modified paths and remaining gaps in the phase delivery report.

Update README, safe env examples and architecture/migration/worker/storage/billing/admin setup as each corresponding implementation lands. Documentation never substitutes for runtime wiring, authorization, validation, loading/empty/error states, tests and build evidence.

## Audit follow-through: bounded research safety correction

The scraper findings above describe the audited baseline. During this upgrade, `services/research/scraper.py` was corrected to return empty evidence and `is_scraped=false` on failed/blocked fetches, preserve missing author/date as empty, validate original and every redirect URL through the shared SSRF validator before requesting, cap redirects and decoded response bytes, and enforce a total timeout. New deterministic MockTransport tests verify these contracts. This closes the specific fabricated scraper fallback; it does not certify all research paths. The shared validator and HTTP client resolve DNS separately, so DNS-rebinding-resistant transport remains additional hardening work. Other research search/verifier fetch paths also require review. The overall research evidence/citation acceptance gate remains open.

## Phase 1 safety increment — verified 2026-09-07

Implemented the existing workbook flow's preview/confirmation boundary in both chat and analysis toolbar. Read-only chat/analysis returns pending highlight/clear proposals; neither clears source formatting nor writes Google Sheets. Multi-sheet aggregation preserves each sheet's proposals. Local confirmation cards support preview, cancel and single consumption, preserve the reviewed color and identify their local-only scope. Export uses confirmed layers; exporting different layer colors at once is rejected explicitly rather than silently changing their colors. Chat export explicitly confirms its historical message's sheet. Remote highlight synchronization requires confirmed local cells plus an explicit remote-write confirmation and reports verification only when the API confirms read-back.

Dataset APIs now resolve stored file IDs through project ownership. Upload filenames are sanitized, reads bounded to 50MiB and temporary outputs use unpredictable unique names. XLSX downloads require a file-bound expiring signed capability (15 minutes). Mutation coordinates and colors are validated, and an absent sheet is rejected before writes. XLSX export produces a copy and does not implicitly synchronize Google. Authenticated chat context is scoped by actor and workbook content; frontend conversation identifiers are random per mounted workspace.

Sheet matching now preserves a unique case-insensitive exact match and rejects ambiguous accent-normalized matches. Identifier columns reuse the existing semantic inference and cannot be summed as numeric measures. Source failures no longer fabricate research metadata or evidence.

Validation: 71 focused backend tests passed (workbook core, Excel upgrade, data access, scraper, Google sync and data API suites); 78 frontend tests passed; typecheck and production build passed; lint has zero errors and 104 warnings. Browser checks on port 3050 with a mocked analysis response passed preview/cancel/confirm/consume and 1280px/390px overflow checks. Real Google API writes were not performed. Database schema and Docker configuration were not changed. Existing tests that expected automatic mutation were updated to require pending confirmation; the original full-suite baseline of 36 failures remains documented above, not declared resolved.

Open Phase 1 work: persist action/execution/version/undo state and audit in the database; support validated non-highlight mutation types; complete structured intent/context contracts and before/after value diffs; verify remote undo and style preservation. Local card consumption is not a durable server-side execution ledger. Remote clear is no longer called as a hidden side effect of local layer removal; its existing API needs a separately reviewed workflow. Phase 1 as a whole and the full production upgrade remain in progress.

## Phase 1 display-layer ledger increment — verified 2026-09-07

Added `workbook_actions` persistence and authenticated preview/history/confirm/cancel/undo/source endpoints. The ledger stores pending proposals, sampled actual source values, normalized CSS colors, workbook content hashes, layer revisions and action status. Confirmation checks both file content and the reviewed layer revision; repeated confirmation is idempotent. Owner serialization protects concurrent confirmations and undo; only the latest applied action can be undone. Audit events record actor, action, sheet, cell count and source hash without copying preview values into the audit log. The legacy undo route now requires authentication and scopes its session identifier by user.

The workspace and AI chat use the saved-action card for authenticated XLSX/XLSM workflows. The history panel restores applied layers and pending proposals when reopening the same source version, supports confirming or cancelling restored proposals, and exposes saved-layer undo. A backend-provided undo identifier remains available even when the latest 100 displayed records are pending proposals. CSV and guest workflows retain local confirmation cards.

Added an idempotent additive migration and README deployment instructions. A local SQLite backup was taken before running the migration. Tests cover repeated migration without loss of an existing table's data, database engine restart persistence, owner isolation, stale source/revision rejection, cancellation, idempotent confirmation, clear/undo replay, audit and normalized restored colors.

Validation: 78 focused backend tests passed with 35 warnings; 78 frontend tests passed; typecheck and production build passed; lint reported zero errors and 104 warnings; `git diff --check` passed. The backend command included `test_workbook_action_ledger`, `test_workbook_core_safety`, `test_excel_ai_workspace_upgrade`, `test_data_access_safety`, `test_research_scraper_safety`, `test_google_sheets_live_sync` and `test_phase_u7_data_analysis`. Browser checks used the web app on port 3050, an isolated database/API on port 8152, real ledger requests and mocked AI analysis: preview actual cell value, cancel, confirm, reload with local workspace cache removed, restore visible highlight color, undo, restore a pending proposal after another reload, confirm that proposal and undo. No horizontal overflow at 1280px and 390px; no browser page errors.

Scope and remaining work: this is a durable SCANT display-layer ledger, not physical workbook mutation or Google Sheets undo. Legacy local layers are not backfilled into history; clearing those layers cannot provide durable recovery of their earlier state. The panel displays the newest 100 records, while replay currently loads all records for that source version; pagination/compaction and large-file performance remain open. Source hashing is byte-exact, so regenerated spreadsheet archives may require a new preview even when cell values match. PostgreSQL migration/concurrency, real Google writes and the full backend suite were not revalidated in this increment. The earlier full-suite baseline of 36 failures is not resolved by these focused results. Other Phase 1 mutations and subsequent production phases remain in progress.
