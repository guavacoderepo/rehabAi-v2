"""Sign in / sign out."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services import users
from utils.auth import safe_next_url, start_session

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = users.authenticate(
            request.form.get("email"),
            request.form.get("password"),
        )

        if user is not None:
            start_session(users.session_payload(user))
            return redirect(
                safe_next_url(request.args.get("next"), url_for("main.dashboard"))
            )

        flash("Invalid email or password.")

    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
