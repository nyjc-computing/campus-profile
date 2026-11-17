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

from campus.model import Integration
from campus_python import errors
from campus_python.auth.v1.connections import Connections
from campus_python.integrations.v1 import IntegrationsRoot
from campus_python.interface import ResourceRoot

USER_ID = "student@nyjc.edu.sg"

# Live-verified registry shape (campus dev, 2026-10-03): an envelope
# object, never a bare array, with calendar as a listed-but-not-
# connectable stub.
REGISTRY_BODY = {
    "integrations": [
        {
            "provider": "google.classroom",
            "slug": "classroom",
            "base_provider": "google",
            "title": "Google Classroom",
            "description": (
                "Connect Google Classroom to your Campus account so "
                "Campus apps can read your courses and coursework."
            ),
            "scopes": [
                "https://www.googleapis.com/auth/classroom.courses.readonly",
            ],
            "connectable": True,
            "authorize_path": "/auth/v1/google/classroom/authorize",
        },
        {
            "provider": "google.calendar",
            "slug": "calendar",
            "base_provider": "google",
            "title": "Google Calendar",
            "description": (
                "Connect Google Calendar to your Campus account "
                "(coming soon)."
            ),
            "scopes": [],
            "connectable": False,
            "authorize_path": "/auth/v1/google/calendar/authorize",
        },
    ]
}

# Live-verified connection payloads (metadata by contract — no token
# values). expires_at is deliberately stale: campus refreshes silently
# server-side, so a healthy connection usually shows a past timestamp.
CLASSROOM_CONNECTION = {
    "provider": "google.classroom",
    "integration": "classroom",
    "scopes": ["https://www.googleapis.com/auth/classroom.courses.readonly"],
    "connected_at": "2026-10-03T09:00:00Z",
    "expires_at": "2026-10-03T12:00:00Z",
}

# Login via Google shows up as an identity connection, not an
# integration grant.
GOOGLE_IDENTITY_CONNECTION = {
    "provider": "google",
    "integration": None,
    "scopes": ["email", "profile"],
    "connected_at": "2026-10-03T09:00:00Z",
    "expires_at": "2026-10-03T12:00:00Z",
}


class _FakeResponse:
    """Minimal stand-in for the client library's JsonResponse."""

    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code < 400:
            return
        error = errors.APIError.with_status_code(self.status_code, self._body)
        if error is not None:
            raise error


class _FakeJsonClient:
    """Serves canned responses per (method, path), records calls."""

    def __init__(self, routes=None,
                 base_url="https://campusauth-development.up.railway.app"):
        self.routes = routes or {}
        self.base_url = base_url
        self.calls = []

    def get(self, path, query=None):
        self.calls.append(("GET", path, query))
        return self.routes.get(("GET", path), _FakeResponse())

    def delete(self, path, _json=None, query=None):
        self.calls.append(("DELETE", path, query))
        return self.routes.get(("DELETE", path), _FakeResponse())


class _FakeAuth(ResourceRoot):
    """The real auth root shape (/auth/v1 over the JSON client), so the
    app delegates to the library's connections resource like production."""

    url_prefix = "/auth/v1"

    def __init__(self, json_client):
        super().__init__(json_client=json_client)
        self._connections = None

    @property
    def connections(self) -> Connections:
        if self._connections is None:
            self._connections = Connections(root=self)
        return self._connections


class _FakeCampus:
    def __init__(self, json_client):
        self.auth = _FakeAuth(json_client)
        # The registry resource is mounted campus-wide (api#84) and
        # shares the auth service's JSON client.
        self.integrations = IntegrationsRoot(json_client=json_client)


def _registry_models() -> list[Integration]:
    """Registry fixtures as the client library returns them."""
    return [
        Integration.from_resource(entry)
        for entry in REGISTRY_BODY["integrations"]
    ]


def _campus(routes=None) -> _FakeCampus:
    return _FakeCampus(_FakeJsonClient(routes))


