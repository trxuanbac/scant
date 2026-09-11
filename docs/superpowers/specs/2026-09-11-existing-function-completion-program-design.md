# Existing Function Completion Program Design

**Date:** 2026-09-11

## Goal

Complete the product capabilities that already exist in SCANT without adding new top-level modules. The finished product should provide one dependable path from a dataset or research source to a grounded analysis, an editable report, and a faithful DOCX/PDF export.

The program preserves the seven regular-user destinations already defined by the focused product cleanup:

1. Dashboard
2. Create new
3. Projects
4. Data
5. Research
6. Templates
7. Settings

Administration remains visible only to authorized administrators. Historical database tables remain intact, but retired collaboration, automation, voice, presentation, code-intelligence, advanced OCR, plagiarism/stylometry, document-designer, and Deep Research V2 runtime surfaces are not restored.

## Product Principle

The primary user is a Vietnamese analyst, manager, researcher, or report author who needs to turn existing data and evidence into a document that can be checked and delivered. Every retained capability must help the user answer one of these questions:

- What data or evidence am I using?
- What does it show, and how was that result calculated?
- What needs my attention or confirmation?
- How do I turn the accepted result into a report?
- Can I reopen, revise, and export that work without losing fidelity?

Function count is not a success measure. Completion means the core path has explicit state, recoverable failures, ownership checks, durable work, and testable output.

## Current Baseline

The focused navigation and saved-dataset analysis handoff are already implemented. The current data/security/workbook slice passes its focused backend suite, frontend tests, typecheck, lint without errors, and production build.

Material completion gaps remain:

- `projects/new/page.tsx`, `ExcelAnalysisWorkspace.tsx`, `ExcelAIChatPanel.tsx`, `workbook_chat_service.py`, `spreadsheet_query_engine.py`, and `reports.py` combine many responsibilities and are difficult to change safely.
- Analysis history is split between browser storage and the durable workbook display-layer ledger. Findings, questions, and scope are not yet a complete server-side session.
- Grounded workbook results contain sheet/range evidence in several paths, but the evidence contract is not uniform through report insertion and export.
- The workspace fallback sends a finding to the first report returned by the API, and the report insertion endpoint accepts `table_data` but currently persists only title and summary text. This can target the wrong report and lose structured evidence.
- Report work uses persisted Job rows but several execution paths still use process-local `asyncio.create_task`; a process restart can orphan active work.
- The current PDF exporter writes printable HTML with an `.html` artifact; it does not yet produce a PDF file.
- Broad backend tests mix deterministic tests with live provider and environment tests. The current broad run cannot be used as a clean release gate.
- Readiness and storage adapters overstate production capability: storage readiness can succeed without a write check, AI is always reported online, and the S3 adapter is process memory.
- SQLite startup schema mutation and standalone additive scripts are not a production migration chain.
- Product funnel events are process-local and are not connected to the retained workflow.

## Chosen Delivery Approach

Upgrade one existing user journey at a time, using a shared set of contracts underneath it. Each phase must leave the application usable and pass its acceptance gate before the next phase starts.

The order is:

0. Deterministic release and migration foundation
1. Data analysis completion
2. Data-to-report, editor, and export completion
3. Projects and dashboard completion
4. Research and source completion
5. Templates, settings, administration, authentication, billing, and operational completion
6. Final release hardening

Cross-cutting reliability work is implemented when the first retained feature depends on it. For example, durable job dispatch belongs in phase 2 because report generation requires it; a truthful provider health contract belongs in phase 4 and is then reused by Settings and Admin in phase 5.

This avoids an infrastructure-only rewrite and also avoids building visible features on process-local behavior.

## Phase 0 — Deterministic Release and Migration Foundation

Phase 0 changes no product workflow. It makes the current behavior safe to evolve and supplies a trustworthy release signal.

It is delivered as four bounded increments:

1. **0A — Test classification:** define `unit`, `integration`, `browser`, and `live`; mark current live tests and make the default command reject outbound network access.
2. **0B — Test isolation:** centralize database, temporary storage, provider, clock, retry, and singleton fixtures so order and parallel execution do not affect results.
3. **0C — Migration baseline:** introduce Alembic, fingerprint the known current schemas, bridge the existing admin/workbook scripts, and verify the SQLite/PostgreSQL migration matrix.
4. **0D — CI release gate:** run deterministic backend/frontend tests, typecheck, lint error gate, build, migration validation, and secret checks on every proposed change.

