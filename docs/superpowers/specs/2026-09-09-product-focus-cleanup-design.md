# SCANT Product Focus Cleanup Design

## Goal

Focus SCANT on one clear promise: turn user instructions, source material, and datasets into grounded reports that can be edited and exported. Reduce navigation, runtime surface area, and misleading capabilities while preserving existing user data and old links.

## Product scope

The primary user is a Vietnamese student, analyst, or business operator who needs to create a credible report. The primary journey is:

1. Start a report or analysis.
2. Attach documents, spreadsheets, or research sources.
3. Generate and review grounded content.
4. Edit the report.
5. Export DOCX or PDF.

The focused product keeps projects, report editing, data analysis, research and citations, templates, exports, authentication, settings, billing, and administration. Billing and administration remain because they support operating SCANT as a SaaS product, but they do not appear as ordinary workspace features.

## Retired capabilities

Remove these user-facing and runtime capabilities:

- AI/human probability and stylometry scoring. The current heuristic presents invented precision and must not be exposed as a trustworthy detector.
- Uploaded-audio voice-to-report. The current service fabricates a successful transcript when the provider is unavailable. Browser dictation that only transfers recognized user speech into a text field is outside this removal.
- Report automations. The current scheduler and worker state are process-local and are not durable enough for a production promise.
- Collaboration members and comments. There is no corresponding frontend workflow, and collaboration is outside the single-user core journey.
- Presentation Studio, Codebase Intelligence, Advanced OCR Layout, Document Designer, and Deep Research V2 modules that have no runtime consumer outside tests.

Remove frontend controls, API client methods, API router registration, services, and tests that exist solely for the retired capability. Preserve database tables and additive migrations for automations and collaboration so existing databases are not destructively rewritten. Do not delete uploaded files, projects, reports, sources, comments, members, automation records, or billing records.

## Information architecture

The ordinary sidebar contains seven destinations:

1. Home
2. Create new
3. Projects
4. Data
5. Research
6. Templates
7. Settings

Admin remains conditional on an admin role. Billing stays inside Settings. Brand Kit moves into Settings.

The command palette mirrors the same destinations. It must never show Admin to a non-admin user.

### Projects and documents

`/projects` becomes the unified work library. A compact segmented control switches between projects and generated reports. Project cards retain project-level actions; report rows/cards retain preview and editor actions. Search applies to the active view.

`/documents` becomes a compatibility redirect to `/projects?view=reports`. Existing report-editor URLs remain unchanged.

### Research and sources

`/research` becomes the research workspace with two top-level views:

- **Discover:** run quick/deep research, inspect evidence, and export citations.
- **Library:** browse saved project sources, add URL/file/DOI sources, verify evidence, and manage citations.

The existing research and source behaviors remain backed by their current APIs during UI consolidation. `/sources` redirects to `/research?view=library`. After the UI is consolidated, remove duplicate legacy source CRUD under `/research/sources`; retain identifier resolution and citation formatting under the research API until a separate API consolidation is justified by tests.

### Brand settings

Brand Kit becomes a section or tab within `/settings`. `/brand-kit` redirects to `/settings?tab=brand`. Brand fields and persisted values remain unchanged.

### Project types

New-project UI exposes four choices:

- **Report** using the existing `business_report` value.
- **Data analysis** using `data_analysis`.
- **Research** using `research`.
- **Custom** using `custom`.

Proposal, financial, technical, and market-research choices become templates or suggested presets under the relevant choice. Existing projects retain their stored type and remain readable, filterable, and editable. No data migration rewrites historical project types.

## Visual direction

Use the existing Tailwind and component conventions with a restrained professional workspace style. Keep neutral surfaces, one indigo primary accent, compact controls, visible focus states, and clear typography. Remove decorative metric cards and claims whose values are fabricated, including fallback research duration.

The consolidated pages use a consistent structure:

```text
WorkspacePage
  PageHeader
    TitleAndDescription
    PrimaryAction
  ViewTabs
  SearchAndFilters
  ContentRegion
    LoadingState
    EmptyState
    ErrorState
    ProjectOrReportView / DiscoverOrLibraryView
```

On mobile, view tabs scroll or wrap without horizontal page overflow, toolbars stack, and dense report/source rows become compact cards. Existing modals and destructive confirmations retain keyboard focus and accessible names.

## Data and compatibility

- Do not drop database tables or columns in this cleanup.
- Do not rewrite existing project types.
- Preserve direct report editor links, project links, downloads, and source ownership.
- Old top-level frontend URLs issue framework redirects to the new canonical views.
- Removed API endpoints return 404 because their routers are no longer mounted; no compatibility endpoint will fabricate success.
- Provider failure must produce an explicit unavailable/error state.

## Implementation boundaries

Split the work into independently verifiable slices:

1. Add behavioral tests for the focused navigation, compatibility redirects, project-type choices, and removal of misleading AI controls.
2. Consolidate the sidebar and command palette, including role-aware Admin visibility.
3. Consolidate Projects/Documents and add the documents redirect.
4. Consolidate Research/Sources and add the sources redirect.
5. Move Brand Kit into Settings and add the brand-kit redirect.
6. Reduce new project choices while preserving legacy project types.
7. Remove retired frontend features and their API client methods.
8. Unmount and remove retired backend APIs/services while preserving models and migrations.
9. Remove runtime-orphan engines and their isolated phase tests.
10. Update documentation and run focused tests, full frontend checks, relevant backend tests, and a production build.

## Testing and acceptance

The cleanup is accepted when:

- The sidebar and command palette expose only the focused destinations, with Admin role-gated.
- `/documents`, `/sources`, and `/brand-kit` redirect to their canonical focused views.
- Projects and reports remain reachable from the unified library.
- Research discovery, saved sources, evidence, and citation export remain reachable from one workspace.
- New projects offer four choices; existing legacy project types still render and open.
- No UI or mounted API exposes stylometry scoring, uploaded-audio report generation, automations, or collaboration.
- Missing AI/provider configuration returns an honest error rather than generated fallback content.
- No persisted user data or database schema is deleted.
- Frontend tests, typecheck, lint, and build pass without new errors.
- Relevant backend API/import tests pass, and the app starts with a valid OpenAPI document.

## Risks and controls

| Risk | Control |
|---|---|
| Removing a module breaks imports at startup | Add import/OpenAPI tests before deleting runtime files. |
| Existing bookmarks break | Keep redirects for all retired top-level frontend routes. |
| Historical projects disappear from filters | Preserve stored values and add legacy display mapping. |
| Consolidated pages become monolithic | Extract focused view components rather than combining two large page files inline. |
| UI looks sparse after navigation removal | Strengthen hierarchy and task-oriented empty states; do not add decorative filler. |
| Existing user data is lost | Preserve tables, migrations, records, and files; perform no destructive database migration. |

