"""Smoke tests to verify basic application functionality."""
import os
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

# Default to CI's dummy values so the suite runs without local setup.
for _var, _value in (
    ("CLIENT_ID", "test-client-id"),
    ("CLIENT_SECRET", "test-client-secret"),
    ("PUBLIC_URL", "http://localhost:5000"),
):
    os.environ.setdefault(_var, _value)

from campus_python import errors


class _FakeToken:
    """Minimal stand-in for campus.model.OAuthToken."""

    def __init__(self, expired=False, scopes=None):
        self._expired = expired
        self.scopes = scopes if scopes is not None else ["read:user"]
        self.expires_at = "2099-01-01T00:00:00Z"

    def is_expired(self):
        return self._expired


class _FakeUserCredentials:
    """Minimal stand-in for campus.model.UserCredentials."""

    def __init__(self, token=None, created_at="2026-01-01T00:00:00Z"):
        self.token = token
        self.created_at = created_at


class _FakeCredentialEntry:
    """Returns canned credentials or raises, like the credentials API."""

    def __init__(self, creds=None, error=None):
        self._creds = creds
        self._error = error

    def get(self):
        if self._error is not None:
            raise self._error
        return self._creds


class _FakeCredentialsCollection:
    """Mirrors client.auth.credentials[provider][user_id].get()."""

    def __init__(self, entry):
        self._entry = entry

    def __getitem__(self, provider):
        return _FakeProvider(self._entry)


class _FakeProvider:
    def __init__(self, entry):
        self._entry = entry

    def __getitem__(self, user_id):
        return self._entry


class _FakeAuth:
    def __init__(self, entry):
        self.credentials = _FakeCredentialsCollection(entry)


class _FakeClient:
    def __init__(self, entry):
        self.auth = _FakeAuth(entry)


class SmokeTest(unittest.TestCase):
    """Basic smoke tests that verify the application can import and initialize."""

    def test_main_imports(self):
        """Verify that main.py imports without errors."""
        import main

    def test_flask_app_exists(self):
        """Verify that the Flask app is created."""
        import main
        self.assertIsNotNone(main.app)

    def test_routes_defined(self):
        """Verify that expected routes are defined."""
        import main
        rules = [str(rule) for rule in main.app.url_map.iter_rules()]

        # Check for main routes
        self.assertTrue(any("/" in rule for rule in rules))
        self.assertTrue(any("/profile/" in rule for rule in rules))
        self.assertTrue(any("/profile/integrations" in rule for rule in rules))
        self.assertTrue(any(
            "/profile/integrations/classroom/connect" in rule
            for rule in rules))
        self.assertTrue(any(
            "/profile/integrations/classroom/callback" in rule
            for rule in rules))


class GetIntegrationStatusTest(unittest.TestCase):
    """Unit tests for the per-provider connection status builder."""

    USER_ID = "student@nyjc.edu.sg"

    def _status(self, creds=None, error=None):
        import integrations
        client = _FakeClient(_FakeCredentialEntry(creds=creds, error=error))
        return integrations.get_integration_status(client, "github", self.USER_ID)

    def test_not_connected(self):
        """A missing credential row means the provider is not connected."""
        import integrations
        status = self._status(error=errors.NotFoundError("no credentials"))
        self.assertEqual(status["status"], integrations.STATUS_NOT_CONNECTED)

    def test_connected_with_valid_token(self):
        """A live token means the integration is active."""
        import integrations
        creds = _FakeUserCredentials(token=_FakeToken(expired=False))
        status = self._status(creds=creds)
        self.assertEqual(status["status"], integrations.STATUS_CONNECTED)

    def test_expired_token(self):
        """An expired token is surfaced distinctly from a live one."""
        import integrations
        creds = _FakeUserCredentials(token=_FakeToken(expired=True))
        status = self._status(creds=creds)
        self.assertEqual(status["status"], integrations.STATUS_EXPIRED)

    def test_parse_failure_reports_unknown(self):
        """Token rehydration failures degrade to unknown, not a 500."""
        import integrations
        # campus-suite builds older than ff98c44 raise TypeError/KeyError
        # while rehydrating the embedded token.
        for error in (TypeError("bad token"), KeyError("token")):
            with self.subTest(error=type(error).__name__):
                status = self._status(error=error)
                self.assertEqual(status["status"], integrations.STATUS_UNKNOWN)

    def test_api_error_reports_unknown(self):
        """Backend errors degrade to unknown, not a 500."""
        import integrations
        status = self._status(error=errors.APIError(error_description="boom"))
        self.assertEqual(status["status"], integrations.STATUS_UNKNOWN)

    def test_status_never_contains_token_material(self):
        """The view must not carry tokens or server-managed metadata."""
        creds = _FakeUserCredentials(token=_FakeToken())
        status = self._status(creds=creds)
        for key in ("token", "access_token", "expires_at", "connected_at",
                    "scopes", "refresh_token", "client_id"):
            self.assertNotIn(key, status)

    def test_connect_pointer_passes_through(self):
        """Cards expose the catalog's connect-flow pointer, others None."""
        import integrations
        creds = _FakeUserCredentials(token=_FakeToken())
        classroom = integrations.get_integration_status(
            _FakeClient(_FakeCredentialEntry(creds=creds)),
            "google.classroom", self.USER_ID)
        self.assertEqual(classroom["connect"], "google/classroom")
        github = integrations.get_integration_status(
            _FakeClient(_FakeCredentialEntry(creds=creds)),
            "github", self.USER_ID)
        self.assertIsNone(github["connect"])

    def test_classroom_status_probe_degrades_to_unknown(self):
        """A denied classroom status probe shows Unknown, not a 500."""
        import integrations
        # Profile has no upstream_scopes for google.classroom, so the
        # status probe is refused campus-side until Phase 2.
        status = self._status(error=errors.AccessDeniedError(
            error_description="no upstream_scopes for client"))
        self.assertEqual(status["status"], integrations.STATUS_UNKNOWN)


