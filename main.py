"""Main program file for Campus Profile"""

import campus_python
import flask
from campus import flask_campus

app = flask.Flask(__name__)

def debug():
    """Run to enable debug mode."""
    app.debug = True
    print("Running in debug mode!")

@app.route('/')
def index():
    return flask.render_template("index.html")

debug()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
    