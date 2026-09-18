import json
import math

from werkzeug.security import generate_password_hash

from model import (
    ITEMS,
    SCALES,
    ITEM_KEYS,
    DOMAINS,
    predict,
    interpret,
    domain_score,
)


# ---------------------------------------------------------------------------
# Demo clinics
# ---------------------------------------------------------------------------

SEED_CLINICS = [
    {
        "name": "Queen's Medical Centre",
        "code": "QMC",
        "level": 2,
    },
    {
        "name": "Luton and Dunstable Hospital",
        "code": "LUT",
        "level": 3,
    },
]


# ---------------------------------------------------------------------------
# Demo users
#
# clinic_id is assigned after the clinics have been created.
#
# The admin is a system-level user and therefore has no clinic.
# ---------------------------------------------------------------------------

SEED_USERS = [
    {
        "first_name": "System",
        "last_name": "Administrator",
        "email": "admin@hotmail.com",
        "password": "12345",
        "clinic_code": None,
        "role": "admin",
    },
    {
        "first_name": "Path",
        "last_name": "Xenophon",
        "email": "path@qmc.uk",
        "password": "12345",
        "clinic_code": "QMC",
        "role": "clinician",
    },
    {
        "first_name": "Jay",
        "last_name": "Ketherine",
        "email": "jay@lut.uk",
        "password": "12345",
        "clinic_code": "LUT",
        "role": "clinician",
    },
]


# ---------------------------------------------------------------------------
# 5 dummy patients
#
# `history` is a list of:
#     (assessment date, recovery profile)
#
# Profile:
#     0.0 = fully dependent
#     1.0 = independent
# ---------------------------------------------------------------------------

DUMMY_PATIENTS = [
    {
        "patient_id": "ROC-4821",
        "nhs_number": "943 721 6081",
        "first_name": "Margaret",
        "last_name": "Whitfield",
        "date_of_birth": "1958-04-14",
        "sex": "F",
        "primary_diagnosis": "Left MCA infarct",
        "admission_date": "2026-06-02",
        "admission_status": "active",
        "history": [
            ("2026-06-03", 0.24),
            ("2026-06-17", 0.33),
            ("2026-07-01", 0.45),
            ("2026-07-22", 0.58),
            ("2026-08-19", 0.66),
        ],
    },
    {
        "patient_id": "ROC-4835",
        "nhs_number": "927 415 3064",
        "first_name": "Daniel",
        "last_name": "Osei",
        "date_of_birth": "1985-09-22",
        "sex": "M",
        "primary_diagnosis": "Traumatic brain injury",
        "admission_date": "2026-06-14",
        "admission_status": "active",
        "history": [
            ("2026-06-15", 0.12),
            ("2026-07-02", 0.19),
            ("2026-07-28", 0.31),
            ("2026-08-25", 0.42),
        ],
    },
    {
        "patient_id": "ROC-4840",
        "nhs_number": "851 263 9475",
        "first_name": "Priya",
        "last_name": "Raghavan",
        "date_of_birth": "1971-02-11",
        "sex": "F",
        "primary_diagnosis": "Incomplete spinal cord injury",
        "admission_date": "2026-05-20",
        "admission_status": "active",
        "history": [
            ("2026-05-21", 0.38),
            ("2026-06-11", 0.51),
            ("2026-07-09", 0.63),
            ("2026-08-06", 0.74),
            ("2026-08-27", 0.79),
        ],
    },
    {
        "patient_id": "ROC-4852",
        "nhs_number": "734 592 8160",
        "first_name": "Kenneth",
        "last_name": "Ollerenshaw",
        "date_of_birth": "1953-11-03",
        "sex": "M",
        "primary_diagnosis": "Right pontine haemorrhage",
        "admission_date": "2026-07-01",
        "admission_status": "active",
        "history": [
            ("2026-07-02", 0.16),
            ("2026-07-23", 0.22),
            ("2026-08-13", 0.21),
            ("2026-08-30", 0.28),
        ],
    },
    {
        "patient_id": "ROC-4861",
        "nhs_number": "618 374 2059",
        "first_name": "Amelia",
        "last_name": "Croft",
        "date_of_birth": "1997-06-19",
        "sex": "F",
        "primary_diagnosis": "Guillain-Barré syndrome",
        "admission_date": "2026-07-18",
        "admission_status": "active",
        "history": [
            ("2026-07-19", 0.31),
            ("2026-08-08", 0.55),
            ("2026-08-28", 0.72),
        ],
    },
]


