"""Smoke tests to verify basic application functionality."""
import os
import unittest

# Default to CI's dummy values so the suite runs without local setup.
for _var, _value in (
    ("CLIENT_ID", "test-client-id"),
    ("CLIENT_SECRET", "test-client-secret"),
    ("HOSTNAME", "localhost:5000"),
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


if __name__ == "__main__":
    unittest.main()