Introduce an Alembic migration chain with an audited baseline for the current schema before Phase 1 adds analysis-session storage. Keep local SQLite support and verify the same chain against PostgreSQL. Production startup no longer mutates schema automatically after the baseline is deployed; development compatibility behavior remains temporary and explicit.

Separate backend tests into deterministic unit/integration markers and opt-in live-provider markers. Provider clients and database session factories become injectable at the boundaries exercised by the current tests. A test that overrides the API database must not open a second global database inside the AI gateway. Clock, UUID, random values, retry delay, and provider outcomes are controllable in deterministic tests. Add a minimal CI workflow for deterministic backend tests, frontend tests, typecheck, lint error gate, production build, migration-up validation, and secret checks. CI rejects unexpected outbound network access in deterministic suites.

### Acceptance gate

1. A clean test run has no dependency on Internet, production AI keys, or payment credentials.
2. Live-provider tests are opt-in and report an explicit skip reason when unconfigured.
3. The current schema can be stamped or migrated through the audited baseline without data loss.
4. A fresh SQLite and PostgreSQL database can migrate to head.
5. The current retained feature suites, frontend typecheck, lint error gate, and build pass in CI.
6. Shared test fixtures isolate database, storage, singleton state, clock, and providers so test order and parallel execution do not change results.

## Alternatives Considered

### Upgrade every screen in parallel

This produces visible activity quickly but creates incompatible state and API contracts across the product. It is rejected because the same data, evidence, job, and report objects cross several screens.

### Finish backend infrastructure before touching the UI

This reduces some operational risk but delays user-visible value and encourages abstractions without a concrete consumer. It is rejected as the primary delivery model. Infrastructure is completed immediately before the retained workflow that needs it.

### Add more AI tools and specialized modules

This expands the surface while current core flows remain incomplete. It is rejected. Existing analysis, research, editor, export, templates, and administration are sufficient for the target workflow.

## Canonical End-to-End Flow

```text
Owned source
  -> immutable source version
  -> profile and quality findings
  -> analysis session with explicit scope
  -> grounded findings and proposed actions
  -> user confirmation
  -> report outline and accepted findings
  -> section edits and versions
  -> authorized export artifact
```

The flow uses stable identifiers rather than copying browser state between pages. A user can leave and return at each durable boundary.

## Shared Contracts

### Source version

Every analysis refers to an owned source and an immutable content version. The minimum identity is:

- owner ID;
- uploaded-file ID or supported connected-source ID;
- SHA-256 content hash or provider revision token;
- original file name;
- media type and byte size;
- created or observed timestamp.

A changed source creates a new version. Existing findings remain visible but are marked stale until recalculated. Original files are never silently overwritten.

### Analysis scope

Every analysis request carries an explicit scope:

- workbook;
- selected sheets;
- selected range;
- or a supported cross-file comparison.

An empty or stale sheet selection does not silently expand to the whole workbook. Ambiguous Vietnamese sheet or column names return candidates and a clarification state instead of choosing the first match.

### Evidence

Every numerical finding uses one response and persistence shape:

```text
Evidence
  source_version
  sheet
  ranges
  operation
  inputs
  formula_or_method
  row_count
  value
  confidence
  warnings
```

The UI can navigate from a finding to the relevant sheet/range. When a finding enters a report, this evidence remains attached through section edits and export. Narrative text without supporting data is labeled interpretation rather than verified fact.

### Proposed action

Read-only navigation may execute immediately. Any workbook or report mutation follows:

```text
proposed -> previewed -> confirmed -> applied -> optionally undone
```

Changing the target, source version, or report revision invalidates the preview. The current durable workbook display-layer ledger remains the starting implementation and is extended rather than replaced.

### Job

Long work uses the existing SQL Job record as the source of truth. The execution contract adds:

- queued, running, waiting-for-user, retrying, completed, failed, and cancelled states;
- idempotency key;
- attempt count and maximum attempts;
- lease owner and lease expiry;
- heartbeat timestamp;
- structured stage and progress;
- typed error code, retryability, and safe user message;
- result references rather than large result bodies.

