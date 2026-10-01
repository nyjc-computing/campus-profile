"""Main program file for Campus Profile"""

import os

from campus import flask_campus
from campus.model import User
from campus_python import Campus
import flask

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
    default_endpoint="get_profile_page"
) # Using default parameters

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


if __name__ == '__main__':
    debug()
    app.run(host="0.0.0.0", port=5000)
