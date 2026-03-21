"""Main program file for Campus Profile"""

import os

from campus_python import Campus
import flask
from campus import flask_campus


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

@app.get("/profile/")
@login_manager.login_required
def get_profile_page():
    """Profile page. Requires the user to be logged in already."""
    user_obj = flask.g.user
    
    return flask.render_template('profile.html', user_obj=user_obj)

@app.get("/profile/integrations")
@login_manager.login_required
def get_integrations_page():
    """Integrations page. Requires the user to be logged in already."""
    user_obj = flask.g.user

    return flask.render_template("integrations.html", user_obj=user_obj)


debug()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
    