Dispatch moves from request-process `asyncio.create_task` and memory queues to a Redis-backed worker. A worker claims a SQL job with a lease, renews the heartbeat, and records completion atomically. Expired jobs can be reclaimed without duplicate report sections or exports.

### Revision

Mutable reports use optimistic concurrency. A write supplies the revision it was based on. A stale write returns `409` with the current revision and enough metadata to reload or compare. Accepted AI changes, manual saves, and restored versions increment the same report revision.

### Error response

Retained APIs use a common error envelope:

```text
code
message
retryable
field_errors
request_id
details
```

The user-facing message is safe and actionable. Provider payloads, paths, tokens, prompts, and stack traces do not cross the API boundary.

## Phase 1 — Data Analysis Completion

Phase 1 is delivered as five bounded increments:

1. **1A — Source version and evidence contract:** normalize owned source identity, analysis scope, and evidence responses without changing the visible workflow.
2. **1B — Durable analysis sessions:** persist session, message, finding, source version, and selected scope; retain the browser snapshot as a temporary fallback.
3. **1C — Quality and clarification:** expose deterministic quality issues and return structured clarification when sheet, column, date, or unit selection is ambiguous.
4. **1D — Workspace integration:** add the quality queue, clickable evidence, restored session history, stale-source state, and complete responsive/error behavior to the existing workspace.
5. **1E — Regression and extraction:** complete the supported workbook task matrix and extract large files only along the proven contracts above.

### Product behavior

The Data library remains responsible for finding, inspecting, versioning, and opening an owned dataset. The existing analysis workspace remains responsible for analysis; no second workspace is embedded in `/data`.

The completed workspace provides:

- explicit workbook, multi-sheet, single-sheet, and range scope;
- a quality issue queue for missing values, duplicates, outliers, invalid dates, mixed types, and formula errors that the current engines can verify;
- clickable evidence that selects the relevant sheet and scrolls to the relevant cell or range;
- consistent deterministic answers for supported aggregation, comparison, missing-data, duplicate, outlier, formula, and row-filter tasks;
- a clarification panel for ambiguous sheet, column, unit, and date choices;
- proposed workbook actions with preview, confirm, cancel, durable history, and bounded undo;
- saved server-side sessions containing source version, scope, questions, answers, accepted findings, and action references;
- a clear degraded state when AI is unavailable while deterministic analysis remains usable;
- an explicit report picker before an accepted finding is sent to an existing report;
- export of the reviewed workbook layer without modifying the original source.

### Structure

The current large frontend and backend files are split at existing behavior boundaries:

```text
AnalysisWorkspace
  SourceHeader
  ScopeSelector
  QualityIssueList
  WorkbookViewport
  FindingList
  AnalysisComposer
  ActionReview
  SessionHistory

Data API
  source/profile routes
  session routes
  deterministic query routes
  AI narrative routes
  workbook action routes
```

This is incremental extraction. Existing endpoints stay available until their consumers move to the new internal services.

### Persistence

Add additive analysis-session and analysis-finding storage. A finding stores the evidence object and source-version identity. Large workbook previews remain derived and are not stored as duplicated JSON blobs.

### Acceptance gate

1. A saved, uploaded, or supported linked dataset opens the same workspace contract.
2. Reopening a session on another browser restores scope, questions, findings, and durable actions.
3. Every displayed numeric finding has navigable evidence or is explicitly labeled unverified interpretation.
4. Ambiguous scope requires clarification and never silently selects the first sheet.
5. Source changes mark previous results stale.
6. Mutation proposals require an unchanged preview and explicit confirmation.
7. The supported deterministic workbook task matrix passes for XLSX, XLSM, and CSV where applicable.
8. Data access, path containment, size limits, source version, and cross-user isolation tests pass.

## Phase 2 — Data-to-Report, Editor, and Export Completion

### Report creation

The user selects accepted findings and chooses **Create report**. SCANT shows a reviewable outline before starting long generation. Each planned section declares which findings and research evidence it will use. The user can edit, reorder, remove, or approve the outline. Sending a finding to an existing report always requires an explicit target report; the client never selects the first list result implicitly.

Generation uses durable jobs and can resume after a worker or API restart. Retrying a failed stage is idempotent. Cancellation stops future stages and retains completed, reviewable work.

### Editor

