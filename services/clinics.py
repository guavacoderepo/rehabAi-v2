"""Hospitals (clinics) and hospital-level data scoping.

Patients belong to a hospital through the clinician who registered them
(patients.created_by -> users.clinic_id). Clinicians only ever see their
own hospital; admins can see every hospital or pick one.
"""

from db import get_db


# A clinic id that can never exist, used to return "nothing" safely.
NO_ACCESS = -1


def list_clinics():
    return get_db().execute(
        "SELECT id, name, code FROM clinics ORDER BY name"
    ).fetchall()


def get_clinic(clinic_id):
    if clinic_id is None:
        return None

    return get_db().execute(
        "SELECT id, name, code FROM clinics WHERE id = ?",
        (clinic_id,),
    ).fetchone()


def resolve_scope(user, requested=None):
    """
    Work out which hospital the current request is allowed to see.

    Returns (clinic_id, clinic_row):
      * clinicians -> always their own hospital
      * admins     -> the requested hospital, or (None, None) for all
    """

    if not user.get("is_admin"):
        clinic_id = user.get("clinic_id")

        if clinic_id is None:
            return NO_ACCESS, None

        return clinic_id, get_clinic(clinic_id)

    try:
        requested_id = int(requested) if requested else None
    except (TypeError, ValueError):
        requested_id = None

    clinic = get_clinic(requested_id)

    if clinic is None:
        return None, None

    return clinic["id"], clinic


def scope_label(user, clinic):
    """Human-readable label for the current hospital scope."""

    if clinic is not None:
        return clinic["name"]

    return "All hospitals" if user.get("is_admin") else "No hospital assigned"
