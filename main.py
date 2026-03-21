"""Main program file for Campus Profile"""

import os

import campus_python
import flask
from campus import flask_campus


app = flask.Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")

def debug():
    """Run to enable debug mode."""
    app.debug = True
    print("Running in debug mode!")

login_manager = flask_campus.OAuthLoginManager(default_endpoint="get_profile_page") # Using default parameters
login_manager.init_app(app)

@app.get("/profile/")
def get_profile_page():
    return flask.render_template('profile.html')

@app.get("/profile/integrations")
def get_integrations_page():
    return flask.render_template("integrations.html")


debug()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
    