The existing Tiptap editor and AI changeset models are retained. Completion adds:

- revision-aware autosave;
- visible saving, saved, offline, conflict, and retry states;
- section-level AI proposals rendered as a diff;
- accept, reject, and partially accept without hidden content replacement;
- report version snapshots at meaningful boundaries;
- restore as a new revision rather than destructive rewind;
- claim/evidence inspection from the edited sentence;
- warnings when a source version used by a report has changed.

The incorrect `ReportVersion` relationship contract is corrected with a migration-safe model fix before relying on version restoration.

### Export

DOCX and PDF export use a normalized report snapshot taken at a specific revision. The export record stores that revision and artifact checksum. A repeated request with the same report revision, format, and settings returns or regenerates the same logical export safely. PDF export produces a real PDF artifact with a valid `%PDF` signature rather than returning printable HTML under a PDF label.

Required fidelity covers headings, page breaks, tables, images, captions, footnotes or evidence notes, citations, references, headers/footers, page numbering, and table of contents behavior supported by the current exporters.

### Acceptance gate

1. A user can review an outline before generation.
2. Restarting API or worker during generation does not lose the job and does not duplicate sections.
3. Autosave rejects stale revisions without overwriting newer content.
4. AI edits remain pending until explicitly accepted.
5. Report versions can be listed, compared, and restored as a new revision.
6. A data-backed claim navigates to its retained evidence.
7. DOCX and PDF fixtures preserve the supported content matrix and reference the exported report revision.
8. All report, section, export, and job endpoints enforce project ownership.
9. Structured finding tables and evidence survive analysis-to-editor-to-export round trips.
10. Export downloads use authorized storage records and signed URLs rather than guessable filenames.

## Phase 3 — Projects and Dashboard Completion

### Projects

The project detail page becomes the durable record of the existing workflow. It groups the project's sources, datasets, analysis sessions, reports, active jobs, and export artifacts without adding a new navigation destination.

The list and detail surfaces provide:

- meaningful status derived from real child records;
- last activity and the next recommended action;
- filters for workflow, status, and update time;
- a single **Continue** action that opens the most recent incomplete work;
- visible failures with retry or recovery actions;
- safe archive behavior; permanent deletion is separate and explicit if retained.

Project list and source-library reads are side-effect free. Opening an empty screen never creates a project automatically. Project list summaries are aggregated server-side with pagination and avoid per-card preview request fan-out.

### Dashboard

The dashboard answers what changed, what needs attention, and what the user can continue. Decorative counts give way to real work states: active jobs, failed jobs, datasets with unresolved quality issues, reports awaiting review, and exports ready to download.

### Acceptance gate

1. Project status is derived consistently and does not contradict job/report state.
2. Continue opens the correct incomplete analysis, report, or review task.
3. Empty, loading, error, filtered-empty, and pagination states are complete.
4. Dashboard cards link to the exact filtered work item list.
5. Project access and artifact download remain owner-scoped.
6. List endpoints do not create records and do not issue an N+1 request pattern for summaries or previews.

## Phase 4 — Research and Source Completion

### Research

The existing unified Research and source-library destination is retained. Completion consolidates provider orchestration behind one service contract and separates deterministic local tests from live-provider checks.

The user sees:

- research plan and query status;
- provider availability and degraded behavior;
- found, fetched, verified, partially verified, broken, and rejected source states;
- deduplication by canonical URL, DOI, and content fingerprint;
- retry for transient provider or fetch failures;
- evidence excerpts within copyright limits;
- claim-to-source traceability;
- citation metadata completeness and style preview.

Displayed progress, author, year, publisher, citation count, and quality score come from measured provider or verification state. Missing metadata stays unavailable; the UI does not cycle simulated pipeline progress or substitute a favorable default score.

Failure to search or fetch never creates fabricated evidence. Redirect destinations, response size, timeouts, and private network targets remain validated on every fetch.

### Acceptance gate

1. Offline deterministic tests pass without network credentials.
2. Live provider tests are explicitly marked and run only in a configured environment.
3. Provider failure produces a visible degraded or unavailable state, not an empty-success result.
4. Duplicate sources merge safely without losing citations or notes.
5. Every verified claim points to an accessible source and retained evidence record.
6. Citation round-trip tests pass from research result through editor and export.
7. SSRF, redirect, size, timeout, and malformed-content tests pass.
8. Opening an empty research/source library does not create a project; creation remains an explicit user action.

