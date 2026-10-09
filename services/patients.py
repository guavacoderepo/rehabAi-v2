"""Patient records: listing, filtering, lookup and create/update."""

import logging
import sqlite3
from dataclasses import asdict, dataclass, fields
from datetime import date

from werkzeug.exceptions import NotFound

from db import get_db
from services.bands import BAND_KEYS, band_info

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reference lists
# ---------------------------------------------------------------------------

# Diagnosis categories offered on the add/edit form (value, label).
DIAGNOSES = [
    ("Stroke: Infarct", "Infarct"),
    ("Stroke: Haemorrhagic", "Haemorrhagic"),
    ("Stroke: Sub-Arachnoid", "Sub-Arachnoid"),
    ("Stroke: Other", "Other stroke"),
    ("Trauma", "Trauma"),
    ("Inflammatory", "Inflammatory"),
    ("Anoxia", "Anoxia"),
    ("Tumour", "Tumour"),
    ("Toxic", "Toxic"),
]

GENDERS = [
    ("F", "Female"),
    ("M", "Male"),
    ("X", "Other / not specified"),
]

ADMISSION_STATUSES = ("active", "discharged")
WALKING_STATUSES = ("walking", "wheelchair")
TRENDS = ("improving", "declining", "stable", "unassessed")

SORTS = {
    "name": ("Name (A-Z)", "p.last_name, p.first_name"),
    "admitted_new": ("Newest admission", "p.admission_date DESC, p.last_name"),
    "admitted_old": ("Oldest admission", "p.admission_date ASC, p.last_name"),
    "wpi_high": ("Highest WPI first", "la.wpi IS NULL, la.wpi DESC"),
    "wpi_low": ("Lowest WPI first", "la.wpi IS NULL, la.wpi ASC"),
}

# A change in WPI smaller than this is treated as "stable".
TREND_TOLERANCE = 0.5
MFRA_THRESHOLD = 0.75

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def patient_name(patient):
    return f"{patient['first_name']} {patient['last_name']}".strip()


def patient_age(patient, on_date=None):
    """Age in whole years at `on_date` (default: admission date, else today)."""

    dob_raw = patient["date_of_birth"]

    if not dob_raw:
        return None

    dob = date.fromisoformat(str(dob_raw)[:10])

    if on_date is None:
        admitted = patient["admission_date"]
        on_date = date.fromisoformat(str(admitted)[:10]) if admitted else date.today()

    return (
        on_date.year
        - dob.year
        - ((on_date.month, on_date.day) < (dob.month, dob.day))
    )


def _valid_iso_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def _trend(change):
    if change is None:
        return "unassessed"
    if change < -TREND_TOLERANCE:
        return "improving"
    if change > TREND_TOLERANCE:
        return "declining"
    return "stable"


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

@dataclass
class PatientFilters:
    """Every filter the patient list supports, parsed from the query string."""

    q: str = ""
    diagnosis: str = ""
    admitted_from: str = ""
    admitted_to: str = ""
    walking_status: str = ""
    admission_status: str = ""
    band: str = ""
    trend: str = ""
    sort: str = "name"

    @classmethod
    def from_args(cls, args):
        raw = {f.name: (args.get(f.name) or "").strip() for f in fields(cls)}

        if raw["walking_status"] not in WALKING_STATUSES:
            raw["walking_status"] = ""
        if raw["admission_status"] not in ADMISSION_STATUSES:
            raw["admission_status"] = ""
        if raw["band"] not in BAND_KEYS:
            raw["band"] = ""
        if raw["trend"] not in TRENDS:
            raw["trend"] = ""
        if raw["sort"] not in SORTS:
            raw["sort"] = "name"

        for key in ("admitted_from", "admitted_to"):
            if raw[key] and not _valid_iso_date(raw[key]):
                raw[key] = ""

        return cls(**raw)

    @property
    def active_count(self):
        """How many filters (excluding search and sort) are applied."""

        return sum(
            1
            for name, value in asdict(self).items()
            if value and name not in ("q", "sort")
        )

    def as_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

