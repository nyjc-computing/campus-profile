# AGENTS.md

Notes for coding agents (and human contributors) working in this repo.

## Local dev tooling (machine-local, gitignored)

- **Live E2E harness**: `scripts/e2e_phase2.py` runs the real Flask app
  against the real dev campus.auth service with a fake signed-in user.
  Fetch the profile service's server-mode credentials from the deployment
  platform at session time and pass them as environment variables — never
  commit them or write them into docs:
  `CLIENT_ID=… CLIENT_SECRET=… poetry run python scripts/e2e_phase2.py`
  (`--serve 8001` to browse with `?as=b`/`?user=` switching the fake user;
  `MOCK_CONNECTED=1` mocks the connections read to eyeball the
  connected-card layout).
- **Backend-free visual preview**: `tools/run_preview.py` (committed,
  secret-free) stubs the Campus client entirely — demo user, canned
  registry/connection data from the test fixtures:
  `poetry run python tools/run_preview.py --port 5001`.
  Don't click Log out / Sign in / Connect there; they leave the stub.

## Railway deploy gotchas

- **The start command is platform-side**: an instance override on BOTH
  environments (`gunicorn --bind "[::]:${PORT:-8080}" main:app` — dual-stack,
  the Railway mesh is IPv6-only). There is deliberately no Procfile (Railpack
  deprecates them; removed in #82) and no `railway.json` yet — the override is
  the only start definition, so never clear it without setting a replacement.
  Edit via the GraphQL API (`railway api`): clearing needs
  `input: { startCommand: "" }` (`null` is a silent no-op); *setting* a value
  does not auto-redeploy — force one with the `serviceInstanceDeploy` mutation
  (`latestCommit: true`).
- **Gateway paths are wired per environment**: `PROFILE_HOST`/`PROFILE_PORT`
  etc. live on the campus-gateway service instance (see campus
  `deploy/gateway/README.md`). An unwired path 502s with nginx resolving the
  `downstream-unrouted.invalid` Dockerfile placeholder.

## Flask/app gotchas

- **Templates are cached when debug is off** — the deployed app and local
  servers run without debug, so template edits don't appear until restart
  unless `app.config["TEMPLATES_AUTO_RELOAD"] = True` is set. Both local
  servers set it; the deployed app intentionally does not.
- Older upstream pins had two kwarg gaps that matter for direct view
  calls and non-GET query params (campus#772, campus-api-python#68).
  This lock's pins (campus-suite 518a9fa, campus-api-python 9563443)
  include both fixes — re-check if the lock ever moves backwards.
- **Feature modules use the blueprint factory pattern** (since #85):
  a feature's routes live in `<feature>_views.py`, with views defined
  inside `init_<feature>(app, login_manager)` so login protection is
  injected. Importing login_manager from main at module level would
  double-import main when run as a script (`python main.py`). The
  feature's data stays in a flask-free seam module (`events.py`) —
  the single swap point for the future real backend.