## Phase 5 — Supporting Function Completion

### Templates

Retain the template library and reverse-engineering path. Remove the hard-coded template selection and add real previews, immutable version selection, compatibility results, placeholder mapping review, and an explicit apply step. Applying a template does not silently alter report content. Unsupported formatting is listed before use.

### Settings and brand

Unify retained user, locale, appearance, brand, AI preference, Google Sheets connection, and account settings behind clear save/error states. A success message is shown only after the server confirms persistence; a local toast is not treated as a save. Brand settings have one preview and one persistence contract shared by report and export. Google identity remains separate from explicit Google Sheets data consent.

### Administration

The existing admin console reports actual stored or measured values. Provider status distinguishes configured, reachable, degraded, and untested. Job controls operate on durable jobs. Storage and readiness status come from real probes. Audit records cover privileged mutations without exposing private document content.

### Authentication and billing

Complete inactive-user handling, token expiry/refresh behavior, password reset and password-change session policy, OAuth state and refresh failure paths, verified payment webhook idempotency, subscription transitions, and consistent server-side entitlement checks. Demo credentials are unavailable in production. Billing remains hidden or unavailable when a real provider is not configured; it does not fall back to a fake successful checkout. Plan descriptions do not advertise retired voice, diagram, presentation, or other removed runtime features.

### Acceptance gate

1. Template preview and application use a selected immutable template version.
2. Settings save and validation failures are field-specific and retryable.
3. Google login never grants Sheets access without explicit connection consent.
4. Admin health does not claim a provider is online without evidence.
5. Privileged changes are authorized and audited.
6. Payment webhook replay cannot duplicate entitlement changes.
7. Entitlements are enforced consistently on API entry points.
8. Every retained setting round-trips through the API and remains correct after reload.

## Phase 6 — Final Release Hardening

### Database and migration

Audit the Alembic chain introduced in Phase 0 across every program migration and representative production-like data. Every phase uses additive migrations first, backfills separately, switches reads/writes after verification, and removes legacy fields only in a later release.

### Storage

Keep local storage for development. Replace the in-memory S3 placeholder with a real configured S3-compatible adapter for production. Validate root containment, MIME, size, checksum, ownership, retention, and signed download expiry. Readiness performs a bounded write/read/delete probe against the configured provider.

### Observability

Propagate one request ID through HTTP, job, AI, research, and export work. Persist or export operational metrics for job duration/failure, provider latency, analysis operations, export failure, and the privacy-safe retained-product funnel. Health and readiness use measured state with explicit timestamps.

### CI and deployment

Extend the deterministic CI introduced in Phase 0 with final end-to-end and deployment checks for:

- backend unit and integration suites;
- frontend unit tests;
- typecheck and lint error gate;
- production build;
- migration up from baseline on PostgreSQL;
- API and browser smoke tests;
- secret and generated-artifact checks.

Live AI, academic, search, and payment sandbox checks run separately and cannot make the deterministic suite flaky. Build the Docker images referenced by Compose and add health-based service dependencies before describing Compose as deployable.

### Acceptance gate

1. A clean checkout can migrate, build, start, and pass deterministic smoke tests.
2. The full deterministic suite has no external network dependency.
3. Browser E2E covers login, saved/uploaded dataset, analysis, action confirmation, report generation, edit, and export.
4. Restart and retry tests prove job recovery and idempotency.
5. PostgreSQL migration and object-storage integration pass in staging.
6. Readiness becomes degraded when a required dependency fails.
7. No secret, database, uploaded document, or generated export is included in the release artifact.

## Frontend Design Direction

Use the existing restrained slate/white system and indigo primary actions. Semantic amber and red appear only for warnings and failures. Existing information is progressively disclosed instead of being duplicated into large cards.

Shared interaction requirements:

- one primary action per surface;
- compact desktop density and usable mobile stacking;
- stable loading skeletons;
- explicit empty, filtered-empty, error, stale, conflict, unavailable, and retry states;
- visible keyboard focus and semantic controls;
- no page-level horizontal overflow;
- tables use headers and scroll inside their data region;
- dialogs and inspectors have accessible titles and focus behavior;
- status is never communicated by color alone.