# ---------------------------------------------------------------------------
# Score generation
# ---------------------------------------------------------------------------

def make_scores(profile):
    """
    Build a plausible set of 28 item scores for a given recovery profile.

    0.0 = fully dependent
    1.0 = independent

    Handles binary NPDS items explicitly so they always satisfy
    the database constraints.
    """
    values = {}

    binary_items = {
        "npds_pressure_adm",
        "npds_specialing_adm",
    }

    for idx, item in enumerate(ITEMS):
        key = item["key"]
        s = SCALES[item["scale"]]

        jitter = (
            math.sin(idx * 12.9898 + profile * 78.233)
            * 43758.5453
        ) % 1

        p = max(
            0.0,
            min(
                1.0,
                profile + (jitter - 0.5) * 0.28,
            ),
        )

        # Binary NPDS items must be exactly 0 or 5.
        if key in binary_items:
            values[key] = 5 if p >= 0.5 else 0
            continue

        span = s["max"] - s["min"]

        if s["dir"] > 0:
            values[key] = s["min"] + round(p * span)
        else:
            values[key] = s["max"] - round(p * span)

    return values


def calculate_domain_scores(values):
    """Calculate domain scores (0-100) for all domains."""
    domains = {}

    for d in DOMAINS:
        domains[d["id"]] = round(
            domain_score(values, d["id"]) * 100
        )

    return domains


def get_walking_status(walk_prob):
    """
    Convert the model walking probability into a database-compatible
    walking status.
    """
    return "walking" if walk_prob >= 50 else "wheelchair"


# ---------------------------------------------------------------------------
# Clinics
# ---------------------------------------------------------------------------

