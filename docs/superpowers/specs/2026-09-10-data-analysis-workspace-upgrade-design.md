# Data Analysis Workspace Upgrade Design

**Date:** 2026-09-10

## Goal

Make the saved-dataset library and the existing spreadsheet analysis workspace behave as one reliable flow. A signed-in user can choose an existing Excel or CSV dataset, enter direct analysis without uploading it again, continue to a DOCX report when needed, and recover from load failures without losing context.

## Current Problems

1. Every **Analyze** link on `/data` opens the generic data workflow without identifying the selected dataset. The user must select or upload the data again.
2. `/data` treats a failed file-list request as an empty library. The page gives no error, cause, or retry action.
3. Preview errors are shown but cannot be retried without closing and reopening the modal.
4. The direct-analysis setup accepts an uploaded browser `File` or a public URL, while the underlying workspace and data API already support a stored `file_id`. The creator page does not expose that path.
5. Switching from analysis to DOCX generation would lose a stored dataset because the report endpoint accepts uploads and URLs but not an existing dataset identifier.
6. Three legacy tests expect highlight operations in the immediately executable `actions` list. The current service intentionally returns them as `pending_actions`, requiring preview and explicit confirmation.
7. `POST /files/{file_id}/signed-url` loads a file by identifier but does not verify that its project belongs to the current user before creating a token.

## Chosen Approach

Extend the existing flow with a stable dataset query parameter and stored-dataset state. Reuse `ExcelAnalysisWorkspace`, the profile endpoint, workbook action ledger, and report pipeline. Do not create a second analysis engine or duplicate the workspace inside `/data`.

The canonical direct-analysis URL is:

```text
/projects/new?mode=auto&type=data_analysis&workflow=data&analysis=direct-analysis&dataset=<file-id>
```

This approach keeps `/data` focused on finding and inspecting datasets, while `/projects/new` remains the place where direct analysis and report generation run.

## Alternatives Considered

### Embed the full workspace in `/data`

This could reduce one navigation step, but it would give `/data` two responsibilities and duplicate state currently owned by the project creator. It would also make switching between direct analysis and DOCX generation harder to keep consistent.

### Polish the current library only

This has the smallest implementation cost, but the selected dataset would still be discarded when the user clicks **Analyze**. It does not solve the main workflow defect.

## User Experience

### Dataset library

The page header has one primary action for adding a new dataset. A compact toolbar contains search and the real dataset/group counts. The main region uses dense dataset rows rather than large decorative cards.

Each primary row shows:

- file name and size;
- row, column, and sheet counts when available;
- quality status for missing values, duplicates, or profile warnings;
- duplicate/similar-version information;
- **Preview** and **Analyze** actions.

Search matches file names case-insensitively. Existing duplicate grouping stays intact, and search filters both primary entries and their visible variants.

### States

- **Loading:** stable skeleton rows preserve the content shape.
- **Empty:** explains which formats are supported and links to the existing upload workflow.
- **Error:** states that datasets could not be loaded and offers **Try again**.
- **Preview loading:** preserves modal dimensions.
- **Preview error:** keeps the selected dataset visible and offers **Try again**.
- **No search results:** keeps the search term and offers a clear-search action.
- **Permission failure:** shows a neutral unavailable message and returns the user to the dataset library.

### Visual direction

Use white and slate surfaces with indigo for the primary action. Semantic amber and red appear only for quality warnings or failures. Use 1px borders, compact controls, restrained radius, and visible keyboard focus. Dataset rows stack their actions below metadata on mobile; wide previews retain horizontal table scrolling.

## Component Boundaries

```text
DataWorkspacePage
  DataPageHeader
  DatasetToolbar
    DatasetSearch
    DatasetCounts
  DatasetContent
    DatasetLoadingState
    DatasetErrorState
    DatasetEmptyState
    DatasetNoResultsState
    DatasetGroupList
      DatasetRow
      DatasetVariantList
  DatasetPreviewModal
    DatasetSummary
    SheetTabs
    VerifiedFacts
    ColumnSummary
    SpreadsheetPreview

UniversalProjectWizardContent
  StoredDatasetBootstrap
  DataAnalysisModeSelection
  DirectAnalysisSetup
  ExcelAnalysisWorkspace
  ReportGenerationFlow
```

Small pure helpers own URL construction, dataset search, and dataset query parsing so the behavior can be tested without rendering the large page components.

## Data Flow

