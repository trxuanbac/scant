# Route Enrichment Implementation Plan

> **For agentic workers:** Implement task by task with tests first. The active user request authorizes implementation in this session.

**Goal:** Add a web workflow that reads a route workbook, resolves stops from a verifiable source table, measures Google driving distance, and downloads an annotated copy.

**Architecture:** A focused FastAPI service parses workbooks and source tables, while a Google Routes adapter measures routes. A Next.js page under the dashboard uploads the workbook and source URL and downloads the result. Looker report URLs are treated as report views; they cannot be assumed to expose chart rows, so the UI/API request a Google Sheet or CSV source if only a report URL is supplied.

**Tech Stack:** FastAPI, openpyxl, httpx, pytest, Next.js 16, React, Tailwind.

**Spec:** This file.

## Global Constraints

- Preserve the uploaded workbook and write only a copied XLSX.
- Never infer a precise warehouse coordinate from its name or from an unrelated provider.
- Use the configured Google Routes API for `distanceMeters`; never substitute SPX distances or straight-line distance.
- Preserve every non-consecutive waypoint and the final return to the starting SOC; measure the complete ordered route.
- Leave unresolved rows blank and list the reason in an audit sheet.
- Require an API key on the server, never in the browser bundle.

---

### Task 1: Workbook and source parsing

**Files:** `apps/api/app/services/data/route_enrichment.py`, `apps/api/tests/test_route_enrichment.py`.

- [x] Add failing tests for header detection, route parsing, source coordinate resolution, and preserving old link/km in the audit.
- [x] Implement parsing and copied-workbook output.
- [x] Run focused tests.

### Task 2: Google Routes measurement and API

**Files:** `apps/api/app/services/data/google_routes.py`, `apps/api/app/api/v1/route_enrichment.py`, `apps/api/app/api/v1/__init__.py`, `apps/api/app/core/config.py`, `apps/api/tests/test_route_enrichment_api.py`.

- [x] Add failing tests for Google request shape, missing key, Looker-only source, and successful XLSX download.
- [x] Implement the adapter and endpoint using the existing safe URL dataset loader.
- [x] Run focused tests.

### Task 3: Web workflow

**Files:** `apps/web/src/app/(dashboard)/routes/page.tsx`, `apps/web/src/lib/api.ts`, `apps/web/src/lib/productFocus.ts`, `apps/web/src/components/Sidebar.tsx`, `apps/web/src/components/CommandPalette.tsx`, `apps/web/src/i18n/messages/{vi,en}.json`, `apps/web/src/lib/__tests__/productFocus.test.mjs`.

- [x] Add failing navigation test.
- [x] Implement page with file/link fields, source guidance, progress/error/result states, and download.
- [x] Run web tests, typecheck, lint and build.

### Task 4: End-to-end verification

- [x] Exercise the sample workbook with a synthetic source table and mocked Google response; inspect output cells and audit sheet.
- [x] Confirm missing production configuration produces an explicit error and no fabricated km.
- [x] Review the changed files and report the remaining external dependency.

The live sample has 235 route rows, 138 distinct stop names, and 43 round trips. The linked Looker report is a rendered report, not a downloadable source URL; a chart export or mapped source table is still needed. The running backend also lacks `GOOGLE_MAPS_ROUTES_API_KEY`, so no production Google distance was claimed or filled.
