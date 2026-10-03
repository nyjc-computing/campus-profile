"""Main program file for Campus Profile"""

import os
import secrets

import flask
from campus import flask_campus
from campus.common.utils import url as campus_url
from campus.model import User
from campus_python import Campus

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

    connections = [
        integrations.get_integration_status(client, provider_id, user.id)
        for provider_id in integrations.PROVIDERS
    ]

    unknown = [
        connection["title"]
        for connection in connections
        if connection["status"] == integrations.STATUS_UNKNOWN
    ]
    if unknown:
        flask.flash(
            "Could not determine the status of: " + ", ".join(unknown),
            "warning",
        )

    return flask.render_template("integrations.html", connections=connections)


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
    """
    nonce = secrets.token_urlsafe()
    flask.session[CLASSROOM_CONNECT_STATE] = nonce
    callback_url = campus_url.full_url_for(
        "get_classroom_connect_callback", connect_state=nonce
    )
    authorize_url = integrations.connect_authorize_url(
        client, "google.classroom", callback_url
    )
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