class SmokeTest(unittest.TestCase):
    """Basic smoke tests that verify the application can import and initialize."""

    def test_main_imports(self):
        """Verify that main.py imports without errors."""
        import main  # noqa: F401 -- the import itself is the assertion

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
        self.assertTrue(any(
            "/profile/integrations/<slug>/disconnect" in rule
            for rule in rules))


class RegistryTest(unittest.TestCase):
    """The campus.auth integration registry feed (#25, #20)."""

    def test_fetch_registry_delegates_to_the_client_resource(self):
        """fetch_registry returns Integration models, via /integrations/v1/."""
        import integrations
        client = _campus({
            ("GET", "/integrations/v1/"): _FakeResponse(200, REGISTRY_BODY),
        })
        registry = integrations.fetch_registry(client)
        self.assertEqual(
            [entry.slug for entry in registry],
            ["classroom", "calendar"])
        for entry in registry:
            self.assertIsInstance(entry, Integration)
        self.assertEqual(
            client.auth.client.calls[0][1], "/integrations/v1/")

    def test_registry_outage_propagates(self):
        """Registry failures propagate; the page decides degradation."""
        import integrations
        client = _campus({
            ("GET", "/integrations/v1/"): _FakeResponse(
                503, {"error": {"code": "UNAVAILABLE"}}),
        })
        with self.assertRaises(errors.APIError):
            integrations.fetch_registry(client)


class ConnectionsTest(unittest.TestCase):
    """The delegated connections read (#25, campus#750)."""

    def test_read_names_the_user_via_query_param(self):
        """Basic auth carries no user: user_id rides the query string."""
        import integrations
        client = _campus({
            ("GET", "/auth/v1/connections/"): _FakeResponse(
                200, {"connections": [CLASSROOM_CONNECTION]}),
        })
        connections = integrations.fetch_connections(client, USER_ID)
        self.assertEqual(connections, [CLASSROOM_CONNECTION])
        method, path, query = client.auth.client.calls[0]
        self.assertEqual((method, path), ("GET", "/auth/v1/connections/"))
        self.assertEqual(query, {"user_id": USER_ID})

    def test_read_envelope_is_unwrapped(self):
        """{"connections": [...]} — absent user is an empty list."""
        import integrations
        client = _campus({
            ("GET", "/auth/v1/connections/"): _FakeResponse(
                200, {"connections": []}),
        })
        self.assertEqual(integrations.fetch_connections(client, USER_ID), [])

    def test_read_failure_propagates(self):
        """A failed read propagates; the page marks cards unavailable."""
        import integrations
        client = _campus({
            ("GET", "/auth/v1/connections/"): _FakeResponse(
                503, {"error": {"code": "UNAVAILABLE"}}),
        })
        with self.assertRaises(errors.APIError):
            integrations.fetch_connections(client, USER_ID)


