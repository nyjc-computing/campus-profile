"""Main program file for Campus Profile"""

import os

from campus_python import Campus
import flask
from campus import flask_campus
from campus.auth.oauth_proxy import __all__ as INTEGRATIONS_LIST
from campus_python.errors import AuthenticationError
from campus.model import User
import campus.common.env as env

# Debug: Check if HOSTNAME is available at import time
_import_time_hostname = None
try:
    _import_time_hostname = env.HOSTNAME
except AttributeError:
    _import_time_hostname = f"NOT AVAILABLE - keys: {list(env.keys())}"

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
    has_hostname_in_os = "HOSTNAME" in os.environ
    hostname_in_os = os.environ.get("HOSTNAME", "NOT SET")
    try:
        hostname_via_env = env.HOSTNAME
        env_hostname_works = True
        env_hostname_value = hostname_via_env
    except AttributeError as e:
        env_hostname_works = False
        env_hostname_value = str(e)

    # Check the url module's env reference
    from campus.common.utils import url
    url_env_module = getattr(url, 'env', None)
    url_env_id = id(url_env_module) if url_env_module else None
    main_env_id = id(env)

    return {
        "import_time_hostname": _import_time_hostname,
        "os_environ_has_HOSTNAME": has_hostname_in_os,
        "os_environ_HOSTNAME_value": hostname_in_os,
        "env_HOSTNAME_works": env_hostname_works,
        "env_HOSTNAME_value": env_hostname_value,
        "all_env_vars": {k: v for k, v in os.environ.items() if "HOST" in k.upper()},
        "module_ids": {
            "main_env_id": main_env_id,
            "url_env_id": url_env_id,
            "same_module": url_env_id == main_env_id,
        },
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
    
