"""Main program file for Campus Profile"""

import os
import secrets

import flask
from campus import flask_campus
from campus.common.utils import url as campus_url
from campus.model import User
from campus_python import Campus, errors

import integrations

app = flask.Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")

def debug():
    """Run to enable debug mode."""
    app.debug = True
    print("Running in debug mode!")

client = Campus(timeout=30, mode="server")

login_manager = flask_campus.OAuthLoginManager(
    campus_client=client,
    # Public landing page: logging out must not redirect into a
    # login-protected route, or the user is bounced straight back
    # into the OAuth flow.
    default_endpoint="get_index_page"
)

login_manager.init_app(app)


@app.template_filter("timestamp")
def timestamp(value, fmt: str = "%Y-%m-%d") -> str:
    """Format a campus DateTime (a string subclass) for display."""
    if not value:
        return "Unknown"
    try:
        return value.to_datetime().strftime(fmt)
    except AttributeError:
        return str(value)


@app.get("/")
def get_index_page():
    """The landing page for users who are not signed into the
    application yet.
    """
    return flask.render_template("index.html")

@app.get("/profile/")
@login_manager.login_required
def get_profile_page():
    """Profile page. Requires the user to be logged in already."""
    user: User = flask.g.user

    return flask.render_template('profile.html', user=user)

@app.get("/profile/integrations")
@login_manager.login_required
def get_integrations_page():
    """Integrations page. Requires the user to be logged in already."""
    user: User = flask.g.user

    try:
        registry = integrations.fetch_registry(client)
    except errors.APIError:
        # Without the registry there is nothing to render; the warning
        # beats a 500 for a transient campus outage.
        flask.flash(
            "Could not load the integrations catalog from Campus."
            " Try again in a moment.",
            "warning",
        )
        return flask.render_template("integrations.html", connections=[])

    try:
        connections = integrations.fetch_connections(client, user.id)
    except errors.APIError:
        # Degrade to "Status unavailable" rather than showing healthy
        # connections as "Not connected" while campus is unreachable.
        connections = None
        flask.flash(
            "Could not load your connection status from Campus."
            " Try again in a moment.",
            "warning",
        )

    cards = [
        integrations.build_card(
            entry,
            integrations.find_connection(connections or [], entry),
        )
        for entry in registry
    ]
    if connections is None:
        cards = [integrations.mark_unavailable(card) for card in cards]

    return flask.render_template("integrations.html", connections=cards)


@app.post("/profile/integrations/<slug>/disconnect")
@login_manager.login_required
def post_integration_disconnect(slug: str):
    """Disconnect an integration grant.

    campus.auth deletes the stored credential and token records and
    emits its own audit event; profile adds nothing. 404 (nothing was
    connected) is idempotent success, not an error (#25).
    """
    user: User = flask.g.user

    try:
        entry = integrations.registry_entry(
            integrations.fetch_registry(client), slug)
    except LookupError:
        flask.abort(404)
    except errors.APIError:
        flask.flash(
            "Could not reach Campus. Try again in a moment.",
            "warning",
        )
        return flask.redirect(flask.url_for("get_integrations_page"))

    if not entry.get("connectable"):
        # Only connectable integrations manage user grants here.
        flask.abort(404)

    try:
        disconnected = integrations.disconnect(client, entry, user.id)
    except errors.APIError:
        flask.flash(
            f"Could not disconnect {entry['title']}."
            " Try again in a moment.",
            "warning",
        )
        return flask.redirect(flask.url_for("get_integrations_page"))

    if disconnected:
        flask.flash(f"{entry['title']} disconnected", "success")
    else:
        flask.flash(f"{entry['title']} was not connected", "info")
    return flask.redirect(flask.url_for("get_integrations_page"))


# Single-use nonce for the classroom connect flow: it rides to
# campus.auth inside the target URL and must ride back on the callback.
# Binding it to the profile session means only a redirect this app
# initiated can mark the integration connected.
CLASSROOM_CONNECT_STATE = "classroom_connect_state"


@app.get("/profile/integrations/classroom/connect")
@login_manager.login_required
def get_classroom_connect():
    """Start the campus.auth connect flow for Google Classroom.

    Classroom tokens are stored campus-side only; profile just walks
    the user through Google consent (forced campus-side) and back.
    The authorize path comes from the integration registry (#25).
    """
    nonce = secrets.token_urlsafe()
    flask.session[CLASSROOM_CONNECT_STATE] = nonce
    callback_url = campus_url.full_url_for(
        "get_classroom_connect_callback", connect_state=nonce
    )
    try:
        authorize_url = integrations.connect_authorize_url(
            client, "classroom", callback_url
        )
    except errors.APIError:
        flask.flash(
            "Could not start the Classroom connect flow."
            " Try again in a moment.",
            "warning",
        )
        return flask.redirect(flask.url_for("get_integrations_page"))
    return flask.redirect(authorize_url)


@app.get("/profile/integrations/classroom/callback")
@login_manager.login_required
def get_classroom_connect_callback():
    """Land back from the classroom connect flow.

    campus.auth redirects to the target with its query params intact,
    so a genuine callback echoes this session's nonce. The failure
    paths (stale campus session, identity mismatch, consent denial)
    error on campus.auth and never reach this callback; a missing,
    stale or mismatching nonce is treated the same way -- not
    connected, never as success.
    """
    expected = flask.session.pop(CLASSROOM_CONNECT_STATE, None)
    received = flask.request.args.get("connect_state")
    if (
            not expected
            or not received
            or not secrets.compare_digest(
                received.encode(), expected.encode())
    ):
        flask.flash(
            "Classroom was not connected. Try Connect again; if Campus"
            " asked you to sign in during the flow, sign in to Campus"
            " Profile once more first.",
            "warning",
        )
        return flask.redirect(flask.url_for("get_integrations_page"))

    flask.flash("Classroom connected", "success")
    return flask.redirect(flask.url_for("get_integrations_page"))


if __name__ == '__main__':
    debug()
    app.run(host="0.0.0.0", port=5000)
