"""
RehabAI — Flask application factory.

This file only wires the app together. All business logic lives in
`services/`, HTTP handling lives in `routes/`, and template helpers live
in `utils/`.
"""

import logging

from flask import Flask, render_template

import db as database
from config import Config
from routes import register_blueprints
from utils.auth import load_logged_in_user
from utils.template_helpers import register_template_helpers


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    database.init_app(app)
    register_template_helpers(app)
    register_blueprints(app)

    app.before_request(load_logged_in_user)

    @app.errorhandler(404)
    def not_found(error):
        return render_template("error.html", error=error), 404

    return app


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        database.ensure_database()

    app.run(debug=True)
