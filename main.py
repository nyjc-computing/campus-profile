"""Main program file for Campus Profile"""

import os

from campus_python import Campus
import flask
from campus import flask_campus
from campus.auth.oauth_proxy import __all__ as INTEGRATIONS_LIST
from campus_python.errors import AuthenticationError
from campus.model import User


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
    """The landing page for users who are not signed into the application yet."""
    return flask.render_template("index.html")

@app.get("/debug/env")
def debug_env():
    """Debug endpoint to check environment variables."""
    import campus.common.env as env
    has_hostname_in_os = "HOSTNAME" in os.environ
    hostname_in_os = os.environ.get("HOSTNAME", "NOT SET")
    try:
        hostname_via_env = env.HOSTNAME
        env_hostname_works = True
        env_hostname_value = hostname_via_env
    except AttributeError as e:
        env_hostname_works = False
        env_hostname_value = str(e)

    return {
        "os_environ_has_HOSTNAME": has_hostname_in_os,
        "os_environ_HOSTNAME_value": hostname_in_os,
        "env_HOSTNAME_works": env_hostname_works,
        "env_HOSTNAME_value": env_hostname_value,
        "all_env_vars": {k: v for k, v in os.environ.items() if "HOST" in k.upper()},
    }

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
            token = client.auth.get_token(provider) # user_id is automatically provided in function
            cur_integrations.append((provider, token.access_token))
        except AuthenticationError as e:
            print(e)

    return flask.render_template("integrations.html", cur_integrations=cur_integrations)


if __name__ == '__main__':
    debug()
    app.run(host="0.0.0.0", port=5000)
    
