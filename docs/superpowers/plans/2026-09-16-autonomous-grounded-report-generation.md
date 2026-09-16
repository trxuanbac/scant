# Autonomous Grounded Report Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a one-click report pipeline that follows an optional DOCX template, researches real web sources, writes source-grounded content, imports relevant web images, and produces a reference list containing only cited sources.

**Architecture:** Extend the existing `AgenticReportOrchestrator` with focused services for template/citation policy, research planning and source normalization, claim evidence, deterministic bibliography rendering, automatic image import, and a final integrity gate. Persist checkpoints in existing job/report JSON fields and reuse the existing `Source`, `ClaimSource`, `ImageAsset`, TipTap, and export paths so the feature remains resumable and compatible with Studio.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Pydantic, httpx, existing AI gateway/search providers, Next.js 16, React, TypeScript, Tailwind CSS, TipTap, pytest, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-16-autonomous-grounded-report-generation-design.md`

## Global Constraints

- The pipeline is fully automatic after the user starts it.
- A supplied DOCX template controls structure, presentation, and citation style; missing mandatory sections are added in the template's style.
- Without a detectable template rule, use APA 7 for research/academic reports, IEEE for technical reports, and numbered references for business/proposal reports.
- Prefer official, academic, standards, university, and reputable institutional sources; use general web sources only when stronger sources are unavailable or the source is the subject's official site.
- Never invent a URL, title, author, publisher, publication date, or reference entry.
- The bibliography contains only sources cited in the report.
- Web images are copied into project storage, not hotlinked, and retain source provenance.
- Images are optional; do not insert an irrelevant image to meet a quota.
- Preserve current spreadsheet grounding behavior and keep private uploaded content out of public search queries.
- Reuse existing database models unless a test proves an existing field cannot represent required data.

---

## File Structure

### New backend units

- `apps/api/app/services/agent/report_research_contracts.py`: versioned Pydantic contracts shared by report research stages.
- `apps/api/app/services/agent/template_profile_service.py`: converts parsed DOCX context and report type into template and citation policy.
- `apps/api/app/services/agent/grounded_research_service.py`: builds section queries, normalizes/deduplicates sources, ranks trust/relevance/freshness, and builds section evidence packets.
- `apps/api/app/services/citations/bibliography_service.py`: renders inline citation labels and reference entries deterministically.
- `apps/api/app/services/assets/auto_report_image_service.py`: turns approved image markers into stored `ImageAsset` records and TipTap image nodes.
- `apps/api/app/services/quality/report_integrity_service.py`: validates citations, bibliography membership, image provenance, unresolved markers, and required sections.

### Existing backend units to modify

- `apps/api/app/services/agent/agentic_report_orchestrator.py`: orchestrates stages, checkpoints, persistence, retries, and terminal status.
- `apps/api/app/services/editor/writing_engine.py`: accepts section evidence packets and stable citation markers without free-form reference generation.
- `apps/api/app/services/assets/image_service.py`: exposes import-from-search-result logic reusable outside HTTP routes.
- `apps/api/app/api/v1/reports.py`: returns structured stage metadata and supports retry from the failed checkpoint through existing job endpoints.
- `apps/api/app/services/exports/docx_exporter.py`: ensures web-image captions include page source/attribution and skips unresolved internal markers.

### Frontend units to modify/create

- `apps/web/src/app/projects/new/page.tsx`: setup summary and real pipeline stages.
- `apps/web/src/lib/autoJobState.js`: normalize the new stage/checkpoint fields for persistence across refresh.
- `apps/web/src/features/editor/ResearchPanel.tsx`: show cited/unused source status and open canonical URLs.
- `apps/web/src/features/editor/TiptapEditor.tsx`: keep imported image source metadata visible and editable.
- `apps/web/src/lib/reportResearchProgress.js`: stage labels and state derivation, isolated from the page component.

### Test units

- `apps/api/tests/test_grounded_report_contracts.py`
- `apps/api/tests/test_grounded_report_research.py`
- `apps/api/tests/test_grounded_report_bibliography.py`
- `apps/api/tests/test_auto_report_images.py`
- `apps/api/tests/test_report_integrity_service.py`
- `apps/api/tests/test_e2e_autonomous_workflow.py`
- `apps/web/src/lib/__tests__/reportResearchProgress.test.mjs`
- `apps/web/src/lib/__tests__/autoJobState.test.mjs`

---

### Task 1: Versioned research and template contracts

**Files:**
- Create: `apps/api/app/services/agent/report_research_contracts.py`
- Create: `apps/api/app/services/agent/template_profile_service.py`
- Create: `apps/api/tests/test_grounded_report_contracts.py`
- Modify: `apps/api/app/services/agent/agentic_report_orchestrator.py`

**Interfaces:**
- Produces: `TemplateProfile`, `ResearchQuestion`, `ResearchPlan`, `SourceCandidate`, `ClaimEvidence`, `ImagePlanItem`, and `IntegrityResult` Pydantic models with `schema_version="1.0"`.
- Produces: `TemplateProfileService.build(parsed_context: dict, report_type: str, explicit_requirements: str) -> TemplateProfile`.
- Consumes later: all service boundaries in Tasks 2-6 use `model_dump(mode="json")` for job checkpoints.

- [ ] **Step 1: Write contract and citation-policy tests**

```python
def test_template_profile_prefers_detected_template_citation_style():
    profile = template_profile_service.build(
        {"headings": [{"text": "TÀI LIỆU THAM KHẢO"}], "full_text": "[1] A. Author, Title, 2025."},
        report_type="research",
        explicit_requirements="",
    )
    assert profile.citation_style == "ieee"
    assert "TÀI LIỆU THAM KHẢO" in profile.required_sections