# One row per patient with their hospital, first and latest assessment.
_PATIENT_SELECT = """
    SELECT
        p.*,
        u.first_name AS clinician_first_name,
        u.last_name  AS clinician_last_name,
        c.id         AS clinic_id,
        c.name       AS hospital_name,
        la.id              AS latest_id,
        la.assessed_on     AS latest_assessed_on,
        la.walking_status  AS latest_walking_status,
        la.wpi             AS latest_wpi,
        la.walk_prob       AS latest_walk_prob,
        la.barrier_score   AS latest_barrier_score,
        la.cluster         AS latest_cluster,
        fa.wpi             AS first_wpi,
        la.mfra_score      AS latest_mfra_score,
        (SELECT COUNT(*) FROM assessments x WHERE x.patient_id = p.id)
                           AS assessment_count
    FROM patients p
    JOIN users u        ON u.id = p.created_by
    LEFT JOIN clinics c ON c.id = u.clinic_id
    LEFT JOIN assessments la ON la.id = (
        SELECT id FROM assessments
        WHERE patient_id = p.id
        ORDER BY assessed_on DESC, id DESC
        LIMIT 1
    )
    LEFT JOIN assessments fa ON fa.id = (
        SELECT id FROM assessments
        WHERE patient_id = p.id
        ORDER BY assessed_on ASC, id ASC
        LIMIT 1
    )
"""


def _enrich(row):
    """Turn a patient row into a dict with computed display fields."""

    item = dict(row)

    item["name"] = patient_name(row)
    item["age"] = patient_age(row, on_date=date.today())
    item["clinician_name"] = (
        f"{row['clinician_first_name']} {row['clinician_last_name']}".strip()
    )

    has_latest = row["latest_wpi"] is not None

    # WPI change since the first assessment. Negative = improvement.
    item["wpi_change"] = (
        round(row["latest_wpi"] - row["first_wpi"], 2)
        if has_latest and row["assessment_count"] > 1
        else None
    )

    item["trend"] = (
        _trend(item["wpi_change"])
        if has_latest and item["wpi_change"] is not None
        else ("stable" if has_latest else "unassessed")
    )

    item["band"] = band_info(row["latest_wpi"])

    # Derived MFRA fall-risk flag. Threshold lives in one place.
    item["latest_mfra_score"] = row["latest_mfra_score"]

    return item


def list_patients(clinic_id=None, filters=None):
    """
    Patients visible in `clinic_id` (None = every hospital), filtered and
    sorted according to `filters`.
    """

    filters = filters or PatientFilters()

    where = []
    params = []

    if clinic_id is not None:
        where.append("u.clinic_id = ?")
        params.append(clinic_id)

    if filters.q:
        like = f"%{filters.q.lower()}%"
        where.append(
            """(
                LOWER(p.patient_id) LIKE ?
                OR REPLACE(p.nhs_number, ' ', '') LIKE REPLACE(?, ' ', '')
                OR LOWER(p.first_name || ' ' || p.last_name) LIKE ?
                OR LOWER(p.diag_std_subcat) LIKE ?
            )"""
        )
        params.extend([like, like, like, like])

    if filters.diagnosis:
        where.append("p.diag_std_subcat = ?")
        params.append(filters.diagnosis)

    if filters.admitted_from:
        where.append("p.admission_date >= ?")
        params.append(filters.admitted_from)

    if filters.admitted_to:
        where.append("p.admission_date <= ?")
        params.append(filters.admitted_to)

    if filters.admission_status:
        where.append("p.admission_status = ?")
        params.append(filters.admission_status)

    if filters.walking_status:
        where.append("la.walking_status = ?")
        params.append(filters.walking_status)

    sql = _PATIENT_SELECT

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY " + SORTS[filters.sort][1]

    people = [_enrich(row) for row in get_db().execute(sql, params).fetchall()]

    # Band and trend depend on model thresholds, so filter them in Python.
    if filters.band:
        people = [p for p in people if p["band"]["key"] == filters.band]

    if filters.trend:
        people = [p for p in people if p["trend"] == filters.trend]

    return people


def count_patients(clinic_id=None):
    sql = """
        SELECT COUNT(*)
        FROM patients p
        JOIN users u ON u.id = p.created_by
    """
    params = []

    if clinic_id is not None:
        sql += " WHERE u.clinic_id = ?"
        params.append(clinic_id)

    return get_db().execute(sql, params).fetchone()[0]