1. `/data` fetches the current user's files and retains supported spreadsheet formats.
2. The user clicks **Analyze** for a dataset.
3. The link includes `analysis=direct-analysis` and `dataset=<file-id>`.
4. The project creator reads the stored dataset identifier and requests `GET /data/profile/{file_id}`.
5. On success it initializes `dataPreview`, the selected sheet, stored file metadata, and opens `ExcelAnalysisWorkspace` with `fileId`.
6. Workbook chat, deterministic analysis, sheet analysis, and the action ledger send `file_id`; existing API authorization resolves the owned file.
7. If the user requests a DOCX report, the client sends `dataset_file_id` to `/reports/auto-create`.
8. The report endpoint verifies ownership and reads the existing bytes. It feeds them through the current dataset-storage/profile path for the newly created report project, preserving the existing report-generation contract.

Changing analysis mode must preserve the `dataset` query parameter. Returning to `/data` does not alter or delete the stored dataset.

## API and Security Contract

### Data profile and workbook operations

Existing `owned_dataset` remains the single authorization boundary for stored dataset access. Unknown and foreign identifiers both return 404 so the endpoint does not reveal whether another user's file exists.

### Report generation

`POST /reports/auto-create` accepts an optional `dataset_file_id` form field. When provided:

- the request must be authenticated;
- the file must belong to a project owned by the current user;
- it must have a supported spreadsheet extension;
- the stored path must exist and remain within the configured upload directory;
- the file must not exceed 50 MB;
- the endpoint passes the bytes through the current `store_dataset_from_bytes` path.

A request may use one primary dataset source: stored dataset, uploaded spreadsheet, or public URL. Template files remain independent.

### Signed download URL

`POST /files/{file_id}/signed-url` must join the file to its project and verify `Project.user_id == current_user.id` before creating a token. A foreign or unknown file returns 404.

## Spreadsheet Action Safety

Read-only navigation actions may execute immediately. Highlight and clear operations remain proposals:

1. the backend returns them in `pending_actions` with a concrete sheet and cells or rows;
2. the UI shows a preview;
3. the user explicitly confirms the unchanged target;
4. the action ledger records the layer and source hash;
5. the user can undo the latest applied layer.

Legacy tests will be updated to assert `pending_actions`. The production response must not move highlight operations back into `actions` merely to satisfy old assertions.

## Error Handling

- Dataset-list failure is distinct from an empty list.
- A retry starts a new request and clears only the previous error.
- Stored-dataset bootstrap guards against stale responses if the query parameter changes.
- Profile 401/404/422 responses use the shared API error formatter and offer navigation back to `/data`.
- Report creation validates an existing dataset identifier, ownership, path, type, and size before it creates the report project or starts long-running work. Validation failure therefore leaves no incomplete project behind.
- Existing workbook action errors remain local to their action cards and do not erase analysis results.

## Responsive and Accessibility Requirements

- Below 640 px, toolbar controls stack, dataset actions fill the available width, and metadata wraps without horizontal page overflow.
- From 640 to 1024 px, rows may wrap actions while keeping file metadata visible.
- Above 1024 px, rows use one-line actions and a compact inspector modal.
- Search has a visible label or accessible name.
- Buttons use button semantics; navigation uses links.
- Icon-only controls have accessible names.
- Focus-visible rings are present on all interactive controls.
- Error messages use `role="alert"`; changing counts and load states use an appropriate polite live region.

## Testing Strategy

### Frontend

- URL helper preserves existing query context and adds/removes `dataset` and analysis mode correctly.
- Dataset filtering is case-insensitive and retains matching variants.
- Source-level component tests verify populated, loading, error, retry, empty, and no-results states.
- Stored-dataset bootstrap tests verify successful profile loading, 404 recovery, and propagation of `fileId` into the workspace and report form.
- Existing local action confirmation and ledger tests continue to pass.

### Backend

- A user can profile and analyze an owned stored dataset.
- A user cannot profile, analyze, create a signed link for, or generate a report from another user's dataset.
- Report auto-create accepts a valid owned `dataset_file_id` and uses the existing dataset profile path.
- Analysis tests assert highlight suggestions in `pending_actions` and verify that `actions` contains no write-like highlight operation.

### Verification

Run focused frontend tests, focused backend tests, frontend typecheck, lint, and production build. Then run the broader data test suite. External-provider failures are reported separately and never counted as proof that local functionality passed.

## Scope Limits

This upgrade does not add new chart types, a second AI analysis engine, dataset deletion, dataset editing, real-time collaboration, or direct writes to original Excel/Google Sheets files. It focuses on reliable dataset selection, analysis continuity, safe actions, clear recovery states, and access control.

## Acceptance Criteria

1. Clicking **Analyze** on a saved dataset opens direct analysis with that exact dataset already loaded.
2. Chat, analysis actions, saved highlight history, and DOCX continuation all use the same owned dataset identifier.
3. List and preview failures are visible and retryable.
4. Search and responsive dataset rows work without page-level horizontal overflow.
5. Foreign dataset identifiers cannot be used through profile, analysis, report, or signed-link endpoints.
6. Highlight and clear actions require preview and confirmation.
7. The focused test suites, typecheck, lint, and production build pass without new errors.