def test_template_profile_uses_report_type_fallback():
    assert template_profile_service.build({}, "technical", "").citation_style == "ieee"
    assert template_profile_service.build({}, "research", "").citation_style == "apa7"
    assert template_profile_service.build({}, "business_report", "").citation_style == "numbered"
```

- [ ] **Step 2: Run the new test and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest tests/test_grounded_report_contracts.py -q`

Expected: collection fails because the new modules do not exist.

- [ ] **Step 3: Implement strict models and citation-style detection**

```python
class TemplateProfile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    headings: list[str] = Field(default_factory=list)
    required_sections: list[str] = Field(default_factory=list)
    citation_style: Literal["apa7", "ieee", "numbered"]
    presentation_rules: str = ""
    has_uploaded_template: bool = False

class ClaimEvidence(BaseModel):
    claim_id: str
    section_id: str
    planned_claim: str
    source_ids: list[str]
    supporting_excerpts: list[str]
    confidence: float = Field(ge=0, le=1)
    citation_required: bool = True
    verification_status: Literal["verified", "needs_review", "unverified"]
```

Keep models serializable, reject unknown enum values, and centralize default citation rules in `TemplateProfileService`.

- [ ] **Step 4: Store `template_profile` as a versioned checkpoint**

After `_load_template_context`, call the service and pass `{"template_profile": profile.model_dump(mode="json")}` to `update_stage`.

- [ ] **Step 5: Run tests and commit**

Run: `cd apps/api && venv/bin/python -m pytest tests/test_grounded_report_contracts.py tests/test_phase_u11_auto_report.py -q`

```bash
git add apps/api/app/services/agent/report_research_contracts.py apps/api/app/services/agent/template_profile_service.py apps/api/app/services/agent/agentic_report_orchestrator.py apps/api/tests/test_grounded_report_contracts.py
git commit -m "feat: add grounded report research contracts"
```

---

### Task 2: Research plan, source normalization, and evidence packets

**Files:**
- Create: `apps/api/app/services/agent/grounded_research_service.py`
- Create: `apps/api/tests/test_grounded_report_research.py`
- Modify: `apps/api/app/services/research/source_ranker.py`
- Modify: `apps/api/app/services/agent/agentic_report_orchestrator.py`