def seed_clinics(db):
    """
    Create the demo clinics if they do not already exist.

    Returns:
        Dictionary mapping clinic codes to clinic IDs.
    """

    clinic_ids = {}

    for clinic in SEED_CLINICS:

        existing = db.execute(
            """
            SELECT id
            FROM clinics
            WHERE code = ?
            """,
            (clinic["code"],),
        ).fetchone()

        if existing:
            clinic_ids[clinic["code"]] = existing["id"]
            continue

        cur = db.execute(
            """
            INSERT INTO clinics (
                name,
                code,
                level
            )
            VALUES (?, ?, ?)
            """,
            (
                clinic["name"],
                clinic["code"],
                clinic["level"],
            ),
        )

        clinic_ids[clinic["code"]] = cur.lastrowid

    return clinic_ids


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def seed_users(db, clinic_ids):
    """
    Create the demo users if they do not already exist.

    The user's clinic is resolved from clinic_code.

    Admin users can have clinic_id = NULL.

    Returns:
        Dictionary mapping email addresses to user IDs.
    """

    user_ids = {}

    for user in SEED_USERS:

        existing = db.execute(
            """
            SELECT id
            FROM users
            WHERE LOWER(email) = LOWER(?)
            """,
            (user["email"],),
        ).fetchone()

        if existing:
            user_ids[user["email"]] = existing["id"]
            continue

        clinic_id = None

        if user["clinic_code"] is not None:
            clinic_id = clinic_ids[user["clinic_code"]]

        password_hash = generate_password_hash(
            user["password"]
        )

        cur = db.execute(
            """
            INSERT INTO users (
                first_name,
                last_name,
                email,
                password_hash,
                clinic_id,
                role
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user["first_name"],
                user["last_name"],
                user["email"],
                password_hash,
                clinic_id,
                user["role"],
            ),
        )

        user_ids[user["email"]] = cur.lastrowid

    return user_ids


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------

def insert_assessment(
    db,
    patient_id,
    user_id,
    patient_name,
    assessed_on,
    values,
    previous=None,
):
    """Compute, interpret and store one assessment."""

    pred = predict(values)

    if "domains" not in pred or not pred["domains"]:
        pred["domains"] = calculate_domain_scores(values)

    text = interpret(
        pred,
        previous,
        patient_name,
    )

    walking_status = get_walking_status(
        pred["walk_prob"]
    )

    columns = [
        "patient_id",
        "user_id",
        "assessed_on",
        "walking_status",
    ] + ITEM_KEYS + [
        "wpi",
        "walk_prob",
        "barrier_score",
        "interpretation",
    ]

    params = [
        patient_id,
        user_id,
        assessed_on,
        walking_status,
    ]

    params += [
        int(values[key])
        for key in ITEM_KEYS
    ]

    params += [
        pred["wpi"],
        pred["walk_prob"],
        pred["barrier_score"],
        json.dumps(
            {
                **text,
                "domains": pred["domains"],
            }
        ),
    ]

    db.execute(
        f"""
        INSERT INTO assessments
        ({', '.join(columns)})
        VALUES ({', '.join('?' * len(columns))})
        """,
        params,
    )

    return pred


# ---------------------------------------------------------------------------
# Seed database
# ---------------------------------------------------------------------------

def seed(db):
    """
    Populate an initialised database.

    Creates:
        - 2 clinics
        - 1 admin
        - 2 clinicians
        - 5 patients
        - assessments for all five patients

    Patient records are distributed between the two clinicians.

    Returns:
        (number_of_patients, number_of_assessments)
    """

    # ---------------------------------------------------------------
    # Create clinics
    # ---------------------------------------------------------------

    clinic_ids = seed_clinics(db)

    # ---------------------------------------------------------------
    # Create users
    # ---------------------------------------------------------------

    user_ids = seed_users(
        db,
        clinic_ids,
    )

    clinician_1_id = user_ids["path@qmc.uk"]
    clinician_2_id = user_ids["jay@lut.uk"]

    # ---------------------------------------------------------------
    # Create patients
    #
    # Alternate patient ownership between the two clinicians.
    # ---------------------------------------------------------------

    n_assessments = 0

    for index, p in enumerate(DUMMY_PATIENTS):

        # Patient 1 -> QMC clinician
        # Patient 2 -> Luton clinician
        # Patient 3 -> QMC clinician
        # Patient 4 -> Luton clinician
        # Patient 5 -> QMC clinician

        created_by = (
            clinician_1_id
            if index % 2 == 0
            else clinician_2_id
        )

        cur = db.execute(
            """
            INSERT INTO patients (
                patient_id,
                nhs_number,
                first_name,
                last_name,
                date_of_birth,
                sex,
                primary_diagnosis,
                admission_date,
                admission_status,
                created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p["patient_id"],
                p["nhs_number"],
                p["first_name"],
                p["last_name"],
                p["date_of_birth"],
                p["sex"],
                p["primary_diagnosis"],
                p["admission_date"],
                p["admission_status"],
                created_by,
            ),
        )

        patient_db_id = cur.lastrowid

        patient_name = (
            f"{p['first_name']} {p['last_name']}"
        )

        previous = None

        # -----------------------------------------------------------
        # Create assessments
        #
        # Each assessment is attributed to the same clinician
        # responsible for the patient.
        # -----------------------------------------------------------

        for assessed_on, profile in p["history"]:

            values = make_scores(profile)

            pred = insert_assessment(
                db=db,
                patient_id=patient_db_id,
                user_id=created_by,
                patient_name=patient_name,
                assessed_on=assessed_on,
                values=values,
                previous=previous,
            )

            previous = pred
            n_assessments += 1

    db.commit()

    return len(DUMMY_PATIENTS), n_assessments