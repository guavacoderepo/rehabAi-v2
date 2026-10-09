"""User accounts and authentication."""

from werkzeug.security import check_password_hash

from db import get_db


def get_user_by_email(email):
    return get_db().execute(
        """
        SELECT u.*, c.name AS clinic_name
        FROM users u
        LEFT JOIN clinics c ON c.id = u.clinic_id
        WHERE LOWER(u.email) = ?
        """,
        ((email or "").strip().lower(),),
    ).fetchone()


def authenticate(email, password):
    """Return the user row if the credentials are valid, else None."""

    user = get_user_by_email(email)

    if user is None:
        return None

    if not check_password_hash(user["password_hash"], password or ""):
        return None

    return user


def session_payload(user):
    """The subset of the user row that is stored in the session."""

    return {
        "user_id": user["id"],
        "username": f"{user['first_name']} {user['last_name']}".strip(),
        "email": user["email"],
        "role": user["role"],
        "clinic_id": user["clinic_id"],
        "clinic_name": user["clinic_name"],
    }