**Interfaces:**
- Consumes: `TemplateProfile`, report sections, project topic, `search_engine.get_search_provider()`, and current `Source` records.
- Produces: `GroundedResearchService.build_plan(topic: str, sections: list, report_type: str) -> ResearchPlan`.
- Produces: `GroundedResearchService.normalize_results(raw: list[dict], query: str) -> list[SourceCandidate]`.
- Produces: `GroundedResearchService.build_evidence_packets(sections: list, candidates: list[SourceCandidate]) -> dict[str, list[ClaimEvidence]]` keyed by section id.

- [ ] **Step 1: Write failing normalization and trust-order tests**

```python
def test_normalize_results_never_invents_missing_metadata():
    items = grounded_research_service.normalize_results([
        {"title": "Official statistic", "url": "https://gov.example/data", "snippet": "2025 result"}
    ], "2025 result")
    assert items[0].author_or_organization is None
    assert items[0].published_at is None

def test_official_and_academic_sources_rank_above_blog():
    items = grounded_research_service.normalize_results([
        {"title": "Blog", "url": "https://blog.example/post", "snippet": "same topic"},
        {"title": "Official", "url": "https://agency.gov.vn/report", "snippet": "same topic"},
    ], "same topic")
    assert items[0].canonical_url == "https://agency.gov.vn/report"
```

Add a dedupe test proving tracking parameters/fragments map to one canonical URL and a section-scoping test proving unrelated snippets are excluded from a section packet.

- [ ] **Step 2: Run RED tests**

Run: `cd apps/api && venv/bin/python -m pytest tests/test_grounded_report_research.py -q`

- [ ] **Step 3: Implement pure planning/normalization methods**

Normalize URLs by lowercasing the host, removing fragments and known tracking parameters, and preserving meaningful query parameters. Do not set placeholder authors such as `Official Author`, publisher values such as `Web Publisher`, or guessed publication years.

```python
def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", urlencode(kept), ""))
```

- [ ] **Step 4: Integrate section-aware web research**

Replace the one-query/four-result block in the orchestrator with:

1. Build `ResearchPlan` after sections exist.
2. Search each unique query with a bounded result count.
3. Normalize, dedupe, and rank all results.
4. Persist only real provider metadata to `Source`.
5. Build evidence packets and checkpoint `research_plan`, `source_candidates`, and `claim_source_ledger`.

Private document text must not enter provider queries. Use topic, section title, report type, and public requirements only.

- [ ] **Step 5: Run focused and regression tests, then commit**

Run: `cd apps/api && venv/bin/python -m pytest tests/test_grounded_report_research.py tests/test_phase1c_research_and_citations.py tests/test_phase_u6_agentic_workflow.py -q`

```bash
git add apps/api/app/services/agent/grounded_research_service.py apps/api/app/services/research/source_ranker.py apps/api/app/services/agent/agentic_report_orchestrator.py apps/api/tests/test_grounded_report_research.py
git commit -m "feat: add section-aware grounded web research"
```

---

### Task 3: Ground section drafting in verified evidence

**Files:**
- Modify: `apps/api/app/services/editor/writing_engine.py`
- Modify: `apps/api/app/services/agent/agentic_report_orchestrator.py`
- Modify: `apps/api/app/repositories/source_repo.py`
- Create: `apps/api/tests/test_grounded_section_writing.py`

**Interfaces:**
- Consumes: `evidence: list[ClaimEvidence]` and a `sources_by_id: dict[str, SourceCandidate]` scoped to one section.
- Produces: `WritingEngine.draft_grounded_section(..., evidence, citation_labels) -> dict` containing `plain_text`, `tiptap_json`, `citations_found`, and `unsupported_claims`.
- Persists: one `ClaimSource` per accepted claim/evidence link using existing models.

- [ ] **Step 1: Write failing prompt and validation tests**

```python
@pytest.mark.asyncio
async def test_grounded_draft_only_exposes_section_sources(monkeypatch):
    captured = {}
    async def fake_execute(request):
        captured["prompt"] = request.prompt
        return SimpleNamespace(text="Thị trường tăng theo số liệu chính thức [SRC:s1].")
    monkeypatch.setattr(ai_gateway, "execute", fake_execute)
    result = await writing_engine.draft_grounded_section(
        section_title="Thị trường", section_level=2, topic_name="EV",
        evidence=[verified_claim("s1")], sources_by_id={"s1": source("Official"), "s2": source("Unrelated")},
        instruction="", tone="professional", target_words=200,
    )
    assert "Official" in captured["prompt"]
    assert "Unrelated" not in captured["prompt"]
    assert result["citations_found"] == ["s1"]
```