class ConnectFlowTest(unittest.TestCase):
    """The campus.auth classroom connect flow (profile#23)."""

    def setUp(self):
        import flask

        import main
        main.app.config["TESTING"] = True
        main.app.secret_key = "smoke-test-secret"
        self.flask = flask
        self.main = main

    def _signed_in(self, path: str):
        """Push a request context whose g.user passes login_required."""
        ctx = self.main.app.test_request_context(path)
        ctx.push()
        self.flask.g.user = SimpleNamespace(id="student@nyjc.edu.sg")
        self.addCleanup(ctx.pop)
        return ctx

    def test_connect_redirects_to_campusauth_with_nonce(self):
        """Connect starts the campus.auth flow with a session-bound nonce."""
        self._signed_in("/profile/integrations/classroom/connect")
        response = self.main.get_classroom_connect()

        location = response.headers["Location"]
        prefix = ("https://campusauth-development.up.railway.app"
                  "/auth/v1/google/classroom/authorize?target=")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(location.startswith(prefix), location)

        target = parse_qs(urlparse(location).query)["target"][0]
        self.assertEqual(
            urlparse(target).path,
            "/profile/integrations/classroom/callback")
        nonce = parse_qs(urlparse(target).query)["connect_state"][0]
        self.assertEqual(
            nonce, self.flask.session[self.main.CLASSROOM_CONNECT_STATE])
        self.assertTrue(len(nonce) >= 32)  # token_urlsafe randomness

    def test_connect_replaces_stale_nonce(self):
        """A fresh Connect overwrites any stale nonce from an abandoned flow."""
        self._signed_in("/profile/integrations/classroom/connect")
        self.flask.session[self.main.CLASSROOM_CONNECT_STATE] = "stale"
        self.main.get_classroom_connect()
        self.assertNotEqual(
            self.flask.session[self.main.CLASSROOM_CONNECT_STATE], "stale")

    def test_callback_accepts_matching_nonce(self):
        """A genuine callback flashes success and clears the nonce."""
        self._signed_in(
            "/profile/integrations/classroom/callback"
            "?connect_state=expected-nonce")
        self.flask.session[self.main.CLASSROOM_CONNECT_STATE] = \
            "expected-nonce"

        response = self.main.get_classroom_connect_callback()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            urlparse(response.headers["Location"]).path,
            "/profile/integrations")
        self.assertNotIn(
            self.main.CLASSROOM_CONNECT_STATE, self.flask.session)
        flashes = self.flask.get_flashed_messages(with_categories=True)
        self.assertEqual(flashes, [("success", "Classroom connected")])

    def test_callback_rejects_mismatched_nonce(self):
        """A nonce this flow did not issue is treated as not connected."""
        self._signed_in(
            "/profile/integrations/classroom/callback"
            "?connect_state=forged")
        self.flask.session[self.main.CLASSROOM_CONNECT_STATE] = \
            "expected-nonce"

        response = self.main.get_classroom_connect_callback()

        self.assertEqual(
            urlparse(response.headers["Location"]).path,
            "/profile/integrations")
        flashes = self.flask.get_flashed_messages(with_categories=True)
        self.assertEqual(len(flashes), 1)
        self.assertEqual(flashes[0][0], "warning")

    def test_callback_rejects_missing_nonce(self):
        """A direct callback visit (stale nonce) is not a success."""
        self._signed_in("/profile/integrations/classroom/callback")

        response = self.main.get_classroom_connect_callback()

        self.assertEqual(
            urlparse(response.headers["Location"]).path,
            "/profile/integrations")
        flashes = self.flask.get_flashed_messages(with_categories=True)
        self.assertEqual(flashes[0][0], "warning")


class RouteSmokeTest(unittest.TestCase):
    """Test-client checks for public route behavior."""

    @classmethod
    def setUpClass(cls):
        import main
        main.app.config["TESTING"] = True
        cls.client = main.app.test_client()

    def test_index_renders_sign_in(self):
        """The landing page renders for anonymous visitors."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sign in", response.data)

    def test_profile_redirects_to_login_when_signed_out(self):
        """Signed-out users are redirected to login."""
        response = self.client.get("/profile/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_connect_flow_routes_require_signin(self):
        """Both classroom connect routes are login-protected."""
        for path in ("/profile/integrations/classroom/connect",
                     "/profile/integrations/classroom/callback"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
