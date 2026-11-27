"""My-events data behind a fake-data seam (#85).

Campus has no events service yet (the campus repo's
docs/api-gaps-and-planned-endpoints.md lists no events endpoints), so
this module is the single swap point: get_event_sections() reads
DEMO_EVENTS today. When a campus events service ships, this module's
fetch changes to the real per-user call — routes and templates stay
untouched. Like integrations.py, nothing here imports flask, so the
data layer is unit-testable on its own.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

# True while the seam serves demo fixtures; flip (and rewire the
# fetch) when a real events service feeds it. The template shows a
# "Demo data" notice off this flag, so the demo stays honest (#85).
DEMO_DATA = True

# Signup statuses (demo vocabulary; align with the future campus
# events service when it exists).
SIGNUP_CONFIRMED = "confirmed"
SIGNUP_PENDING = "pending"


@dataclass(frozen=True)
class Event:
    """One campus event as the page renders it."""

    id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    location: str = ""
    description: str = ""
    signup: str = SIGNUP_CONFIRMED
    attended: bool = False


def _at(days: int, hour: int) -> datetime:
    """`hour`-o'clock, `days` days from now.

    Relative dates keep the demo sensible forever — there is always an
    upcoming and an attended event no matter when the app runs.
    """
    day = datetime.now() + timedelta(days=days)
    return day.replace(hour=hour, minute=0, second=0, microsecond=0)


DEMO_EVENTS = [
    Event(
        id="class-day",
        title="Class Day",
        starts_at=_at(days=14, hour=8),
        ends_at=_at(days=14, hour=13),
        location="NYJC Hall",
        description="Whole-college celebration to close the year.",
    ),
    Event(
        id="badminton-friendly",
        title="Staff & Student Badminton Friendly",
        starts_at=_at(days=21, hour=17),
        ends_at=_at(days=21, hour=19),
        location="Sports Hall",
        description="Sign-up pending organiser confirmation.",
        signup=SIGNUP_PENDING,
    ),
    Event(
        id="cca-showcase",
        title="CCA Showcase",
        starts_at=_at(days=28, hour=9),
        ends_at=_at(days=28, hour=17),
        location="NYJC",
        description="Tour the co-curricular activity booths.",
    ),
    Event(
        id="bishan-visit",
        title="Service Learning — Bishan Home",
        starts_at=_at(days=-7, hour=14),
        ends_at=_at(days=-7, hour=17),
        location="Bishan Home",
        description="VIA session with the residents.",
        attended=True,
    ),
]

# Display vocabulary per section (Bootstrap badge classes + label),
# mirroring integrations.py's status labels.
_SECTION_BADGES = {
    "upcoming": ("bg-success", "Confirmed"),
    "pending": ("bg-warning text-dark", "Pending"),
    "attended": ("bg-secondary", "Attended"),
}


def get_event_sections(now: datetime | None = None) -> dict[str, list[dict]]:
    """Bucket events into the page's three sections of display cards.

    Upcoming: confirmed and still ahead, soonest first. Pending:
    sign-up awaiting organiser confirmation, soonest first. Attended:
    past events with an attended record, most recent first. Past
    events without an attended record are not the user's history and
    are left out.

    Swap point (#85): the body reads DEMO_EVENTS while no campus
    events service exists; when one ships, this becomes the per-user
    fetch — callers and templates do not change.
    """
    now = datetime.now() if now is None else now
    sections: dict[str, list[dict]] = {
        "upcoming": [],
        "pending": [],
        "attended": [],
    }
    for event in sorted(_all_events(), key=lambda ev: ev.starts_at):
        if event.ends_at >= now:
            if event.signup == SIGNUP_PENDING:
                sections["pending"].append(_card(event, "pending"))
            else:
                sections["upcoming"].append(_card(event, "upcoming"))
        elif event.attended:
            sections["attended"].append(_card(event, "attended"))
    sections["attended"].reverse()  # most recent first
    return sections


def _all_events() -> list[Event]:
    """The seam itself: demo fixtures today, a real fetch later (#85)."""
    return DEMO_EVENTS


def _card(event: Event, section: str) -> dict:
    """Build the display state for one event card (#85)."""
    badge, badge_label = _SECTION_BADGES[section]
    return {
        "title": event.title,
        "when": event.starts_at.strftime("%a %d %b %Y, %H:%M"),
        "location": event.location,
        "description": event.description,
        "badge": badge,
        "badge_label": badge_label,
        # A past event has no "add to calendar".
        "calendar_url": calendar_url(event) if section != "attended" else "",
    }


def calendar_url(event: Event) -> str:
    """Google Calendar template link for an event (#85).

    Timestamps are floating local times (no UTC offset): Google
    interprets them in the viewer's timezone, which is right for
    school events.
    """
    query = urlencode(
        {
            "action": "TEMPLATE",
            "text": event.title,
            "dates": f"{_stamp(event.starts_at)}/{_stamp(event.ends_at)}",
            "location": event.location,
            "details": event.description,
        }
    )
    return f"https://calendar.google.com/calendar/render?{query}"


def _stamp(value: datetime) -> str:
    """Compact Google Calendar datetime format (YYYYMMDDTHHMMSS)."""
    return value.strftime("%Y%m%dT%H%M%S")