class BuildCardTest(unittest.TestCase):
    """Mapping connections inventory onto registry entries (#25)."""

    def _card(self, connections, entry_slug="classroom"):
        import integrations
        entry = integrations.registry_entry(
            _registry_models(), entry_slug)
        return integrations.build_card(
            entry, integrations.find_connection(connections, entry))

    def test_absent_connection_means_not_connected(self):
        """No matching connection entry renders Not connected."""
        import integrations
        card = self._card([])
        self.assertEqual(card["status"], integrations.STATUS_NOT_CONNECTED)
        self.assertEqual(card["label"], "Not connected")

    def test_present_connection_means_connected(self):
        """Presence of the grant is Connected — even with a stale
        expires_at (campus refreshes silently server-side)."""
        import integrations
        card = self._card([CLASSROOM_CONNECTION])
        self.assertEqual(card["status"], integrations.STATUS_CONNECTED)
        self.assertEqual(card["label"], "Connected")

    def test_identity_connection_is_not_an_integration_grant(self):
        """Google login (integration: null) never connects Classroom."""
        import integrations
        card = self._card([GOOGLE_IDENTITY_CONNECTION])
        self.assertEqual(card["status"], integrations.STATUS_NOT_CONNECTED)

    def test_other_integration_grants_do_not_bleed_over(self):
        """A calendar grant must not light up the classroom card."""
        import integrations
        calendar_grant = dict(CLASSROOM_CONNECTION,
                              provider="google.calendar",
                              integration="calendar")
        card = self._card([calendar_grant])
        self.assertEqual(card["status"], integrations.STATUS_NOT_CONNECTED)

    def test_card_is_metadata_free(self):
        """Connection metadata is server-managed, never template-bound."""
        card = self._card([CLASSROOM_CONNECTION])
        for key in ("scopes", "connected_at", "expires_at",
                    "access_token", "refresh_token", "token"):
            self.assertNotIn(key, card)

    def test_registry_fields_pass_through(self):
        """Title/description/connectable come from the registry."""
        card = self._card([])
        self.assertEqual(card["id"], "classroom")
        self.assertEqual(card["title"], "Google Classroom")
        self.assertTrue(card["connectable"])
        self.assertIn("read your courses", card["description"])

    def test_stub_is_not_connectable(self):
        """The calendar stub renders but offers no connect flow."""
        import integrations
        card = self._card([], entry_slug="calendar")
        self.assertFalse(card["connectable"])
        self.assertEqual(card["status"], integrations.STATUS_NOT_CONNECTED)

    def test_unknown_slug_gets_a_generic_icon(self):
        """Icons are display hints; unknown slugs degrade to a plug."""
        import integrations
        entry = Integration.from_resource(
            dict(REGISTRY_BODY["integrations"][0], slug="whiteboards"))
        card = integrations.build_card(entry, None)
        self.assertEqual(card["icon"], "bi-plug")

    def test_unavailable_marks_the_card(self):
        """A failed status read stamps every card unavailable."""
        import integrations
        card = integrations.mark_unavailable(self._card([]))
        self.assertEqual(card["status"], integrations.STATUS_UNAVAILABLE)
        self.assertEqual(card["label"], "Status unavailable")


class DisconnectUnitTest(unittest.TestCase):
    """integrations.disconnect against the campus.auth primitive."""

    def _disconnect(self, status):
        import integrations
        entry = integrations.registry_entry(
            _registry_models(), "classroom")
        client = _campus({
            ("DELETE", "/auth/v1/connections/google/classroom/"):
                _FakeResponse(status, {}),
        })
        result = integrations.disconnect(client, entry, USER_ID)
        return result, client

    def test_delete_hits_the_integration_route(self):
        """Two-segment form: /connections/google/classroom/?user_id=…."""
        _, client = self._disconnect(200)
        method, path, query = client.auth.client.calls[0]
        self.assertEqual(method, "DELETE")
        self.assertEqual(
            path, "/auth/v1/connections/google/classroom/")
        self.assertEqual(query, {"user_id": USER_ID})

    def test_200_means_disconnected(self):
        """200 {} deletes the stored grant."""
        result, _ = self._disconnect(200)
        self.assertTrue(result)

    def test_404_is_idempotent_success(self):
        """404: nothing was connected — not an error."""
        result, _ = self._disconnect(404)
        self.assertFalse(result)

    def test_real_failures_raise(self):
        """A campus outage is not silently swallowed."""
        import integrations
        entry = integrations.registry_entry(
            _registry_models(), "classroom")
        client = _campus({
            ("DELETE", "/auth/v1/connections/google/classroom/"):
                _FakeResponse(503, {"error": {"code": "UNAVAILABLE"}}),
        })
        with self.assertRaises(errors.APIError):
            integrations.disconnect(client, entry, USER_ID)


