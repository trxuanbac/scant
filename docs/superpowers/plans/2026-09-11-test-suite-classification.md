# Deterministic Test Suite Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the default backend test command deterministic and offline by defining the repository test taxonomy, blocking unexpected network access, and moving provider-dependent checks behind an explicit live-test switch.

**Architecture:** Pytest owns the policy at the `apps/api` root. A small test-support module installs an outbound Python socket guard, root `conftest.py` skips tests marked `live` unless `--run-live` is supplied, and `pytest.ini` registers all four marker classes. Phase 0A classifies existing provider-dependent functions with `live`; the remaining unit/integration/browser classification is completed as those layers receive their dedicated fixtures and harnesses.

**Tech Stack:** Python 3.14, pytest 9, pytest-asyncio, socket standard library, FastAPI integration tests.

**Spec:** `docs/superpowers/specs/2026-09-11-existing-function-completion-program-design.md` — Phase 0A only.

## Global Constraints

- Do not change product runtime behavior in Phase 0A.
- The default suite must not require Internet, production AI keys, payment credentials, or a running PostgreSQL service.
- Live tests run only with the explicit `--run-live` option.
- In-process FastAPI tests using `ASGITransport` are integration tests, not browser E2E tests.
- Mark only the provider-dependent functions in mixed test modules; keep deterministic functions active.
- Unexpected TCP, DNS, or UDP access through Python sockets in a non-live test must fail with the destination in the error message. Container-level egress enforcement belongs to Phase 0D.
- Preserve all pre-existing working-tree changes and stage only Phase 0A hunks.
- Do not restore retired runtime features to make legacy tests pass.

---

### Task 1: Pytest Taxonomy and Offline Network Guard

**Files:**
- Create: `apps/api/pytest.ini`
- Create: `apps/api/tests/support/__init__.py`
- Create: `apps/api/tests/support/network_guard.py`
- Create: `apps/api/tests/conftest.py`
- Create: `apps/api/tests/test_suite_policy.py`

**Interfaces:**
- Produces: `--run-live` pytest option.
- Produces: markers `unit`, `integration`, `browser`, and `live`.
- Produces: `NetworkAccessBlocked(RuntimeError)`.
- Produces: `install_network_guard(monkeypatch) -> None`.
- Default behavior: tests marked `live` are skipped and every other test rejects TCP/DNS/UDP access through Python sockets.

- [ ] **Step 1: Write the policy tests before the support module exists**

Create `apps/api/tests/test_suite_policy.py`:

```python
import socket

import pytest

from support.network_guard import NetworkAccessBlocked


@pytest.mark.unit
def test_test_taxonomy_is_registered(pytestconfig):
    registered = "\n".join(pytestconfig.getini("markers"))
    for marker in ("unit", "integration", "browser", "live"):
        assert f"{marker}:" in registered
    assert isinstance(pytestconfig.getoption("--run-live"), bool)


@pytest.mark.unit
def test_default_suite_blocks_dns_access():
    with pytest.raises(NetworkAccessBlocked, match="example.com"):
        socket.getaddrinfo("example.com", 443)


@pytest.mark.unit
def test_default_suite_blocks_tcp_access():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(NetworkAccessBlocked, match="93.184.216.34:443"):
            sock.connect(("93.184.216.34", 443))
    finally:
        sock.close()


@pytest.mark.unit
def test_default_suite_blocks_udp_access():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(NetworkAccessBlocked, match="127.0.0.1:9"):
            sock.sendto(b"blocked", ("127.0.0.1", 9))
    finally:
        sock.close()


@pytest.mark.live
def test_live_marker_sentinel():
    assert True
```

- [ ] **Step 2: Run the policy test and confirm collection fails**

Run:

```bash
cd apps/api
venv/bin/python -m pytest tests/test_suite_policy.py -q
```

Expected: FAIL during import because `support.network_guard` and the marker policy do not exist.

- [ ] **Step 3: Add the marker configuration**

Create `apps/api/pytest.ini`:

