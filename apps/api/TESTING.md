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

- Backend default suite: 246 passed, 33 live tests skipped, 0 failed; 125 existing deprecation warnings.
- Backend live collection: 33 live tests collected without executing them.
- Frontend unit suite: 95 passed, 0 failed, 0 skipped.
- TypeScript typecheck: passed.
- ESLint: passed with 0 errors and 51 existing warnings.
- Next.js production build: passed; Next.js reported the existing middleware convention deprecation warning.