def list_diagnoses(clinic_id=None):
    """Distinct diagnoses actually recorded, for the filter dropdown."""

    sql = """
        SELECT DISTINCT p.diag_std_subcat
        FROM patients p
        JOIN users u ON u.id = p.created_by
    """
    params = []

    if clinic_id is not None:
        sql += " WHERE u.clinic_id = ?"
        params.append(clinic_id)

    sql += " ORDER BY p.diag_std_subcat"

    return [row[0] for row in get_db().execute(sql, params).fetchall()]


def get_patient(patient_code, clinic_id=None):
    """
    Fetch one patient by their public patient number.

    Raises 404 if the patient does not exist OR belongs to a hospital
    outside `clinic_id`, so records in other hospitals are not revealed.
    """

    sql = _PATIENT_SELECT + " WHERE p.patient_id = ?"
    params = [patient_code]

    if clinic_id is not None:
        sql += " AND u.clinic_id = ?"
        params.append(clinic_id)

    row = get_db().execute(sql, params).fetchone()

    if row is None:
        raise NotFound(f"No patient with ID {patient_code}")

    return _enrich(row)


def get_history(patient_db_id):
    """All assessments for a patient, oldest first."""

    return get_db().execute(
        """
        SELECT *
        FROM assessments
        WHERE patient_id = ?
        ORDER BY assessed_on, id
        """,
        (patient_db_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Create / update
# ---------------------------------------------------------------------------

_EDITABLE_ON_UPDATE = (
    "first_name",
    "last_name",
    "date_of_birth",
    "diag_std_subcat",
)

_FORM_FIELDS = (
    "patient_id",
    "nhs_number",
    "first_name",
    "last_name",
    "date_of_birth",
    "patient_gender",
    "diag_std_subcat",
    "admission_date",
)


def parse_patient_form(form, existing=None):
    """
    Read and validate the add/edit form.

    When editing, identifiers and admission details are locked and always
    taken from the existing record, whatever the browser sends.

    Returns (data, errors).
    """

    data = {key: (form.get(key) or "").strip() for key in _FORM_FIELDS}

    if existing is not None:
        for key in _FORM_FIELDS:
            if key not in _EDITABLE_ON_UPDATE:
                data[key] = existing[key]

    errors = []

    missing = [key for key, value in data.items() if not value]
    if missing:
        errors.append("Please complete all required fields.")

    if data["patient_gender"] and data["patient_gender"] not in dict(GENDERS):
        errors.append("Please select a valid sex.")

    for key, label in (
        ("date_of_birth", "date of birth"),
        ("admission_date", "admission date"),
    ):
        if data[key] and not _valid_iso_date(data[key]):
            errors.append(f"Please enter a valid {label}.")

    if (
        _valid_iso_date(data["date_of_birth"])
        and _valid_iso_date(data["admission_date"])
        and data["date_of_birth"] > data["admission_date"]
    ):
        errors.append("Date of birth must be before the admission date.")

    return data, errors


def create_patient(data, created_by):
    """Insert a new patient. Returns (ok, error_message)."""

    db = get_db()

    try:
        db.execute(
            """
            INSERT INTO patients (
                patient_id, nhs_number, first_name, last_name,
                date_of_birth, patient_gender, diag_std_subcat,
                admission_date, admission_status, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                data["patient_id"],
                data["nhs_number"],
                data["first_name"],
                data["last_name"],
                data["date_of_birth"],
                data["patient_gender"],
                data["diag_std_subcat"],
                data["admission_date"],
                created_by,
            ),
        )
        db.commit()

    except sqlite3.IntegrityError as exc:
        db.rollback()
        logger.warning("Could not create patient %s: %s", data["patient_id"], exc)
        return False, "A patient with this patient number or NHS number already exists."

    return True, None


def update_patient(patient, data):
    """Update the editable fields of an existing patient."""

    db = get_db()

    assignments = ", ".join(f"{key} = ?" for key in _EDITABLE_ON_UPDATE)
    params = [data[key] for key in _EDITABLE_ON_UPDATE] + [patient["id"]]

    db.execute(f"UPDATE patients SET {assignments} WHERE id = ?", params)
    db.commit()


def diagnosis_choices(current=None):
    """Form choices, making sure the patient's existing value is included."""

    choices = list(DIAGNOSES)

    if current and current not in dict(choices):
        choices.insert(0, (current, current))

    return choices
