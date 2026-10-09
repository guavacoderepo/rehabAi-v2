"""HTTP routes, grouped into blueprints."""

from routes.assessments import bp as assessments_bp
from routes.auth import bp as auth_bp
from routes.main import bp as main_bp
from routes.patients import bp as patients_bp


def register_blueprints(app):
    for blueprint in (main_bp, auth_bp, patients_bp, assessments_bp):
        app.register_blueprint(blueprint)