Add tests that unknown `[SRC:missing]` markers are rejected and that a factual sentence marked unsupported makes the section `review_needed`.

- [ ] **Step 2: Run RED tests**

Run: `cd apps/api && venv/bin/python -m pytest tests/test_grounded_section_writing.py -q`

- [ ] **Step 3: Implement grounded drafting**

Use stable `[SRC:<source_id>]` markers in model output. Parse them before TipTap conversion. Keep analysis/recommendations allowed when clearly phrased as analysis, but reject specific numbers, dates, laws, rankings, or named claims without evidence.

```python
CITATION_RE = re.compile(r"\[SRC:([a-zA-Z0-9-]+)\]")

def extract_source_ids(text: str, allowed: set[str]) -> tuple[list[str], list[str]]:
    found = list(dict.fromkeys(CITATION_RE.findall(text or "")))
    return [item for item in found if item in allowed], [item for item in found if item not in allowed]
```

- [ ] **Step 4: Persist claim-source links and section status**

After a successful draft, replace stable markers with the selected citation style label, store `structured_summary_json` with source ids/unsupported claims, and create `ClaimSource` rows for verified evidence. Mark the section `review_needed` when unsupported required claims remain.

- [ ] **Step 5: Run tests and commit**

Run: `cd apps/api && venv/bin/python -m pytest tests/test_grounded_section_writing.py tests/test_editor_alignment.py tests/test_phase_u5_copilot.py -q`

```bash
git add apps/api/app/services/editor/writing_engine.py apps/api/app/services/agent/agentic_report_orchestrator.py apps/api/app/repositories/source_repo.py apps/api/tests/test_grounded_section_writing.py
git commit -m "feat: ground report sections in verified sources"
```

---

### Task 4: Deterministic citations and bibliography

**Files:**
- Create: `apps/api/app/services/citations/bibliography_service.py`
- Create: `apps/api/tests/test_grounded_report_bibliography.py`
- Modify: `apps/api/app/services/agent/agentic_report_orchestrator.py`
- Modify: `apps/api/app/services/editor/writing_engine.py`

**Interfaces:**
- Consumes: `style: Literal["apa7", "ieee", "numbered"]`, ordered cited source ids, and persisted `Source` records.
- Produces: `BibliographyService.inline_label(source, position, style) -> str`.
- Produces: `BibliographyService.render_entry(source, position, style, accessed_at) -> str`.
- Produces: `BibliographyService.build(cited_source_ids, sources_by_id, style) -> BibliographyResult`.

- [ ] **Step 1: Write failing reference membership and missing-metadata tests**

```python
def test_bibliography_contains_only_cited_sources():
    result = bibliography_service.build(["s2"], {"s1": source("Unused"), "s2": source("Used")}, "apa7")
    assert "Used" in result.plain_text
    assert "Unused" not in result.plain_text

def test_missing_author_and_date_are_not_invented():
    entry = bibliography_service.render_entry(source("Policy", authors=None, published_date=None), 1, "apa7", date(2026, 9, 16))
    assert "Official Author" not in entry
    assert "2024" not in entry
    assert "n.d." in entry
```

Add APA 7, IEEE, numbered, stable ordering, URL, and dedupe coverage.

- [ ] **Step 2: Run RED tests**

Run: `cd apps/api && venv/bin/python -m pytest tests/test_grounded_report_bibliography.py -q`

- [ ] **Step 3: Implement deterministic formatters**

Keep formatting logic pure. Escape only at the export/render boundary. Use the real source fields and the job access date; never ask the language model to compose entries.

- [ ] **Step 4: Replace orchestrator's free-form reference section**

Collect source ids actually present in completed section metadata. Build or update one `TÀI LIỆU THAM KHẢO` section using `BibliographyResult`, preserving the template's section title when it differs. Ensure a missing reference section is appended after the conclusion using the template's closest heading level.

