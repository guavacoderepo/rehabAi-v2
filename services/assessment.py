"""Assessments: form handling, prediction, storage and result views."""

import json
import logging
from datetime import date

from werkzeug.exceptions import NotFound

from db import get_db
from model import (
    DOMAIN_PROFILE,
    DOMAIN_VIEW,
    DOMAINS,
    ITEM_KEYS,
    PHENOTYPE_REFERENCE_DATASET,
    explain_patient,
    get_similar_wpi_patients,
    interpret,
    measures_grouping,
    predict,
    MFRA_DOMAINS, 
    mfra_domain_score
)
from services.patients import WALKING_STATUSES, patient_age, patient_name

logger = logging.getLogger(__name__)


MEASURE_GROUPS = [
    ("fimfam", "FIM+FAM"),
    ("nis", "NIS"),
    ("npds", "NPDS"),
]

_OUTPUT_COLUMNS = ["wpi", "walk_prob", "barrier_score", "cluster", "mfra_score", "interpretation"]


# ---------------------------------------------------------------------------
# Form handling
# ---------------------------------------------------------------------------

def parse_assessment_form(form):
    """
    Read the 28 items, walking status and date from the submitted form.

    Returns a dict: {values, walking_status, assessed_on, errors}.
    """

    values = {}
    errors = []

    walking_status = form.get("walking_status")
    if walking_status not in WALKING_STATUSES:
        errors.append("walking_status")

    for key in ITEM_KEYS:
        raw = form.get(key)

        try:
            values[key] = int(raw)
        except (TypeError, ValueError):
            errors.append(key)

    assessed_on = form.get("assessed_on") or date.today().isoformat()

    try:
        if date.fromisoformat(assessed_on) > date.today():
            errors.append("assessed_on")
    except ValueError:
        errors.append("assessed_on")
        assessed_on = date.today().isoformat()

    return {
        "values": values,
        "walking_status": walking_status,
        "assessed_on": assessed_on,
        "errors": errors,
    }


def error_message(errors):
    if "walking_status" in errors:
        return "Please select the patient's current walking status."

    if "assessed_on" in errors:
        return "Please enter a valid assessment date (not in the future)."

    missing = len([e for e in errors if e in ITEM_KEYS])
    return f"{missing} of {len(ITEM_KEYS)} items still need a score."


def form_defaults(history, prefill=False):
    """Initial state for the new-assessment form."""

    state = {
        "values": {},
        "walking_status": None,
        "assessed_on": date.today().isoformat(),
        "prefilled_from": None,
    }

    if prefill and history:
        last = history[-1]
        state["values"] = {key: last[key] for key in ITEM_KEYS}
        state["walking_status"] = last["walking_status"]
        state["prefilled_from"] = last

    return state


# ---------------------------------------------------------------------------
# Prediction + storage
# ---------------------------------------------------------------------------

def run_prediction(patient, values, previous=None):
    """Score the patient and generate the plain-English interpretation."""

    model_input = dict(values)
    model_input["patient_age"] = patient_age(patient)
    model_input["patient_gender"] = patient["patient_gender"]
    model_input["diag_std_subcat"] = patient["diag_std_subcat"]

    pred = predict(model_input)

    text = interpret(
        pred,
        dict(previous) if previous is not None else None,
        patient_name(patient),
    )

    pred["interpretation"] = json.dumps({**text, "domains": pred.get("domains", {})})

    return pred


def save_assessment(patient, user_id, form_state, pred):
    """Insert the assessment and its model outputs. Returns the new id."""

    columns = (
        ["patient_id", "user_id", "assessed_on", "walking_status"]
        + ITEM_KEYS
        + _OUTPUT_COLUMNS
    )

    params = (
        [patient["id"], user_id, form_state["assessed_on"], form_state["walking_status"]]
        + [form_state["values"][key] for key in ITEM_KEYS]
        + [float(pred[col]) if col != "interpretation" else pred[col] for col in _OUTPUT_COLUMNS]
    )

    db = get_db()

    cur = db.execute(
        f"""
        INSERT INTO assessments ({", ".join(columns)})
        VALUES ({", ".join("?" for _ in columns)})
        """,
        params,
    )
    db.commit()

    return cur.lastrowid


def create_assessment(patient, user_id, form, history):
    """
    Validate, predict and store a new assessment.

    Returns (assessment_id, form_state). assessment_id is None when the
    form is invalid; form_state then holds the values to re-render.
    """

    state = parse_assessment_form(form)

    if state["errors"]:
        return None, state

    previous = history[-1] if history else None
    pred = run_prediction(patient, state["values"], previous)

    return save_assessment(patient, user_id, state, pred), state


# ---------------------------------------------------------------------------
# Reading assessments
# ---------------------------------------------------------------------------

def mfra_domains_for(row):
    values = {key: row[key] for key in ITEM_KEYS}
    rows = [
        {
            "id": d["id"],
            "name": d["name"],
            "value": round(mfra_domain_score(values, d["id"]), 1),
        }
        for d in MFRA_DOMAINS
    ]
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows

def get_assessment(patient_db_id, assessment_id):
    row = get_db().execute(
        "SELECT * FROM assessments WHERE id = ? AND patient_id = ?",
        (assessment_id, patient_db_id),
    ).fetchone()

    if row is None:
        raise NotFound("No such assessment for this patient")

    return row


def parse_interpretation(row):
    try:
        return json.loads(row["interpretation"] or "{}")
    except (TypeError, ValueError):
        return {}


def previous_of(history, assessment_id):
    previous = None

    for row in history:
        if row["id"] == assessment_id:
            return previous
        previous = row

    return None


def item_values(row):
    return {key: row[key] for key in ITEM_KEYS}


def domain_raw_scores(values):
    """Raw mean of item values per domain (matches the training pipeline)."""

    scores = {}

    for domain in DOMAINS:
        items = [float(values[key]) for key, _l, _s in domain["items"] if values.get(key) is not None]
        scores[domain["name"]] = round(sum(items) / len(items), 2) if items else None

    return scores


# ---------------------------------------------------------------------------
# View models
# ---------------------------------------------------------------------------

def build_patient_view(history):
    """Progress chart data and the collapsible prediction timeline."""

    chart = [
        {
            "date": row["assessed_on"],
            "wpi": round(row["wpi"], 1),
            "walk": round(row["walk_prob"], 1),
            "barrier": round(row["barrier_score"], 1),
        }
        for row in history
    ]

    timeline = []
    total = len(history)

    for position, row in enumerate(reversed(history)):
        timeline.append(
            {
                "row": row,
                "text": parse_interpretation(row),
                "index": total - position,
                "is_latest": position == 0,
            }
        )

    change = (
        round(history[-1]["wpi"] - history[0]["wpi"], 1)
        if len(history) > 1
        else None
    )

    return {
        "chart": chart,
        "timeline": timeline,
        "wpi_change": change,
        "domains": DOMAINS,
    }


def _measures_with_percent(row):
    """Group the 28 items by instrument and add a 0–100 'better is higher' %."""

    grouped = measures_grouping(row)

    for items in grouped.values():
        for m in items:
            span = m["max"] - m["min"]
            if not span:
                m["pct"] = 0
            elif m["dir"] > 0:
                m["pct"] = round((m["value"] - m["min"]) / span * 100, 1)
            else:
                m["pct"] = round((m["max"] - m["value"]) / span * 100, 1)

    return grouped


def _shap_with_widths(result):
    """Add bar widths (relative to the strongest factor in each list)."""

    for key in ("supporting", "limiting"):
        factors = result.get(key) or []
        top = max((abs(f["shap"]) for f in factors), default=0) or 1

        for f in factors:
            f["width"] = round(abs(f["shap"]) / top * 100, 1)

    return result


def _cluster_share(cluster):
    df = PHENOTYPE_REFERENCE_DATASET

    if df is None or not len(df) or "cluster" not in df.columns:
        return None

    return round(float((df["cluster"] == cluster).mean() * 100), 1)


def build_result_view(patient, assessment, history):
    """Everything the result page needs, pre-computed."""

    values = item_values(assessment)
    cluster = int(assessment["cluster"])

    try:
        cluster_profile = DOMAIN_PROFILE.loc[cluster]
    except KeyError:
        cluster_profile = None

    similar = get_similar_wpi_patients(assessment["wpi"], cluster)
    patient_raw = domain_raw_scores(values)

    domain_rows = []
    for domain in DOMAINS:
        name = domain["name"]
        domain_rows.append(
            {
                "id": domain["id"],
                "name": name,
                "patient": patient_raw.get(name),
                "cluster": (
                    round(float(cluster_profile[name]), 2)
                    if cluster_profile is not None and name in cluster_profile.index
                    else None
                ),
                "similar": similar.get("averages", {}).get(name),
            }
        )

    try:
        shap_result = _shap_with_widths(explain_patient(values))
    except Exception:  # explanation is helpful, never essential
        logger.exception("SHAP explanation failed for assessment %s", assessment["id"])
        shap_result = None

    mfra_domains  = mfra_domains_for(assessment)

    return {
        "text": parse_interpretation(assessment),
        "previous": previous_of(history, assessment["id"]),
        "domains": DOMAINS,
        "measures": _measures_with_percent(assessment),
        "measure_groups": MEASURE_GROUPS,
        "shap": shap_result,
        "cluster": cluster,
        "cluster_share": _cluster_share(cluster),
        "similar_count": similar.get("n_matched", 0),
        "domain_rows": domain_rows,
        "mfra_domains": mfra_domains,
        "domain_chart": {
            "labels": [row["name"] for row in domain_rows],
            "datasets": [
                {"label": "This patient", "data": [row["patient"] for row in domain_rows], "color": "pink"},
                {"label": f"Cluster {cluster} average", "data": [row["cluster"] for row in domain_rows], "color": "ink-3"},
                {"label": "Similar patients", "data": [row["similar"] for row in domain_rows], "color": "mid"},
            ],
        },
    }


def form_domains():
    """Domain/item structure used to render the assessment form."""

    return DOMAIN_VIEW