class _SignedInTest(unittest.TestCase):
    """Base for view-level tests that need a signed-in g.user."""

    def setUp(self):
        import flask

        import main
        main.app.config["TESTING"] = True
        main.app.secret_key = "smoke-test-secret"
        self.flask = flask
        self.main = main

    def _signed_in(self, path: str, user_id: str = USER_ID):
        """Push a request context whose g.user passes login_required."""
        ctx = self.main.app.test_request_context(path)
        ctx.push()
        self.flask.g.user = SimpleNamespace(id=user_id)
        self.addCleanup(ctx.pop)
        return ctx

    def _patch_client(self, client):
        """Swap main.client for a fake; restore the real one after."""
        import main
        original = main.client
        main.client = client
        self.addCleanup(setattr, main, "client", original)
        return client


class IntegrationsPageTest(_SignedInTest):
    """The /profile/integrations page against faked campus.auth."""

    def _routes(self, connections_body=None, registry_status=200,
                connections_status=200):
        routes = {
            ("GET", "/integrations/v1/"): _FakeResponse(
                registry_status, REGISTRY_BODY),
        }
        if connections_body is not None or connections_status != 200:
            routes[("GET", "/auth/v1/connections/")] = _FakeResponse(
                connections_status, connections_body or {})
        return routes

    def test_cards_come_from_the_registry(self):
        """Both registry entries render; the stub has no Connect."""
        self._signed_in("/profile/integrations")
        self._patch_client(_campus(
            self._routes({"connections": []})))
        html = self.main.get_integrations_page()

        self.assertIn("Google Classroom", html)
        self.assertIn("Google Calendar", html)
        self.assertIn("Not connected", html)
        # Only the connectable integration gets a Connect link, and it
        # points at the classroom connect flow (#23/#24).
        self.assertEqual(html.count("/profile/integrations/classroom/connect"), 1)
        self.assertIn(">Connect</a>", html)
        self.assertNotIn("Reconnect", html)

    def test_connected_user_sees_disconnect(self):
        """A connected classroom shows Connected + a Disconnect form.

        The connect affordance stays (prompt=consent re-consent), but
        reads Reconnect next to a Connected badge (#26 thread)."""
        self._signed_in("/profile/integrations")
        self._patch_client(_campus(self._routes({
            "connections": [CLASSROOM_CONNECTION]})))
        html = self.main.get_integrations_page()

        self.assertIn("Connected", html)
        self.assertIn("Reconnect", html)
        self.assertIn('action="/profile/integrations/classroom/disconnect"', html)
        self.assertIn("confirm(", html)

    def test_status_read_failure_marks_cards_unavailable(self):
        """Campus unreachable: honest unavailability, not false
        "Not connected"."""
        self._signed_in("/profile/integrations")
        self._patch_client(_campus(self._routes(
            connections_status=503)))
        html = self.main.get_integrations_page()

        self.assertIn("Status unavailable", html)
        self.assertNotIn("Not connected", html)
        self.assertIn("Could not load your connection status", html)

    def test_registry_failure_renders_empty_grid(self):
        """No registry, no cards — with a warning instead of a 500."""
        self._signed_in("/profile/integrations")
        client = _campus({
            ("GET", "/integrations/v1/"): _FakeResponse(
                503, {"error": {"code": "UNAVAILABLE"}}),
        })
        self._patch_client(client)
        html = self.main.get_integrations_page()

        self.assertNotIn("Google Classroom", html)
        self.assertIn("Could not load the integrations catalog", html)


