# CI Release Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal GitHub Actions gate that reproduces the verified deterministic backend, frontend, migration, and secret checks on every push and pull request.

**Architecture:** One read-only workflow runs four independent jobs: repository policy, backend tests without external networking, frontend tests/build without external networking, and SQLite/PostgreSQL migration validation. Dependency installation happens before network isolation; retained test and build commands run through a Linux network namespace with only loopback enabled, while the migration job can reach only its local PostgreSQL service. Repository tests inspect the workflow and isolation wrapper so accidental removal of a release gate fails the normal backend suite.

**Tech Stack:** GitHub Actions, Ubuntu, Python 3.14, Node.js 24, Bash, Linux `unshare`, PostgreSQL 16, pytest, npm, Alembic.

**Spec:** `docs/superpowers/specs/2026-09-11-existing-function-completion-program-design.md` — Phase 0D.

## Global Constraints

- CI runs on `push` and `pull_request`; it never uses `pull_request_target`.
- Workflow permissions are `contents: read` and no job receives application secrets.
- Live public-provider tests remain opt-in and are not part of the deterministic backend job.
- Dependency installation may use the network; test, lint, typecheck, and build commands run after network isolation.
- PostgreSQL validation creates and removes uniquely named schemas inside the CI-only service database.
- Preserve the existing working-tree product changes and stage only Phase 0D files or hunks.

---

### Task 1: Executable CI contract and network isolation wrapper

**Files:**

- Create: `apps/api/tests/test_ci_release_policy.py`
- Create: `scripts/run-without-network.sh`

**Interfaces:**

- Produces: `scripts/run-without-network.sh <command> [args...]`, which requires Linux `unshare` when `SCANT_REQUIRE_NETWORK_NAMESPACE=1`, enables loopback inside a fresh network namespace, and executes the supplied command without external interfaces.
- The wrapper runs the command directly on non-Linux developer machines unless strict CI mode is enabled.
- The first policy test covers the wrapper. Task 2 extends the same file with workflow checks without adding a YAML dependency.

- [x] **Step 1: Write the failing CI policy tests**

```python
def test_offline_wrapper_uses_a_required_linux_network_namespace():
    wrapper = (ROOT / "scripts/run-without-network.sh").read_text()
    assert "unshare --net" in wrapper
    assert "ip link set lo up" in wrapper
    assert "SCANT_REQUIRE_NETWORK_NAMESPACE" in wrapper
```

- [x] **Step 2: Run the policy tests and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_ci_release_policy.py`

Expected: failure because the isolation wrapper does not exist.

- [x] **Step 3: Implement the network isolation wrapper**

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: run-without-network.sh <command> [args...]" >&2
  exit 2
fi

if [ "$(uname -s)" != "Linux" ]; then
  if [ "${SCANT_REQUIRE_NETWORK_NAMESPACE:-0}" = "1" ]; then
    echo "strict network isolation requires Linux" >&2
    exit 1
  fi
  exec "$@"
fi

if [ "${SCANT_INSIDE_NETWORK_NAMESPACE:-0}" = "1" ]; then
  ip link set lo up
  exec "$@"
fi

exec sudo --preserve-env=PATH unshare --net env \
  SCANT_INSIDE_NETWORK_NAMESPACE=1 "$0" "$@"
```

- [x] **Step 4: Verify wrapper fallback and strict argument handling**

Run: `bash scripts/run-without-network.sh bash -c 'test 4 -eq 4'`

Run: `bash scripts/run-without-network.sh`

Expected: the first command exits 0; the second exits 2 and prints only usage text.

- [x] **Step 5: Commit the executable contract**

```bash
git add apps/api/tests/test_ci_release_policy.py scripts/run-without-network.sh
git commit -m "test: define CI release contract"
```

### Task 2: GitHub Actions release workflow

**Files:**

- Create: `.github/workflows/ci.yml`
- Modify: `apps/api/tests/test_ci_release_policy.py`

**Interfaces:**

- `policy` runs the tracked-file secret scanner and the CI contract tests.
- `backend` installs `apps/api/requirements.txt`, then runs `python -m pytest -q` through the strict network wrapper with deterministic runtime settings.
- `frontend` runs `npm ci`, then test, typecheck, lint, and production build through the strict network wrapper.
- `migrations` starts PostgreSQL 16, runs the 25-test SQLite migration gate, runs the two PostgreSQL migration tests with `--run-live`, and runs `alembic heads`, `history`, and `check` against a migrated temporary SQLite database.

