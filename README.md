# RehabAI

Rehabilitation outcome prediction from UK ROC admission data. Flask + SQLite,
Bootstrap 5 and Chart.js on the front end.

Score a patient's 28 UK ROC admission items and get a walking probability, a
WPI score, a barrier score and a plain-English interpretation. Every
prediction is stored, so the patient record shows progress over the whole
admission, and the hospital dashboard summarises all patients.

## Running it

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                                       # creates + seeds the DB on first run
```

Or with the Flask CLI:

```bash
export FLASK_APP=app.py        # PowerShell: $env:FLASK_APP="app.py"
flask seed-db
flask run
```

Demo accounts (password `12345`):

| Email               | Role      | Hospital                     |
| ------------------- | --------- | ---------------------------- |
| `admin@hotmail.com` | admin     | all hospitals                |
| `path@qmc.uk`       | clinician | Queen's Medical Centre       |
| `jay@lut.uk`        | clinician | Luton and Dunstable Hospital |

## Screens

| Route                          | Screen                                                |
| ------------------------------ | ----------------------------------------------------- |
| `/`                            | Public home page                                      |
| `/login`                       | Sign in                                               |
| `/dashboard`                   | Hospital statistics (landing page after sign in)      |
| `/patients`                    | Patient list with search, filters and sorting         |
| `/patients/add`                | Add patient                                           |
| `/patients/<code>`             | Patient record: tiles, progress chart, history        |
| `/patients/<code>/edit`        | Edit patient                                          |
| `/patients/<code>/predict`     | New assessment, with a review modal before predicting |
| `/patients/<code>/a/<id>`      | A stored prediction                                   |

## Project layout

```
app.py                 application factory (wiring only)
config.py              configuration
db.py                  SQLite connection + CLI commands
model.py               scales, domains, WPI scoring, prediction, SHAP
seed.py / schema.sql   demo data and tables
routes/                HTTP layer (blueprints) - thin, calls services
  auth.py  main.py  patients.py  assessments.py
services/              business logic - all SQL lives here
  users.py        authentication
  clinics.py      hospitals and hospital-level scoping
  patients.py     list/filter/get/create/update patients
  assessment.py   form parsing, prediction, storage, result view models
  dashboard.py    hospital statistics
  bands.py        WPI barrier-band thresholds (single source of truth)
utils/
  auth.py              login_required, session helpers
  template_helpers.py  Jinja filters and globals
templates/             Jinja templates (_macros.html holds shared components)
static/css/style.css   brand layer on top of Bootstrap
static/js/app.js       page behaviour (filters, form progress, preview modal)
static/js/charts.js    Chart.js gauges, doughnuts, bars and lines
```

## Hospital scoping

Patients belong to a hospital through the clinician who registered them
(`patients.created_by -> users.clinic_id`). Clinicians only see their own
hospital on the dashboard, patient list and patient records; records from
other hospitals return 404. Admins see every hospital and can pick one.

## WPI direction

WPI is a barrier index: **lower is better**. Bands come from the quantiles in
the model artifacts (`services/bands.py`). A negative WPI change since
baseline is an improvement.

## Before this goes near real patients

* Set a real `SECRET_KEY` environment variable.
* SQLite is single-writer; move to PostgreSQL for multi-user deployments.
* Consider a `clinic_id` column on `patients` so a patient's hospital does
  not depend on the clinician who created the record.
* Interpretation text is rule-based template output, not clinical guidance.
