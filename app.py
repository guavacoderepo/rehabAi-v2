import json
import os
from datetime import date, datetime
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.security import check_password_hash
import db as database
from model import (
    DOMAIN_VIEW,
    DOMAINS,
    ITEM_KEYS,
    explain_patient,
    wpi_barrier_class,
    wpi_barrier_var,
    interpret,
    predict,
    wpi_barrier_band,
)

app = Flask(__name__)

app.config.from_mapping(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-key-change-me"),
    DATABASE=database.DB_PATH,
)

database.init_app(app)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

@app.template_filter("age")
def calculate_age(dob):
    if not dob:
        return None

    if isinstance(dob, str):
        dob = datetime.strptime(dob, "%Y-%m-%d").date()

    today = date.today()

    return (
        today.year
        - dob.year
        - ((today.month, today.day) < (dob.month, dob.day))
    )

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("username"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def load_user():
    g.username = session.get("username")
    g.email = session.get("email")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    """
    If the user is already signed in, take them to the patient list.
    Otherwise show the public home page explaining the concepts.
    """
    if session.get("username"):
        return redirect(url_for("patients"))

    return render_template("home.html")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        conn = database.get_db()

        # ---------------------------------------------------------------
        # 1. Check registered clinicians first
        # ---------------------------------------------------------------
        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE LOWER(email) = ?
            """,
            (email,),
        ).fetchone()

        if user is not None:

            # Registered user found - verify password
            if check_password_hash(
                user["password_hash"],
                password,
            ):
                session.clear()

                session["clinician_id"] = user["id"]
                session["username"] = (
                    f"{user['first_name']} "
                    f"{user['last_name']}"
                ).strip()
                session["email"] = user["email"]
                session["role"] = user["role"]

                return redirect(
                    request.args.get("next")
                    or url_for("patients")
                )

            # Email exists but password is wrong
            flash("Invalid email or password.")
            return render_template(
                "login.html",
                login_role="Clinician",
            )

        flash("Invalid email or password.")

    return render_template(
        "login.html",
        login_role="Clinician",
    )

@app.route("/patients")
@login_required
def patients():
    conn = database.get_db()

    q = (request.args.get("q") or "").strip()
    flt = request.args.get("filter", "all")

    rows = conn.execute(
        """
        SELECT *
        FROM patients
        ORDER BY last_name, first_name
        """
    ).fetchall()

    people = []

    today = date.today()

    for r in rows:
        history = conn.execute(
            """
            SELECT *
            FROM assessments
            WHERE patient_id = ?
            ORDER BY assessed_on
            """,
            (r["id"],),
        ).fetchall()

        patient = dict(r)

        # Patient has no assessment yet
        if not history:
            people.append(
                {
                    "row": patient,
                    "latest": None,
                    "delta": 0,
                    "trend": [],
                    "count": 0,
                }
            )
            continue

        latest = history[-1]
        first = history[0]

        people.append(
            {
                "row": patient,
                "latest": latest,
                "delta": first["wpi"] - latest["wpi"],
                "trend": [h["wpi"] for h in history],
                "count": len(history),
            }
        )

    # Patients with the highest barrier burden.
    needs_review = sum(
        1
        for p in people
        if p["latest"] is not None
        and wpi_barrier_band(p["latest"]["wpi"])
        == "Higher barrier burden"
    )

    # Search
    if q:
        ql = q.lower()

        filtered_people = []

        for p in people:
            row = p["row"]

            full_name = (
                f"{row['first_name']} {row['last_name']}"
            )

            searchable = " ".join(
                [
                    str(row.get("patient_id") or ""),
                    str(row.get("nhs_number") or ""),
                    full_name,
                    str(row.get("primary_diagnosis") or "")
                ]
            ).lower()

            if ql in searchable:
                filtered_people.append(p)

        people = filtered_people

    # Filter: higher barrier burden
    if flt == "high":
        people = [
            p
            for p in people
            if p["latest"] is not None
            and wpi_barrier_band(p["latest"]["wpi"])
            == "Higher barrier burden"
        ]

    # Filter: improving barrier burden
    elif flt == "improving":
        people = [
            p
            for p in people
            if p["latest"] is not None
            and p["delta"] > 0
        ]

    return render_template(
        "patients.html",
        people=people,
        q=q,
        filter=flt,
        total=len(rows),
        needs_review=needs_review,
        today=today,
    )


@app.route("/patients/add", methods=["GET", "POST"])
@login_required
def add_patient():

    if request.method == "POST":
        patient_id = (request.form.get("patient_id") or "").strip()
        nhs_number = (request.form.get("nhs_number") or "").strip()
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        date_of_birth = request.form.get("date_of_birth")
        sex = request.form.get("sex")
        primary_diagnosis = (
            request.form.get("primary_diagnosis") or ""
        ).strip()
        admission_date = request.form.get("admission_date")
        admission_status = "active"
        created_by = session.get("clinician_id")


        if not all([
            patient_id,
            nhs_number,
            first_name,
            last_name,
            date_of_birth,
            sex,
            primary_diagnosis,
            admission_date,
            admission_status,
            created_by,
        ]):
            flash("Please complete all required fields.")
            return render_template("add_patient.html")

        db = database.get_db()

        try:
            db.execute(
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
                ),
            )

            db.commit()

        except Exception as e:
            db.rollback()
            print(type(e).__name__) 
            print(str(e))
            flash(
                "A patient with this patient number or NHS number already exists."
            )
            return render_template("add_patient.html")

        flash("Patient added successfully.")
        return redirect(
            url_for("patient", patient_id=patient_id)
        )

    return render_template("add_patient.html")

@app.route(
    "/patients/<patient_id>/edit",
    methods=["GET", "POST"],
)
@login_required
def edit_patient(patient_id):

    p = _get_patient(patient_id)

    if not p:
        flash("Patient not found.")
        return redirect(url_for("patients"))

    if request.method == "POST":

        patient_number = request.form.get("patient_id", "").strip()
        nhs_number = request.form.get("nhs_number", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        date_of_birth = request.form.get("date_of_birth", "").strip()
        sex = request.form.get("sex", "").strip()
        primary_diagnosis = request.form.get(
            "primary_diagnosis",
            "",
        ).strip()
        admission_date = request.form.get(
            "admission_date",
            "",
        ).strip()

        if not all([
            patient_number,
            nhs_number,
            first_name,
            last_name,
            date_of_birth,
            sex,
            primary_diagnosis,
            admission_date,
        ]):
            flash("Please complete all required fields.")

            return render_template(
                "add_patient.html",
                p=p,
                editing=True,
            )

        if sex not in ("F", "M", "X"):
            flash("Please select a valid sex.")

            return render_template(
                "add_patient.html",
                p=p,
                editing=True,
            )

        db = database.get_db()

        # Check that another patient is not already using the
        # same patient number or NHS number.
        duplicate = db.execute(
            """
            SELECT id
            FROM patients
            WHERE (patient_id = ? OR nhs_number = ?)
              AND id != ?
            """,
            (
                patient_number,
                nhs_number,
                p["id"],
            ),
        ).fetchone()

        if duplicate:
            flash(
                "Another patient already uses that patient number "
                "or NHS number."
            )

            return render_template(
                "add_patient.html",
                p=p,
                editing=True,
            )

        db.execute(
            """
            UPDATE patients
            SET
                patient_id = ?,
                nhs_number = ?,
                first_name = ?,
                last_name = ?,
                date_of_birth = ?,
                sex = ?,
                primary_diagnosis = ?,
                admission_date = ?
            WHERE id = ?
            """,
            (
                patient_number,
                nhs_number,
                first_name,
                last_name,
                date_of_birth,
                sex,
                primary_diagnosis,
                admission_date,
                p["id"],
            ),
        )

        db.commit()

        flash("Patient details updated successfully.")

        return redirect(
            url_for(
                "patient",
                patient_id=patient_number,
            )
        )

    return render_template(
        "add_patient.html",
        p=p,
        editing=True,
    )

# ---------------------------------------------------------------------------
# Patient helpers
# ---------------------------------------------------------------------------
def _get_patient(patient_id):
    row = database.get_db().execute(
        """
        SELECT *
        FROM patients
        WHERE patient_id = ?
        """,
        (patient_id,),
    ).fetchone()

    if row is None:
        from werkzeug.exceptions import NotFound

        raise NotFound(
            f"No patient with ID {patient_id}"
        )

    return row


def _history(patient_db_id):
    return database.get_db().execute(
        """
        SELECT *
        FROM assessments
        WHERE patient_id = ?
        ORDER BY assessed_on
        """,
        (patient_db_id,),
    ).fetchall()


def _clinician(patient_db_id):
    db = database.get_db()

    return db.execute(
        """
        SELECT
            u.id,
            u.first_name,
            u.last_name,
            u.email,
            u.role,
            c.name AS hospital_name,
            c.code AS hospital_code
        FROM patients p
        JOIN users u
            ON u.id = p.created_by
        LEFT JOIN clinics c
            ON c.id = u.clinic_id
        WHERE p.id = ?
        """,
        (patient_db_id,),
    ).fetchone()

def _patient_name(patient):
    return f"{patient['first_name']} {patient['last_name']}".strip()




# ---------------------------------------------------------------------------
# One patient
# ---------------------------------------------------------------------------
@app.route("/patients/<patient_id>")
@login_required
def patient(patient_id):
    p = _get_patient(patient_id)

    if not p:
        flash("Patient not found.")
        return redirect(url_for("patients"))

    history = _history(p["id"])

    # ---------------------------------------------------------
    # Clinician + hospital
    # ---------------------------------------------------------

    clinician = _clinician(p["id"])

    clinician_name = None
    hospital_name = None

    if clinician:
        clinician_name = (
            f"{clinician['first_name']} {clinician['last_name']}"
        ).strip()

        hospital_name = clinician["hospital_name"]

    latest = history[-1] if history else None

    delta = 0

    if len(history) > 1:
        delta = history[-1]["wpi"] - history[0]["wpi"]

    chart = []

    for h in history:
        chart.append(
            {
                "date": h["assessed_on"],
                "wpi": h["wpi"],
                "walk": h["walk_prob"],
            }
        )

    entries = []

    for index, row in enumerate(reversed(history), start=1):

        text = {}

        try:
            if row["interpretation"]:
                text = json.loads(row["interpretation"])
        except (TypeError, ValueError, json.JSONDecodeError):
            text = {}

        entries.append(
            {
                "row": row,
                "text": text,
                "index": len(history) - index + 1,
                "is_latest": index == 1,
            }
        )

    return render_template(
        "patient.html",
        p=p,
        history=history,
        latest=latest,
        delta=delta,
        chart=chart,
        entries=entries,
        domains=DOMAIN_VIEW,
        clinician_name=clinician_name,
        hospital_name=hospital_name,
    )


# ---------------------------------------------------------------------------
# New prediction
# ---------------------------------------------------------------------------
@app.route(
    "/patients/<patient_id>/predict",
    methods=["GET", "POST"],
)
@login_required
def new_prediction(patient_id):
    p = _get_patient(patient_id)

    if not p:
        flash("Patient not found.")
        return redirect(url_for("patients"))

    edit_id = request.args.get("edit", type=int)

    history = _history(p["id"])

    # -------------------------------------------------------------------
    # If editing, load the existing assessment
    # -------------------------------------------------------------------

    editing = None

    if edit_id:
        editing = database.get_db().execute(
            """
            SELECT *
            FROM assessments
            WHERE id = ?
              AND patient_id = ?
            """,
            (
                edit_id,
                p["id"],
            ),
        ).fetchone()

        if editing is None:
            flash("Assessment not found.")
            return redirect(
                url_for(
                    "patient",
                    patient_id=patient_id,
                )
            )

    # -------------------------------------------------------------------
    # POST — create or update assessment
    # -------------------------------------------------------------------

    if request.method == "POST":

        values = {}
        errors = []

        # ---------------------------------------------------------------
        # Get walking status
        # ---------------------------------------------------------------

        walking_status = request.form.get("walking_status")

        if walking_status not in (
            "walking",
            "wheelchair",
        ):
            errors.append("walking_status")

        # ---------------------------------------------------------------
        # Get 28 assessment items
        # ---------------------------------------------------------------

        for key in ITEM_KEYS:
            raw = request.form.get(key)

            if raw is None or raw == "":
                errors.append(key)
                continue

            try:
                values[key] = int(raw)
            except ValueError:
                errors.append(key)

        # ---------------------------------------------------------------
        # Assessment date
        # ---------------------------------------------------------------

        assessed_on = (
            request.form.get("assessed_on")
            or date.today().isoformat()
        )

        # ---------------------------------------------------------------
        # Validation errors
        # ---------------------------------------------------------------

        if errors:

            if "walking_status" in errors:
                flash(
                    "Please select the patient's current walking status."
                )
            else:
                flash(
                    f"{len(errors)} of 28 items still need a score."
                )

            return render_template(
                "predict.html",
                p=p,
                domains=DOMAIN_VIEW,
                values=values,
                assessed_on=assessed_on,
                walking_status=walking_status,
                previous=history[-1] if history else None,
                editing=editing,
            )

        # ---------------------------------------------------------------
        # Get logged-in user
        # ---------------------------------------------------------------

        user_id = session.get("clinician_id")

        if not user_id:
            flash(
                "Your session has expired. Please log in again."
            )
            return redirect(url_for("login"))

        # ---------------------------------------------------------------
        # Run model prediction
        # ---------------------------------------------------------------

        pred = predict(values)

        # ---------------------------------------------------------------
        # Determine previous assessment
        #
        # When editing, do not use the assessment being edited as the
        # "previous" assessment.
        # ---------------------------------------------------------------

        previous = None

        if edit_id:
            previous_candidates = [
                dict(row)
                for row in history
                if row["id"] != edit_id
            ]

            if previous_candidates:
                previous = previous_candidates[-1]

        elif history:
            previous = dict(history[-1])

        # ---------------------------------------------------------------
        # Generate interpretation
        # ---------------------------------------------------------------

        patient_name = _patient_name(p)

        text = interpret(
            pred,
            previous,
            patient_name,
        )

        interpretation = json.dumps(
            {
                **text,
                "domains": pred.get(
                    "domains",
                    {},
                ),
            }
        )

        # ---------------------------------------------------------------
        # Save assessment
        #
        # EDIT  → UPDATE existing row
        # NEW   → INSERT new row
        # ---------------------------------------------------------------

        conn = database.get_db()

        if edit_id:

            columns = (
                [
                    "user_id",
                    "assessed_on",
                    "walking_status",
                ]
                + ITEM_KEYS
                + [
                    "wpi",
                    "walk_prob",
                    "barrier_score",
                    "interpretation",
                ]
            )

            params = (
                [
                    user_id,
                    assessed_on,
                    walking_status,
                ]
                + [values[k] for k in ITEM_KEYS]
                + [
                    pred["wpi"],
                    pred["walk_prob"],
                    pred["barrier_score"],
                    interpretation,
                    edit_id,
                    p["id"],
                ]
            )

            set_clause = ", ".join(
                f"{column} = ?"
                for column in columns
            )

            conn.execute(
                f"""
                UPDATE assessments
                SET {set_clause}
                WHERE id = ?
                  AND patient_id = ?
                """,
                params,
            )

            conn.commit()

            return redirect(
                url_for(
                    "assessment",
                    patient_id=patient_id,
                    assessment_id=edit_id,
                )
            )

        # ----------------------------------------------------------------
        # NEW ASSESSMENT
        # ----------------------------------------------------------------

        columns = (
            [
                "patient_id",
                "user_id",
                "assessed_on",
                "walking_status",
            ]
            + ITEM_KEYS
            + [
                "wpi",
                "walk_prob",
                "barrier_score",
                "interpretation",
            ]
        )

        params = (
            [
                p["id"],
                user_id,
                assessed_on,
                walking_status,
            ]
            + [values[k] for k in ITEM_KEYS]
            + [
                pred["wpi"],
                pred["walk_prob"],
                pred["barrier_score"],
                interpretation,
            ]
        )

        placeholders = ", ".join(
            "?" for _ in columns
        )

        cur = conn.execute(
            f"""
            INSERT INTO assessments
            ({", ".join(columns)})
            VALUES ({placeholders})
            """,
            params,
        )

        conn.commit()

        return redirect(
            url_for(
                "assessment",
                patient_id=patient_id,
                assessment_id=cur.lastrowid,
            )
        )

    # -------------------------------------------------------------------
    # GET — populate the form
    # -------------------------------------------------------------------

    values = {}
    walking_status = None
    assessed_on = date.today().isoformat()

    # -------------------------------------------------------------------
    # Editing an existing assessment
    # -------------------------------------------------------------------

    if editing:

        for key in ITEM_KEYS:
            values[key] = editing[key]

        walking_status = editing["walking_status"]
        assessed_on = editing["assessed_on"]

    # -------------------------------------------------------------------
    # New assessment with "Score again" / prefill
    # -------------------------------------------------------------------

    elif request.args.get("prefill") and history:

        last = history[-1]

        for key in ITEM_KEYS:
            values[key] = last[key]

        walking_status = last["walking_status"]

        # Keep today's date when creating a new assessment.
        assessed_on = date.today().isoformat()

    # -------------------------------------------------------------------
    # Render the same prediction page
    # -------------------------------------------------------------------

    return render_template(
        "predict.html",
        p=p,
        domains=DOMAIN_VIEW,
        values=values,
        walking_status=walking_status,
        assessed_on=assessed_on,
        previous=history[-1] if history else None,
        editing=editing,
    )

# ---------------------------------------------------------------------------
# Assessment result
# ---------------------------------------------------------------------------
@app.route(
    "/patients/<patient_id>/a/<int:assessment_id>"
)
@login_required
def assessment(patient_id, assessment_id):
    p = _get_patient(patient_id)

    a = database.get_db().execute(
        """
        SELECT *
        FROM assessments
        WHERE id = ?
          AND patient_id = ?
        """,
        (
            assessment_id,
            p["id"],
        ),
    ).fetchone()

    if a is None:
        from werkzeug.exceptions import NotFound

        raise NotFound(
            "No such assessment for this patient"
        )

    history = _history(p["id"])

    previous = None

    for h in history:
        if h["id"] == a["id"]:
            break

        previous = h

    # Get the 28 clinical assessment values
    values = {
        key: a[key]
        for key in ITEM_KEYS
    }

    # Run SHAP explanation for this assessment
    shap_result = explain_patient(values)

    text = json.loads(a["interpretation"])

    return render_template(
        "result.html",
        p=p,
        a=a,
        text=text,
        shap=shap_result,
        previous=previous,
        domains=DOMAINS,
    )


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------
@app.template_filter("longdate")
def longdate(iso):
    import platform

    date_obj = datetime.fromisoformat(
        str(iso)[:10]
    )

    if platform.system() == "Windows":
        return date_obj.strftime("%#d %B %Y")

    return date_obj.strftime("%-d %B %Y")


@app.template_filter("shortdate")
def shortdate(iso):
    return datetime.fromisoformat(
        str(iso)[:10]
    ).strftime("%d %b")


@app.template_filter("ago")
def ago(iso):
    days = (
        date.today()
        - date.fromisoformat(str(iso)[:10])
    ).days

    if days <= 0:
        return "today"

    if days == 1:
        return "yesterday"

    if days < 7:
        return f"{days} days ago"

    if days < 14:
        return "a week ago"

    return f"{round(days / 7)} weeks ago"


@app.template_filter("initials")
def initials(name):
    return "".join(
        w[0] for w in name.split()[:2]
    ).upper()


@app.template_filter("tint")
def tint(code):
    return "t" + str(
        sum(ord(c) for c in str(code)) % 4
    )


@app.template_filter("signed")
def signed(n):
    return (
        f"+{n}"
        if n > 0
        else ("±0" if n == 0 else str(n))
    )


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------
@app.context_processor
def inject_helpers():
    import platform

    now = datetime.now()

    if platform.system() == "Windows":
        today_long = now.strftime(
            "%A, %#d %B"
        )
    else:
        today_long = now.strftime(
            "%A, %-d %B"
        )

    return {
        "wpi_barrier_band": wpi_barrier_band,
        "wpi_barrier_class": wpi_barrier_class,
        "wpi_barrier_var": wpi_barrier_var,

        "greeting": (
            "Good morning"
            if now.hour < 12
            else (
                "Good afternoon"
                if now.hour < 18
                else "Good evening"
            )
        ),

        "today_long": today_long,
    }


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():

        # Create and seed the database only if
        # the patients table does not exist.
        if not database.database_ready():

            database.init_db()

            from seed import seed

            n_p, n_a = seed(
                database.get_db()
            )

            print(
                f"Created database with "
                f"{n_p} patients and "
                f"{n_a} assessments."
            )

    app.run(debug=True)