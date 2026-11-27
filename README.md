# campus-profile

An application that allows Campus users to see their own profile and data
(3rd-party integrations, activity history, logged on devices...).

Part of the [Campus ecosystem](https://github.com/nyjc-computing): sign-in
and integration grants are handled by campus.auth through the
[flask-campus](https://github.com/nyjc-computing/flask-campus) layer; this
app is the thin Flask front on top. The Campus client libraries are
installed as wheels pinned from other nyjc-computing repos' GitHub
releases (see `pyproject.toml`).

## Requirements

- Python 3.11–3.13 (CI-supported range; 3.14 not yet supported)
- [Poetry](https://python-poetry.org/)

## Setup

```bash
poetry install --no-root
```

## Environment variables

All configuration comes from the environment — there are no config files
and no baked-in service topology:

| Variable | Required | Purpose |
|---|---|---|
| `CLIENT_ID` / `CLIENT_SECRET` | yes | This app's OAuth client at campus.auth (server-mode credentials; fetch from the deployment platform). Read at import time. |
| `SECRET_KEY` | yes | Signs the Flask session cookie (login, flash, CSRF). The app refuses to boot without it. |
| `PUBLIC_URL` | yes | This app's public origin; used to build OAuth redirect/callback URLs (the callback lands at `/profile/finalize_login` on this origin). |
| `BASE_URL` or `CAMPUS_AUTH_URL` | yes | The campus.auth origin. Required even to render the landing page: flask-campus resolves it on every request. |
| `AUDIT_API_KEY` + `AUDIT_TRACING_ENABLED` | no | Opt-in audit tracing (see the campus repo's `docs/audit-tracing.md`; flipping the flag is a redeploy). |

## Running

```bash
poetry run python main.py   # http://localhost:5000
```

Without real campus.auth credentials only the landing page renders —
sign-in needs this app's registered OAuth client. For a credentials-free
look at the signed-in pages, see the preview harness in `AGENTS.md`.

## Tests

With the same dummy values CI uses:

```bash
CLIENT_ID=test-client-id CLIENT_SECRET=test-client-secret \
PUBLIC_URL=http://localhost:5000 BASE_URL=https://campus.test \
SECRET_KEY=test-secret-key \
poetry run python -m unittest discover tests
```

Lint (same policy as the campus repo — config in `pyproject.toml`, no
autofixes):

```bash
poetry run ruff check .
```

CI (`.github/workflows/tests.yml`) runs ruff and the test suite on
Python 3.11, 3.12 and 3.13 for every push/PR to `main` and `dev`.

## Architecture

- `main.py` — the Flask app and all routes:
  - `/` — public landing page
  - `/health` — fleet liveness probe (`200 "ok"`; no auth, no session,
    no downstream calls)
  - `/profile/` — profile page (login required)
  - `/profile/integrations` — integration cards enumerated from the
    campus.auth registry, with per-user connection status
  - `POST /profile/integrations/<slug>/disconnect` — disconnect a grant
    (session-bound CSRF token; 404 is idempotent success)
  - `GET /profile/integrations/<slug>/connect` + `/callback` — generic
    connect flow via campus.auth for any integration the registry marks
    connectable, protected by a per-slug session nonce (#70)
- `integrations.py` — builds the integration cards and handles
  connection status/disconnect. The registry is the catalog: this app
  keeps no list of integrations and never touches token material.
- `templates/` + `static/` — Bootstrap 5 UI. Templates are cached when
  debug is off (see the gotcha in `AGENTS.md`).
- `tests/test_smoke.py` — unittest suite: unit tests, view-level tests
  against faked campus clients, and route-guard tests.

## Deployment

Deployed on Railway; the deploy configuration lives platform-side (there
are no deploy files in this repo). The deployed app intentionally runs
without debug and without `TEMPLATES_AUTO_RELOAD`. The deploy process
and credential ownership are not yet documented here — confirm with the
previous maintainer and record them in this section.

## Contributor and agent notes

See [AGENTS.md](AGENTS.md) for dev tooling (E2E harness, preview server)
and app gotchas.
