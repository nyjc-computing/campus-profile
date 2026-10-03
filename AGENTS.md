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
- **Backend-free visual preview**: `.zcode/run_preview.py` stubs the
  Campus client entirely (demo user, canned credentials).

## Flask/app gotchas

- **Templates are cached when debug is off** — the deployed app and local
  servers run without debug, so template edits don't appear until restart
  unless `app.config["TEMPLATES_AUTO_RELOAD"] = True` is set. Both local
  servers set it; the deployed app intentionally does not.
- Older upstream pins had two kwarg gaps that matter for direct view
  calls and non-GET query params (campus#772, campus-api-python#68).
  This lock's pins (campus-suite 74738e1, campus-api-python 39a6285)
  include both fixes — re-check if the lock ever moves backwards.
