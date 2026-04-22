"""Main program file for Campus Profile"""

import os

from campus import flask_campus
from campus.auth.oauth_proxy import __all__ as INTEGRATIONS_LIST
from campus.model import User
from campus_python import Campus, errors
import flask


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
    cur_integrations = []
    
    for provider in INTEGRATIONS_LIST:
        try:
            token = client.auth.credentials[provider][user.id].get().token
            if token:
                cur_integrations.append((provider, token.access_token))     
        except errors.NotFoundError as e:
            # No credentials found for this provider, skip it
            continue
        except errors.APIError as e:
            raise RuntimeError(
                f"Unhandled login error getting token for {provider}: "
                f"{str(e)}"
            )

    return flask.render_template("integrations.html", cur_integrations=cur_integrations)


if __name__ == '__main__':
    debug()
    app.run(host="0.0.0.0", port=5000)
    
