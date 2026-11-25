"""Backend-free visual preview (see AGENTS.md): runs the real Flask app
with the Campus client stubbed out entirely — demo user, canned registry
and connection data lifted from the test fixtures.

    poetry run python tools/run_preview.py --port 5001

Sign-in is faked via a before_request hook (g.user is what
login_required checks — see tests/test_smoke.py _SignedInTest).
Do not click Log out / Sign in / Connect here: those leave the stub
and hit the real campus.auth dev server, which rejects fake clients.
"""
import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# campus_python reads CLIENT_ID/CLIENT_SECRET at import time.
# BASE_URL: flask-campus's before_request hook resolves the campus.auth
# origin on every request; the CI sentinel (never contacted here) is
# enough for the stubbed preview.
for _var, _value in (
    ("CLIENT_ID", "preview-client-id"),
    ("CLIENT_SECRET", "preview-client-secret"),
    ("PUBLIC_URL", "http://localhost:5001"),
    ("SECRET_KEY", "preview-secret"),
    ("BASE_URL", "https://campus.test"),
):
    os.environ.setdefault(_var, _value)

from types import SimpleNamespace

import flask

import main
from tests.test_smoke import (
    CLASSROOM_CONNECTION,
    REGISTRY_BODY,
    _FakeResponse,
    _campus,
)

DEMO_USER = SimpleNamespace(
    id="student@nyjc.edu.sg",
    name="Demo Student",
    email="student@nyjc.edu.sg",
    created_at="2026-10-03T09:00:00Z",
)

# Classroom connected, calendar stub not — the same state the tests
# assert against.
ROUTES = {
    ("GET", "/integrations/v1/"): _FakeResponse(200, REGISTRY_BODY),
    ("GET", "/auth/v1/connections/"): _FakeResponse(
        200, {"connections": [CLASSROOM_CONNECTION]}),
}

main.client = _campus(ROUTES)


@main.app.before_request
def _demo_signin():
    flask.g.user = DEMO_USER


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()

    # AGENTS.md gotcha: templates are cached when debug is off.
    main.app.config["TEMPLATES_AUTO_RELOAD"] = True
    print(f"Preview serving on http://localhost:{args.port} "
          f"(demo user {DEMO_USER.email}, stubbed campus client)")
    main.app.run(host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    run()