```ini
[pytest]
testpaths = tests
asyncio_mode = strict
markers =
    unit: pure deterministic test without database, filesystem, process, or network dependencies
    integration: deterministic test crossing application boundaries with isolated local dependencies
    browser: end-to-end browser test against running application processes
    live: opt-in test requiring network access, a configured provider, or an external service
```

Create an empty `apps/api/tests/support/__init__.py`.

- [ ] **Step 4: Implement the reusable socket guard**

Create `apps/api/tests/support/network_guard.py`:

```python
import socket
from typing import Any


class NetworkAccessBlocked(RuntimeError):
    """Raised when a deterministic test attempts external network access."""


def _destination(address: Any) -> str:
    if isinstance(address, tuple) and len(address) >= 2:
        return f"{address[0]}:{address[1]}"
    return str(address)


def install_network_guard(monkeypatch) -> None:
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_sendto = socket.socket.sendto
    unix_family = getattr(socket, "AF_UNIX", None)

    def guarded_connect(sock, address):
        if unix_family is not None and sock.family == unix_family:
            return original_connect(sock, address)
        raise NetworkAccessBlocked(
            f"Outbound network is disabled in deterministic tests: {_destination(address)}"
        )

    def guarded_connect_ex(sock, address):
        if unix_family is not None and sock.family == unix_family:
            return original_connect_ex(sock, address)
        raise NetworkAccessBlocked(
            f"Outbound network is disabled in deterministic tests: {_destination(address)}"
        )

    def guarded_sendto(sock, data, *args):
        address = args[-1] if args else "<unknown>"
        if unix_family is not None and sock.family == unix_family:
            return original_sendto(sock, data, *args)
        raise NetworkAccessBlocked(
            f"Outbound network is disabled in deterministic tests: {_destination(address)}"
        )

    def guarded_getaddrinfo(host, port, *args, **kwargs):
        raise NetworkAccessBlocked(
            f"Outbound DNS is disabled in deterministic tests: {host}:{port}"
        )

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", guarded_sendto)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
```

- [ ] **Step 5: Install the policy through root conftest**

Create `apps/api/tests/conftest.py`:

```python
import pytest

from support.network_guard import install_network_guard


def pytest_addoption(parser):
    group = parser.getgroup("scant-live")
    group.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run tests that require external network or configured services",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skipped = pytest.mark.skip(
        reason="live test disabled; rerun with --run-live and required services configured"
    )
    for item in items:
        if item.get_closest_marker("live") is not None:
            item.add_marker(skipped)


@pytest.fixture(autouse=True)
def block_network_in_deterministic_tests(request, monkeypatch):
    is_live = request.node.get_closest_marker("live") is not None
    if is_live and request.config.getoption("--run-live"):
        return
    install_network_guard(monkeypatch)
```

- [ ] **Step 6: Run the policy tests in default and explicit-live modes**

Run:

```bash
cd apps/api
venv/bin/python -m pytest tests/test_suite_policy.py -q
venv/bin/python -m pytest tests/test_suite_policy.py --run-live -q
venv/bin/python -m pytest tests/test_suite_policy.py::test_live_marker_sentinel --run-live -q
```

Expected: the default command reports four passed and one skipped; the full `--run-live` command reports five passed, proving deterministic tests remain guarded; the sentinel command reports one passed.

- [ ] **Step 7: Commit the policy foundation**

```bash
git add apps/api/pytest.ini apps/api/tests/conftest.py apps/api/tests/support/__init__.py apps/api/tests/support/network_guard.py apps/api/tests/test_suite_policy.py
git commit -m "test: make backend suite offline by default"
```

---

### Task 2: Classify Live Research and Source Checks

**Files:**
- Modify: `apps/api/tests/test_deep_research_pipeline.py`
- Modify: `apps/api/tests/test_phase1c_research_and_citations.py`
- Modify: `apps/api/tests/test_source_library_and_citations.py`

**Interfaces:**
- Consumes: registered `pytest.mark.live` policy from Task 1.
- Produces: opt-in classification for tests that call Crossref, arXiv, search providers, DOI resolution, or live web fetches.