- [x] **Step 1: Extend the policy test with the complete workflow contract**

```python
def test_ci_runs_every_release_gate_without_application_secrets():
    workflow = workflow_text()
    for command in (
        "bash scripts/check-secrets.sh",
        "scripts/run-without-network.sh python -m pytest -q",
        "scripts/run-without-network.sh npm test",
        "scripts/run-without-network.sh npm run typecheck",
        "scripts/run-without-network.sh npm run lint",
        "scripts/run-without-network.sh npm run build",
        "tests/test_alembic_postgresql.py",
        "alembic check",
    ):
        assert command in workflow
    assert "pull_request_target" not in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "GEMINI_API_KEY" not in workflow
    assert "OPENAI_API_KEY" not in workflow
```

- [x] **Step 2: Run the workflow contract and verify RED**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_ci_release_policy.py`

Expected: the wrapper test passes and the workflow contract fails because `.github/workflows/ci.yml` does not exist.

- [x] **Step 3: Add the four-job workflow with least privilege**

Use `actions/checkout@v7`, `actions/setup-python@v7`, and `actions/setup-node@v7`, which are the current majors documented by their official repositories. Set `persist-credentials: false` on checkout. Use Python `3.14`, Node `24`, pip/npm dependency caches, and job timeouts of 15 minutes.

The backend and frontend command steps set `SCANT_REQUIRE_NETWORK_NAMESPACE=1`. The migration PostgreSQL service uses database `scant_ci`, a CI-only password, and a health check; its test URL points at `127.0.0.1:5432`.

- [x] **Step 4: Run the CI contract and secret scanner**

Run: `cd apps/api && venv/bin/python -m pytest -q tests/test_ci_release_policy.py`

Run: `bash scripts/check-secrets.sh`

Expected: both pass; no application credential appears in the workflow.

- [x] **Step 5: Validate YAML and migration commands locally**

Run: `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml")'`

Run: `cd apps/api && venv/bin/alembic heads && venv/bin/alembic history`

Run: `cd apps/api && DATABASE_URL=sqlite+aiosqlite:////tmp/scant-ci-check.sqlite venv/bin/alembic upgrade head && DATABASE_URL=sqlite+aiosqlite:////tmp/scant-ci-check.sqlite venv/bin/alembic check`

Expected: YAML parses, Alembic reports head `0002`, and check reports no new upgrade operations.

- [x] **Step 6: Commit the workflow**

```bash
git add .github/workflows/ci.yml apps/api/tests/test_ci_release_policy.py
git commit -m "ci: enforce deterministic release gates"
```

### Task 3: Release documentation and final evidence

**Files:**

- Modify: `apps/api/TESTING.md`
- Modify: `README.md` (stage only the CI and migration-command hunks)
- Modify: `docs/superpowers/plans/2026-09-13-ci-release-gate.md`

**Interfaces:**

- Documents the exact local equivalents of every required CI job.
- Replaces the obsolete workbook-only migration command with the guarded Alembic bootstrap and check commands.

- [ ] **Step 1: Update operator and contributor commands**

Document `bash scripts/check-secrets.sh`, backend `pytest -q`, frontend test/typecheck/lint/build, the deterministic migration gate, and the opt-in PostgreSQL migration command. State that public-provider live tests remain manual.

- [ ] **Step 2: Run final release evidence**

Run backend normal and reverse collection order, frontend test/typecheck/lint/build, the 25-test SQLite migration gate, the two-test PostgreSQL 16 gate, `bash scripts/check-secrets.sh`, and the Alembic heads/history/check commands.

Expected: 299 backend tests pass with 12 live tests skipped in both orders; 95 frontend tests pass; typecheck/build pass; lint has zero errors; both migration gates pass; secret and Alembic checks pass.

- [ ] **Step 3: Self-review the workflow contract**

Confirm the workflow has no `pull_request_target`, write permission, application secret reference, public-provider live test, or deterministic test command outside the network wrapper. Confirm the PostgreSQL job scopes all DDL to its disposable CI database/schema.

- [ ] **Step 4: Commit documentation and evidence**

```bash
git add apps/api/TESTING.md docs/superpowers/plans/2026-09-13-ci-release-gate.md
git apply --cached /tmp/scant-readme-ci.patch
git commit -m "docs: record CI release evidence"
```