class DisconnectRouteTest(_SignedInTest):
    """POST /profile/integrations/<slug>/disconnect."""

    def _post(self, delete_status=200):
        routes = {
            ("GET", "/integrations/v1/"): _FakeResponse(200, REGISTRY_BODY),
            ("DELETE", "/auth/v1/connections/google/classroom/"):
                _FakeResponse(delete_status, {}),
        }
        client = _campus(routes)
        self._patch_client(client)
        return client

    def test_disconnect_flashes_and_redirects(self):
        """A real disconnect confirms and returns to the page."""
        self._signed_in("/profile/integrations/classroom/disconnect")
        self._post()
        response = self.main.post_integration_disconnect(slug="classroom")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            urlparse(response.headers["Location"]).path,
            "/profile/integrations")
        flashes = self.flask.get_flashed_messages(with_categories=True)
        self.assertEqual(
            flashes, [("success", "Google Classroom disconnected")])

    def test_disconnect_404_is_a_clean_success(self):
        """Nothing was connected: idempotent, no error (#25)."""
        self._signed_in("/profile/integrations/classroom/disconnect")
        self._post(delete_status=404)
        self.main.post_integration_disconnect(slug="classroom")

        flashes = self.flask.get_flashed_messages(with_categories=True)
        self.assertEqual(
            flashes, [("info", "Google Classroom was not connected")])

    def test_disconnect_outage_warns_instead_of_500(self):
        """A campus outage degrades to a warning flash."""
        client = _campus({
            ("GET", "/integrations/v1/"): _FakeResponse(200, REGISTRY_BODY),
            ("DELETE", "/auth/v1/connections/google/classroom/"):
                _FakeResponse(503, {"error": {"code": "UNAVAILABLE"}}),
        })
        self._signed_in("/profile/integrations/classroom/disconnect")
        self._patch_client(client)

        response = self.main.post_integration_disconnect(slug="classroom")
        self.assertEqual(response.status_code, 302)
        flashes = self.flask.get_flashed_messages(with_categories=True)
        self.assertEqual(flashes[0][0], "warning")

    def test_unknown_slug_is_404(self):
        """Unregistry'd slugs do not reach campus.auth."""
        from werkzeug.exceptions import NotFound

        self._signed_in("/profile/integrations/nope/disconnect")
        self._post()
        with self.assertRaises(NotFound):
            self.main.post_integration_disconnect(slug="nope")

    def test_non_connectable_stub_is_404(self):
        """The calendar stub manages no grants from this page."""
        from werkzeug.exceptions import NotFound

        self._signed_in("/profile/integrations/calendar/disconnect")
        self._post()
        with self.assertRaises(NotFound):
            self.main.post_integration_disconnect(slug="calendar")


class ConnectFlowTest(_SignedInTest):
    """The campus.auth classroom connect flow (profile#23, #25 URL source)."""

    def _registry_client(self):
        client = _campus({
            ("GET", "/integrations/v1/"): _FakeResponse(200, REGISTRY_BODY),
        })
        self._patch_client(client)
        return client

    def test_connect_redirects_to_campusauth_with_nonce(self):
        """Connect starts the campus.auth flow with a session-bound nonce."""
        self._registry_client()
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

    def test_connect_authorize_path_comes_from_the_registry(self):
        """The authorize URL is registry-sourced, not hardcoded (#25)."""
        client = self._registry_client()
        self._signed_in("/profile/integrations/classroom/connect")
        self.main.get_classroom_connect()

        method, path, _ = client.auth.client.calls[0]
        self.assertEqual((method, path), ("GET", "/integrations/v1/"))

    def test_connect_registry_outage_bounces_back(self):
        """A failed registry read cannot mint a broken authorize URL."""
        client = _campus({
            ("GET", "/integrations/v1/"): _FakeResponse(
                503, {"error": {"code": "UNAVAILABLE"}}),
        })
        self._patch_client(client)
        self._signed_in("/profile/integrations/classroom/connect")
        response = self.main.get_classroom_connect()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            urlparse(response.headers["Location"]).path,
            "/profile/integrations")
        flashes = self.flask.get_flashed_messages(with_categories=True)
        self.assertEqual(flashes[0][0], "warning")

    def test_connect_replaces_stale_nonce(self):
        """A fresh Connect overwrites any stale nonce from an abandoned flow."""
        self._registry_client()
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

    def test_disconnect_requires_signin(self):
        """The disconnect route is login-protected (and POST-only)."""
        response = self.client.post(
            "/profile/integrations/classroom/disconnect")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_disconnect_rejects_get(self):
        """Disconnect is POST-only: no link prefetching deletes grants."""
        response = self.client.get(
            "/profile/integrations/classroom/disconnect")
        self.assertEqual(response.status_code, 405)


if __name__ == "__main__":
    unittest.main()