- [ ] **Step 5: Run tests and commit**

Run: `cd apps/api && venv/bin/python -m pytest tests/test_grounded_report_bibliography.py tests/test_phase1c_research_and_citations.py tests/test_docx_exporter_layout.py -q`

```bash
git add apps/api/app/services/citations/bibliography_service.py apps/api/app/services/agent/agentic_report_orchestrator.py apps/api/app/services/editor/writing_engine.py apps/api/tests/test_grounded_report_bibliography.py
git commit -m "feat: build references from cited sources"
```

---

### Task 5: Automatic web-image discovery and insertion

**Files:**
- Create: `apps/api/app/services/assets/auto_report_image_service.py`
- Create: `apps/api/tests/test_auto_report_images.py`
- Modify: `apps/api/app/services/assets/image_service.py`
- Modify: `apps/api/app/services/agent/agentic_report_orchestrator.py`
- Modify: `apps/api/app/services/exports/docx_exporter.py`

**Interfaces:**
- Consumes: section id/title/plain text/content JSON, report/project/user ids, and `ImagePlanItem`.
- Produces: `AutoReportImageService.plan(sections, topic) -> list[ImagePlanItem]`.
- Produces: `AutoReportImageService.import_and_insert(db, item, project_id, report_id, user_id) -> ImageInsertionResult`.
- Reuses: `ImageService.search_web_images`, `download_remote_image`, `create_asset`, and existing SSRF/MIME/size checks.

- [ ] **Step 1: Write failing plan/import/TipTap tests**

```python
@pytest.mark.asyncio
async def test_imported_web_image_becomes_stored_tiptap_node(db, monkeypatch, report_section):
    monkeypatch.setattr(image_service, "search_web_images", fake_relevant_results)
    monkeypatch.setattr(image_service, "download_remote_image", fake_png_download)
    result = await auto_report_image_service.import_and_insert(
        db, image_plan(section_id=report_section.id), project_id=report_section.report.project_id,
        report_id=report_section.report_id, user_id=report_section.report.project.user_id,
    )
    assert result.asset.source_type == "web"
    assert result.asset.source_page_url == "https://source.example/article"
    assert any(node["type"] == "image" for node in result.content_json["content"])
```

Add tests for irrelevant/no results, failed first candidate with successful fallback, duplicate checksum, and source caption export.

- [ ] **Step 2: Run RED tests**

Run: `cd apps/api && venv/bin/python -m pytest tests/test_auto_report_images.py -q`

- [ ] **Step 3: Extract reusable image import helper**

Add `ImageService.import_search_result(...) -> ImageAsset` so both `/assets/images/import-web` and the automatic pipeline use identical validation and provenance. The route becomes a thin adapter.

- [ ] **Step 4: Implement conservative planning and insertion**

Create at most one image plan per important top-level content section, skip front matter/references, and cap the report at a length-aware maximum. Choose a result only when its title/source metadata overlaps the query terms. Append this TipTap node after the first substantive paragraph:

```python
{
    "type": "image",
    "attrs": {
        "assetId": asset.id,
        "src": f"/api/v1/assets/images/{asset.id}/content",
        "alt": item.alt_text,
        "caption": item.caption,
        "sourceType": "web",
        "sourceName": asset.source_domain,
        "sourceUrl": asset.source_page_url,
        "license": asset.license,
        "attribution": asset.attribution,
        "width": min(asset.width or 520, 620),
        "alignment": "center",
    },
}
```

- [ ] **Step 5: Add orchestrator stage and export provenance**

Checkpoint `image_plan`, imported asset ids, per-item warnings, and stage progress. Include source page domain and attribution in DOCX captions; do not fail the report when no relevant image is available.

- [ ] **Step 6: Run tests and commit**

Run: `cd apps/api && venv/bin/python -m pytest tests/test_auto_report_images.py tests/test_phase1d_editor_and_export.py tests/test_docx_exporter_layout.py -q`