- [ ] **Step 1: Run the three modules under the offline guard**

Run:

```bash
cd apps/api
venv/bin/python -m pytest tests/test_deep_research_pipeline.py tests/test_phase1c_research_and_citations.py tests/test_source_library_and_citations.py -q
```

Expected: FAIL with `NetworkAccessBlocked` or existing empty-provider assertions in the live functions, while pure scoring, evidence, and citation tests pass.

- [ ] **Step 2: Mark only direct provider functions live**

Add `@pytest.mark.live` immediately above the existing `@pytest.mark.asyncio` decorator on these functions:

```text
test_deep_research_pipeline.py
  test_crossref_live_search
  test_arxiv_live_search
  test_end_to_end_deep_research_pipeline_vietnam_ev_2026

test_phase1c_research_and_citations.py
  test_search_and_ranking
  test_research_api_flow

test_source_library_and_citations.py
  test_multi_provider_search_anti_hallucination
  test_source_verification_scoring
  test_sources_api_e2e
```

Do not mark deterministic quality scoring, deduplication, evidence extraction, support evaluation, or citation formatting tests.

- [ ] **Step 3: Verify deterministic research tests and live collection**

Run:

```bash
cd apps/api
venv/bin/python -m pytest tests/test_deep_research_pipeline.py tests/test_phase1c_research_and_citations.py tests/test_source_library_and_citations.py -q
venv/bin/python -m pytest tests/test_deep_research_pipeline.py tests/test_phase1c_research_and_citations.py tests/test_source_library_and_citations.py --run-live -m live --collect-only -q
```

Expected: the default command passes with eight live skips; the collection command lists exactly eight live tests.

- [ ] **Step 4: Commit research classification**

```bash
git add apps/api/tests/test_deep_research_pipeline.py apps/api/tests/test_phase1c_research_and_citations.py apps/api/tests/test_source_library_and_citations.py
git commit -m "test: classify live research checks"
```

---

### Task 3: Classify Live AI, Payment, and Service Checks

**Files:**
- Modify: `apps/api/tests/test_e2e_autonomous_workflow.py`
- Modify: `apps/api/tests/test_phase1b_parsers_and_outline.py`
- Modify: `apps/api/tests/test_phase_u10_document_transformation.py`
- Modify: `apps/api/tests/test_phase_u11_auto_report.py`
- Modify: `apps/api/tests/test_phase_u12_document_agent.py`
- Modify: `apps/api/tests/test_phase_u27_5_production_reality_audit.py`
- Modify: `apps/api/tests/test_phase_u28_document_intelligence.py`
- Modify: `apps/api/tests/test_phase_u2_intent_and_wizard.py`
- Modify: `apps/api/tests/test_phase_u30_spreadsheet_agent.py`
- Modify: `apps/api/tests/test_phase_u32_diagram_agent.py`
- Modify: `apps/api/tests/test_phase_u3_template_reverse_engineer.py`
- Modify: `apps/api/tests/test_phase_u5_copilot.py`
- Modify: `apps/api/tests/test_phase_u8_fact_inspector.py`
- Modify: `apps/api/tests/test_superpower_upgrades.py`

**Interfaces:**
- Consumes: registered `pytest.mark.live` policy from Task 1.
- Produces: opt-in classification for tests that use a configured AI/payment provider or a real PostgreSQL service.

- [ ] **Step 1: Mark the known external-service functions**

Add `@pytest.mark.live` immediately above the existing `@pytest.mark.asyncio` decorator on these functions:

```text
test_e2e_autonomous_workflow.py
  test_full_autonomous_workspace_e2e_workflow

test_phase1b_parsers_and_outline.py
  test_full_phase1b_outline_and_report_flow

test_phase_u10_document_transformation.py
  test_document_transformation_unit
  test_transform_document_api

test_phase_u11_auto_report.py
  test_one_click_auto_create_flow
  test_auto_create_accepts_dataset_link_sheet_range_and_analysis_request
  test_agentic_background_workflow_completes_with_sections

test_phase_u12_document_agent.py
  test_agent_execute_turn_api

test_phase_u27_5_production_reality_audit.py
  test_audit_1_real_postgresql_integration
  test_audit_6_concurrency_and_latency_benchmark
  test_audit_7_failure_recovery_and_fallback

test_phase_u28_document_intelligence.py
  test_visual_query_reasoning

test_phase_u2_intent_and_wizard.py
  test_ai_analyze_intent_flow

test_phase_u30_spreadsheet_agent.py
  test_spreadsheet_agent_narrative

test_phase_u32_diagram_agent.py
  test_diagram_generation_flowchart
  test_diagram_generation_erd
  test_diagram_generation_sequence

test_phase_u3_template_reverse_engineer.py
  test_reverse_engineer_docx
  test_reverse_engineer_api

test_phase_u5_copilot.py
  test_copilot_chat_flow

test_phase_u8_fact_inspector.py
  test_fact_inspector_unit
  test_fact_inspect_api

test_superpower_upgrades.py
  test_vietqr_billing_generation
  test_mermaid_diagram_agent
```

The PostgreSQL audit is live because it requires a separately running service. The two `test_superpower_upgrades.py` marker hunks must be staged without including unrelated pre-existing changes in that file.

- [ ] **Step 2: Run the affected modules under the default policy**

Run:

```bash
cd apps/api
venv/bin/python -m pytest \
  tests/test_e2e_autonomous_workflow.py \
  tests/test_phase1b_parsers_and_outline.py \
  tests/test_phase_u10_document_transformation.py \
  tests/test_phase_u11_auto_report.py \
  tests/test_phase_u12_document_agent.py \
  tests/test_phase_u27_5_production_reality_audit.py \
  tests/test_phase_u28_document_intelligence.py \
  tests/test_phase_u2_intent_and_wizard.py \
  tests/test_phase_u30_spreadsheet_agent.py \
  tests/test_phase_u32_diagram_agent.py \
  tests/test_phase_u3_template_reverse_engineer.py \
  tests/test_phase_u5_copilot.py \
  tests/test_phase_u8_fact_inspector.py \
  tests/test_superpower_upgrades.py -q
```

Expected: deterministic functions pass and the 24 listed service-dependent functions skip.

- [ ] **Step 3: Verify live tests remain discoverable**

Run:

```bash
cd apps/api
venv/bin/python -m pytest --run-live -m live --collect-only -q
```

Expected: collection includes the eight research tests from Task 2, the 24 service tests from this task, and the policy sentinel: 33 known live tests before the Task 4 leak audit. Any additional legitimate classifications increase this count. No live test executes during collection.

- [ ] **Step 4: Commit service classification**

Stage only the marker changes and clean files, inspect `git diff --cached`, then commit:

```bash
git add \
  apps/api/tests/test_e2e_autonomous_workflow.py \
  apps/api/tests/test_phase1b_parsers_and_outline.py \
  apps/api/tests/test_phase_u10_document_transformation.py \
  apps/api/tests/test_phase_u11_auto_report.py \
  apps/api/tests/test_phase_u12_document_agent.py \
  apps/api/tests/test_phase_u27_5_production_reality_audit.py \
  apps/api/tests/test_phase_u28_document_intelligence.py \
  apps/api/tests/test_phase_u2_intent_and_wizard.py \
  apps/api/tests/test_phase_u30_spreadsheet_agent.py \
  apps/api/tests/test_phase_u32_diagram_agent.py \
  apps/api/tests/test_phase_u3_template_reverse_engineer.py \
  apps/api/tests/test_phase_u5_copilot.py \
  apps/api/tests/test_phase_u8_fact_inspector.py
git add -p apps/api/tests/test_superpower_upgrades.py
git diff --cached --check
git commit -m "test: classify provider-dependent checks"
```

---

### Task 4: Close Remaining Offline-Suite Leaks

**Files:**
- Modify: only test files identified by the full offline run.
- Test: `apps/api/tests/test_suite_policy.py`

**Interfaces:**
- Consumes: network guard and live taxonomy.
- Produces: a full default backend suite whose Python TCP/DNS/UDP attempts are rejected by the test guard.

