"""My-events page routes (#85): the profile's event blueprint.

The routes live on a blueprint — the first post-audit feature, the
point where main.py stops growing single-file. The data lives behind
the events seam; this module only renders.

Views are defined inside init_events() rather than at module level so
the login_manager instance can be injected from main: login_required
is an instance method, and importing it from main at module import
time would double-import main when the app is run as a script
(`python main.py`, the README's run command). The factory also makes
the wiring explicit — future feature modules should copy this pattern:
seam in `<feature>.py` (flask-free), routes in
`<feature>_views.py::init_<feature>(app, login_manager)`.
"""

import flask
from campus import flask_campus

import events

events_bp = flask.Blueprint("events", __name__)


def init_events(
    app: flask.Flask, login_manager: flask_campus.OAuthLoginManager
) -> None:
    """Define the blueprint's views and register them on the app.

    Called from main after login_manager exists; login_required wraps
    the view here, at definition time.
    """

    @events_bp.get("/profile/events")
    @login_manager.login_required
    def get_events_page():
        """My events: upcoming / pending / attended (demo data, #85)."""
        return flask.render_template(
            "events.html",
            sections=events.get_event_sections(),
            demo_data=events.DEMO_DATA,
        )

    app.register_blueprint(events_bp)