```bash
git add apps/api/app/services/assets/auto_report_image_service.py apps/api/app/services/assets/image_service.py apps/api/app/services/agent/agentic_report_orchestrator.py apps/api/app/services/exports/docx_exporter.py apps/api/tests/test_auto_report_images.py
git commit -m "feat: insert sourced web images into reports"
```

---

### Task 6: Final integrity gate and resumable checkpoints

**Files:**
- Create: `apps/api/app/services/quality/report_integrity_service.py`
- Create: `apps/api/tests/test_report_integrity_service.py`
- Modify: `apps/api/app/services/agent/agentic_report_orchestrator.py`
- Modify: `apps/api/app/api/v1/reports.py`
- Modify: `apps/api/tests/test_e2e_autonomous_workflow.py`

**Interfaces:**
- Consumes: report sections, cited sources, image assets, `TemplateProfile`, and job checkpoint metadata.
- Produces: `ReportIntegrityService.validate(...) -> IntegrityResult` with `blocking_errors`, `warnings`, and counts.
- Produces: `resume_stage(metadata: dict) -> str` for the first incomplete/failed stage.

- [ ] **Step 1: Write failing integrity tests**

```python
def test_integrity_blocks_fake_or_dangling_citations():
    result = report_integrity_service.validate(
        sections=[section("Claim [SRC:missing]")], sources=[], images=[], template_profile=profile()
    )
    assert result.ready is False
    assert "dangling_citation" in {item.code for item in result.blocking_errors}

def test_integrity_warns_but_does_not_block_when_optional_image_is_missing():
    result = report_integrity_service.validate(
        sections=[grounded_section()], sources=[source("s1")], images=[], template_profile=profile()
    )
    assert result.ready is True
    assert "no_relevant_image" in {item.code for item in result.warnings}
```

Cover unresolved `[[IMAGE]]`, uncited bibliography entries, missing required sections, missing image source URLs, and valid reports.

- [ ] **Step 2: Run RED tests**

Run: `cd apps/api && venv/bin/python -m pytest tests/test_report_integrity_service.py -q`

- [ ] **Step 3: Implement pure integrity checks and checkpoint selection**

Store stage completion under `metadata_json["pipeline"][stage]` with `status`, `started_at`, `completed_at`, `warnings`, and schema-versioned output. Resume skips only stages whose input fingerprint still matches.

- [ ] **Step 4: Integrate terminal status**

Use `completed` only when `IntegrityResult.ready` is true. Use existing `review_needed` for blocking evidence/reference failures and expose `integrity_result` in the job response. Retry begins from the earliest failed or invalidated checkpoint without duplicating sources or images.

- [ ] **Step 5: Add an end-to-end grounded workflow test**

Mock search and image downloads, run `_run_workflow_with_session`, then assert:

```python
assert job.status == "completed"
assert job.metadata_json["integrity_result"]["ready"] is True
assert bibliography_source_ids == cited_source_ids
assert all(asset.source_page_url for asset in report.image_assets)
assert not unresolved_markers(report.sections)
```

- [ ] **Step 6: Run tests and commit**

Run: `cd apps/api && venv/bin/python -m pytest tests/test_report_integrity_service.py tests/test_e2e_autonomous_workflow.py tests/test_phase_u11_auto_report.py -q`

```bash
git add apps/api/app/services/quality/report_integrity_service.py apps/api/app/services/agent/agentic_report_orchestrator.py apps/api/app/api/v1/reports.py apps/api/tests/test_report_integrity_service.py apps/api/tests/test_e2e_autonomous_workflow.py
git commit -m "feat: verify and resume autonomous report jobs"
```

---

### Task 7: Product UI for automatic research stages and source review

**Files:**
- Create: `apps/web/src/lib/reportResearchProgress.js`
- Create: `apps/web/src/lib/__tests__/reportResearchProgress.test.mjs`
- Modify: `apps/web/src/lib/autoJobState.js`
- Modify: `apps/web/src/lib/__tests__/autoJobState.test.mjs`
- Modify: `apps/web/src/app/projects/new/page.tsx`
- Modify: `apps/web/src/features/editor/ResearchPanel.tsx`
- Modify: `apps/web/src/features/editor/TiptapEditor.tsx`

