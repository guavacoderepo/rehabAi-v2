"""Public home page and the signed-in dashboard."""

from flask import Blueprint, current_app, g, redirect, render_template, request, url_for

from services import clinics
from services.dashboard import build_dashboard
from services.patients import ADMISSION_STATUSES
from utils.auth import login_required

bp = Blueprint("main", __name__)


@bp.route("/")
def home():
    """Public landing page. Signed-in users go straight to the dashboard."""

    if g.user:
        return redirect(url_for("main.dashboard"))

    return render_template("home.html")


@bp.route("/dashboard")
@login_required
def dashboard():
    clinic_id, clinic = clinics.resolve_scope(g.user, request.args.get("clinic"))

    status = request.args.get("status", "")
    if status not in ADMISSION_STATUSES:
        status = ""

    stats = build_dashboard(
        clinic_id=clinic_id,
        admission_status=status,
        recent_days=current_app.config["DASHBOARD_RECENT_DAYS"],
    )

    return render_template(
        "dashboard.html",
        stats=stats,
        clinic=clinic,
        scope_label=clinics.scope_label(g.user, clinic),
        clinic_options=clinics.list_clinics() if g.user["is_admin"] else [],
        status=status,
    )
