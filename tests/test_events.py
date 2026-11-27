"""My-events page tests (#85): the events seam and the blueprint view.

The signed-in base helper mirrors test_smoke.py's; it stays duplicated
(one small class) so this file reads standalone.
"""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import events


def _event(days: int, title: str = "Event", signup: str = "confirmed",
           attended: bool = False) -> events.Event:
    """A test event `days` days from now (ends 3 hours after start)."""
    return events.Event(
        id=title.lower().replace(" ", "-"),
        title=title,
        starts_at=datetime.now() + timedelta(days=days),
        ends_at=datetime.now() + timedelta(days=days, hours=3),
        location="NYJC",
        description="",
        signup=signup,
        attended=attended,
    )


class EventsSeamTest(unittest.TestCase):
    """Bucketing and card mapping in the events seam (#85)."""

    def _sections(self, events_list, now):
        original = events.DEMO_EVENTS
        events.DEMO_EVENTS = events_list
        self.addCleanup(setattr, events, "DEMO_EVENTS", original)
        return events.get_event_sections(now=now)

    def test_future_confirmed_lands_in_upcoming(self):
        now = datetime.now()
        result = self._sections([_event(5, "Class Day")], now)
        self.assertEqual(
            [card["title"] for card in result["upcoming"]], ["Class Day"])
        self.assertEqual(result["pending"], [])
        self.assertEqual(result["attended"], [])
        card = result["upcoming"][0]
        self.assertEqual((card["badge"], card["badge_label"]),
                         ("bg-success", "Confirmed"))

    def test_future_pending_lands_in_pending(self):
        now = datetime.now()
        result = self._sections(
            [_event(5, "Badminton", signup="pending")], now)
        self.assertEqual(result["upcoming"], [])
        self.assertEqual(
            [card["title"] for card in result["pending"]], ["Badminton"])
        self.assertEqual(result["pending"][0]["badge"],
                         "bg-warning text-dark")

    def test_past_attended_lands_most_recent_first(self):
        now = datetime.now()
        result = self._sections(
            [_event(-5, "Earlier Visit", attended=True),
             _event(-1, "Recent Visit", attended=True)], now)
        self.assertEqual([card["title"] for card in result["attended"]],
                         ["Recent Visit", "Earlier Visit"])
        # Past events have no "add to calendar".
        self.assertEqual(result["attended"][0]["calendar_url"], "")

    def test_past_without_attended_record_is_dropped(self):
        now = datetime.now()
        result = self._sections([_event(-3, "Missed It")], now)
        self.assertEqual(sum(len(v) for v in result.values()), 0)

    def test_upcoming_sorted_soonest_first(self):
        now = datetime.now()
        result = self._sections(
            [_event(9, "Later"), _event(2, "Sooner")], now)
        self.assertEqual([card["title"] for card in result["upcoming"]],
                         ["Sooner", "Later"])

    def test_calendar_url_shape(self):
        url = events.calendar_url(_event(5, "Class Day"))
        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "calendar.google.com")
        self.assertEqual(parsed.path, "/calendar/render")
        query = parse_qs(parsed.query)
        self.assertEqual(query["action"], ["TEMPLATE"])
        self.assertEqual(query["text"], ["Class Day"])
        self.assertEqual(query["location"], ["NYJC"])
        start, end = query["dates"][0].split("/")
        datetime.strptime(start, "%Y%m%dT%H%M%S")
        datetime.strptime(end, "%Y%m%dT%H%M%S")

    def test_demo_flag_is_on(self):
        self.assertTrue(events.DEMO_DATA)

    def test_shipped_fixtures_fill_upcoming_pending_and_attended(self):
        """The demo fixtures bucket sensibly no matter the run date."""
        result = events.get_event_sections()
        self.assertTrue(result["upcoming"])
        self.assertTrue(result["pending"])
        self.assertTrue(result["attended"])


class _SignedInTest(unittest.TestCase):
    """Base for view-level tests that need a signed-in g.user."""

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


class EventsPageTest(_SignedInTest):
    """GET /profile/events rendered against the demo seam (#85)."""

    def _page(self) -> str:
        self._signed_in("/profile/events")
        view = self.main.app.view_functions["events.get_events_page"]
        return view()

    def test_page_renders_sections_demo_notice_and_calendar_links(self):
        html = self._page()
        self.assertIn("My events", html)
        for heading in ("Upcoming", "Pending", "Attended"):
            self.assertIn(heading, html)
        self.assertIn("Demo data", html)
        # Fixtures guarantee an upcoming and an attended event.
        self.assertIn("Class Day", html)
        self.assertIn("Bishan Home", html)
        self.assertIn("https://calendar.google.com/calendar/render", html)

    def test_signed_in_navbar_links_to_the_page(self):
        self.assertIn('href="/profile/events"', self._page())

    def test_route_requires_signin(self):
        client = self.main.app.test_client()
        response = client.get("/profile/events")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            urlparse(response.headers["Location"]).path, "/profile/login")


if __name__ == "__main__":
    unittest.main()