**Interfaces:**
- Consumes: job `current_stage`, `timeline`, `pipeline`, `integrity_result`, source records, and image attrs from previous tasks.
- Produces: `buildReportResearchStages(job, locale) -> Array<{id,label,status,message,warnings}>`.
- Produces: `summarizeReportSetup({hasTemplate, reportType, webResearch, webImages}, locale)`.

- [ ] **Step 1: Write failing stage-mapping tests**

```javascript
test("maps backend checkpoints to the eight user-facing stages", () => {
  const stages = buildReportResearchStages({
    current_stage: "image_research",
    pipeline: { template_profile: { status: "completed" }, research: { status: "completed" } },
  }, "vi");
  assert.equal(stages.length, 8);
  assert.equal(stages.find((item) => item.id === "images").status, "running");
  assert.equal(stages.find((item) => item.id === "research").status, "completed");
});
```

Add refresh persistence and `review_needed` warning mapping tests.

- [ ] **Step 2: Run RED tests**

Run: `cd apps/web && node --test src/lib/__tests__/reportResearchProgress.test.mjs src/lib/__tests__/autoJobState.test.mjs`

- [ ] **Step 3: Implement pure frontend helpers**

Keep localized labels and backend-stage aliases outside `page.tsx`. Treat unknown stages as pending and preserve raw messages for diagnostics.

- [ ] **Step 4: Upgrade the create/report progress UI**

Before start, show compact status chips for template, citation rule, web research, and web images. During execution, render the eight real stages with success/running/warning states, source count, image count, and an explicit `needs review` card when integrity blocks completion. Retain pause, resume, cancel, and retry actions.

- [ ] **Step 5: Upgrade Studio source and image provenance surfaces**

In `ResearchPanel`, show **Đã trích dẫn** and **Chưa sử dụng** filters, canonical source links, publisher/date when present, and no fabricated fallback labels. In the TipTap image inspector/panel, show page source, attribution, and license metadata already stored on the image node.

- [ ] **Step 6: Run frontend checks and commit**

Run:

```bash
cd apps/web
node --test src/lib/__tests__/reportResearchProgress.test.mjs src/lib/__tests__/autoJobState.test.mjs
npm run typecheck
npm run lint -- --quiet
```

```bash
git add apps/web/src/lib/reportResearchProgress.js apps/web/src/lib/__tests__/reportResearchProgress.test.mjs apps/web/src/lib/autoJobState.js apps/web/src/lib/__tests__/autoJobState.test.mjs apps/web/src/app/projects/new/page.tsx apps/web/src/features/editor/ResearchPanel.tsx apps/web/src/features/editor/TiptapEditor.tsx
git commit -m "feat: show grounded report research progress"
```

---

### Task 8: Full verification, build, and runtime smoke test

**Files:**
- Modify only if verification reveals a defect in files already listed above.

**Interfaces:**
- Consumes: completed Tasks 1-7.
- Produces: a clean branch with passing backend/frontend suites and a locally verified automatic report flow.

- [ ] **Step 1: Run the full backend suite**

Run: `cd apps/api && venv/bin/python -m pytest tests -q`

Expected: all non-environment tests pass; existing explicitly skipped integration tests remain skipped.

- [ ] **Step 2: Run the full frontend suite and production build**

Run:

```bash
cd apps/web
npm test
npm run typecheck
npm run lint -- --quiet
npm run build
```

Expected: tests, TypeScript, lint, and the Next.js production build pass.

- [ ] **Step 3: Run diff hygiene checks**

Run:

```bash
git diff --check
git status --short
```

Restore the known Next.js-generated `apps/web/next-env.d.ts` dev-path change if it appears and is unrelated to the feature.

- [ ] **Step 4: Start the isolated local runtime and smoke test**

Run the existing `scripts/dev.sh` against a copied temporary SQLite database. Verify:

1. A topic-only report reaches all eight stages.
2. A DOCX-template report preserves headings and citation style.
3. The completed Studio shows live source links and stored images.
4. Exported DOCX contains images, captions, inline citations, and a matching bibliography.
5. A deliberately missing source causes `review_needed`, not a false `completed` state.