Large components are extracted into named feature components and hooks while preserving route behavior. No new global frontend state library is introduced.

Global creation modes are shown only inside the Create flow. Report outline and AI panels use accessible drawers below the desktop breakpoint rather than disappearing. Before section changes, route changes, or unload, the editor either flushes pending saves or clearly reports that a save could not complete.

## Security and Privacy Requirements

- Unknown and foreign resource identifiers return a neutral 404 where disclosure would leak tenancy information.
- Every child resource is authorized through its owning project/user, not only by child ID.
- File paths are server-derived, normalized, and constrained to configured roots.
- Connected URLs are checked before and after redirects and cannot access private, loopback, link-local, or metadata networks.
- Original workbook and report content is not placed in logs, analytics, or audit records.
- Signed URLs are short-lived, resource-specific, and revocable by version or record state where required.
- AI prompts receive only the source scope required for the task.
- All mutation previews are invalidated by source or revision changes.

## Testing Strategy

### Deterministic layers

1. Pure parsing, routing, calculation, validation, and state-machine unit tests.
2. Service tests with fixed workbook, document, and source fixtures.
3. API integration tests against an isolated database and temporary storage.
4. Frontend interaction tests for state transitions and accessibility.
5. Playwright golden-path tests against locally controlled services.

The shared backend fixture owns one isolated database/session factory, temporary storage root, reset singleton state, and controlled provider implementations. Tests do not write to the repository's default storage. Existing in-process FastAPI tests remain integration tests; the `e2e` label is reserved for browser tests across running processes.

Tests do not open a second global database session when the API dependency has been overridden for an isolated test. AI, search, storage, and payment providers are injected behind contracts so deterministic tests use controlled fakes.

### Live layers

Provider tests carry an explicit live marker, configured timeout, and skip reason. Their results describe provider availability; they do not block deterministic validation unless a release process explicitly requires that provider.

### Regression evidence per phase

Each phase records:

- focused tests written before implementation;
- previous retained-flow tests;
- typecheck, lint, and build results where relevant;
- migration result on a copy of representative data;
- browser smoke evidence;
- known external or legacy failures kept separate from the phase gate.

## Rollout and Compatibility

- Use additive schema changes and dual-read only where necessary.
- Preserve old URLs through the existing redirect layer.
- Preserve existing file IDs, project IDs, report IDs, and historical records.
- Introduce server-side analysis sessions without deleting browser snapshots; import or ignore old snapshots safely, then remove the fallback in a later release.
- Keep current API fields during consumer migration and mark replacements before removal.
- Snapshot OpenAPI contracts and generate or validate frontend request/response types so new code does not widen the existing use of `any`.
- Gate incomplete bulk generation and any provider-dependent surface when its durable path is not available.
- Back up the target database before migrations and verify rollback procedures on staging.
- Roll out material behavior behind a controlled percentage when production traffic exists. Stop the rollout for any data loss or duplication, or when 5xx rate rises by 0.5 percentage points, p95 latency rises by 15%, or job failure rate rises by 1 percentage point from the pre-release baseline.

## Program Completion Criteria

The program is complete when:

1. All seven retained user destinations have complete loading, empty, error, stale, conflict, success, and recovery behavior relevant to their job.
2. The canonical source-to-export flow survives browser, API, and worker restarts at its durable boundaries.
3. Numerical claims are traceable to source versions and evidence through report export.
4. Mutations require review and support bounded undo or version restore.
5. Deterministic CI is green without Internet or production credentials.
6. Live-provider availability is reported separately and honestly.
7. PostgreSQL migrations, configured object storage, authorization, observability, and deployment smoke tests pass in staging.
8. Retired modules remain outside runtime and navigation.
9. Large implementation files have been split along the contracts described here without a parallel replacement architecture.

## First Implementation Slice

The first implementation plan covers only Phase 0A. Subsequent plans cover Phase 0B, 0C, and 0D in order. After the complete Phase 0 acceptance gate passes, the next plan covers Phase 1A: the owned source-version, explicit scope, and uniform evidence contracts. Existing saved-dataset navigation and workbook action-ledger work is treated as the baseline and is not rebuilt.

Each bounded increment receives its own plan and verification record. Phase 2 planning starts only after the Phase 1 acceptance gate passes. The same rule applies to every later phase.