- [ ] **Step 1: Run the full backend suite with fail-fast disabled**

Run:

```bash
cd apps/api
venv/bin/python -m pytest -q
```

Expected before final classification: any missed provider-dependent Python socket attempt fails with `NetworkAccessBlocked` before it reaches the requested destination.

- [ ] **Step 2: Classify each remaining failure by behavior**

For every remaining failure:

- If the test explicitly promises a real provider, public URL, configured payment system, or running service, add `@pytest.mark.live` to that function.
- If it intends to test local behavior, replace the network boundary with `httpx.MockTransport`, a provider fake, or an existing monkeypatch in that test; keep it unmarked.
- If it fails for a product regression unrelated to network, leave it unmarked and fix or report the regression rather than hiding it as live.

Do not mark an entire mixed module live to silence one function.

- [ ] **Step 3: Re-run each adjusted module**

Repeat the tests that failed in the immediately preceding run:

```bash
cd apps/api
venv/bin/python -m pytest --lf -q
```

Expected: deterministic corrected tests pass; newly classified live tests skip with the documented reason.

- [ ] **Step 4: Run the full default suite again**

Run:

```bash
cd apps/api
venv/bin/python -m pytest -q
```

Expected: PASS with live tests reported as skipped and no `NetworkAccessBlocked` failure.

- [ ] **Step 5: Commit only the leak closures**

Inspect every staged hunk, then commit:

```bash
git add -p apps/api/tests
git diff --cached --check
git commit -m "test: close deterministic suite network leaks"
```

---

### Task 5: Document and Verify the Phase 0A Contract

**Files:**
- Create: `apps/api/TESTING.md`
- Modify: `docs/superpowers/plans/2026-09-11-test-suite-classification.md` (check completed steps only after evidence exists)

**Interfaces:**
- Consumes: `--run-live`, marker taxonomy, and network guard.
- Produces: exact contributor commands for deterministic and live test execution.

- [ ] **Step 1: Write the testing guide**

Create `apps/api/TESTING.md` with these commands and rules:

````markdown
# Backend testing

The default suite is deterministic and rejects outbound TCP, DNS, and UDP access through Python sockets:

```bash
cd apps/api
venv/bin/python -m pytest -q
```

Run only live checks after configuring their required providers and services:

```bash
cd apps/api
venv/bin/python -m pytest --run-live -m live -q
```

Test classes:

- `unit`: pure deterministic logic.
- `integration`: deterministic application boundaries with isolated local dependencies.
- `browser`: browser tests against running SCANT processes.
- `live`: public network, configured provider, payment sandbox, or separately running service.

New tests are deterministic by default. A live marker must describe the real dependency in the test name or docstring. Do not use `live` to hide a product regression.

The socket guard catches application-level Python clients. Phase 0D also blocks container egress in CI so subprocesses and native libraries cannot bypass this policy.
````

- [ ] **Step 2: Verify marker registration and collection**

Run:

```bash
cd apps/api
venv/bin/python -m pytest --markers
venv/bin/python -m pytest --run-live -m live --collect-only -q
```

Expected: all four marker descriptions appear and every classified live test is collected.

- [ ] **Step 3: Run Phase 0A verification**

Run:

```bash
cd apps/api
venv/bin/python -m pytest -q
venv/bin/python -m pytest tests/test_suite_policy.py -q
cd ../web
npm test
npm run typecheck
npm run lint
npm run build
cd ../..
git diff --check
```

Expected: default backend and all frontend commands pass; lint may report existing warnings but no errors; live tests are skipped, not executed.

- [ ] **Step 4: Record exact results in the testing guide**

Append a dated `Current verification` section to `apps/api/TESTING.md` containing the exact backend passed/skipped counts, frontend test count, and typecheck/lint/build status from Step 3. Do not call skipped live tests passing tests.

- [ ] **Step 5: Commit documentation and final plan state**

```bash
git add apps/api/TESTING.md docs/superpowers/plans/2026-09-11-test-suite-classification.md
git commit -m "docs: record deterministic test workflow"
```
