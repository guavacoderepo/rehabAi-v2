"""Session handling and access-control helpers."""

from functools import wraps
from urllib.parse import urlparse

from flask import g, redirect, request, session, url_for


SESSION_KEYS = (
    "user_id",
    "username",
    "email",
    "role",
    "clinic_id",
    "clinic_name",
)


def load_logged_in_user():
    """Expose the signed-in user on `g.user` (or None) for every request."""

    if not session.get("user_id"):
        g.user = None
        return

    g.user = {key: session.get(key) for key in SESSION_KEYS}
    g.user["is_admin"] = g.user["role"] == "admin"


def start_session(payload):
    """Replace the current session with a freshly signed-in user."""

    session.clear()

    for key in SESSION_KEYS:
        session[key] = payload.get(key)


def login_required(view):
    """Redirect anonymous users to the login page."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return redirect(url_for("auth.login", next=request.path))

        return view(*args, **kwargs)

    return wrapped


def safe_next_url(target, fallback):
    """Only allow relative redirects back into this site."""

    if not target:
        return fallback

    parsed = urlparse(target)

    if parsed.scheme or parsed.netloc or not target.startswith("/"):
        return fallback

    return target
