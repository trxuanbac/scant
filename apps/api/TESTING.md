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

## Current verification

Verified on 2026-09-12:

- Backend default suite: 274 passed, 10 live tests skipped, 0 failed; 166 existing deprecation warnings.
- Backend deterministic suite in reverse collection order: 274 passed, 0 failed; 166 existing deprecation warnings.
- Shared fixture stress run: four database/client modules collected twice in one process, 40 passed and 0 failed.
- Backend live collection: 10 live tests collected without executing them.
- Frontend unit suite: 95 passed, 0 failed, 0 skipped.
- TypeScript typecheck: passed.
- ESLint: passed with 0 errors and 51 existing warnings.
- Next.js production build: passed; Next.js reported the existing middleware convention deprecation warning.

The remaining live collection consists of Crossref/arXiv/deep-research checks, research search/API checks, one real PostgreSQL integration, multi-provider anti-hallucination, DOI and URL verification, a source API flow that fetches a public page, and the policy sentinel.

The remaining local test engines are intentional because their database or application topology is the subject of the test:

- `test_admin_billing_security.py` builds a minimal FastAPI app around billing routers and a controlled payment provider.
- `test_admin_migration.py` constructs incomplete and prerelease schemas to test additive migration behavior.
- `test_seed_sample.py` injects a standalone engine into the seed command to test repeated execution and repair.
- `test_workbook_action_ledger.py` uses file-backed databases to test migration and reopen persistence.
- `test_phase_u27_5_production_reality_audit.py` connects to the separately configured PostgreSQL audit database only when live tests are enabled.
