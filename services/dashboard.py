"""Hospital-level statistics for the dashboard."""

from collections import Counter, OrderedDict
from datetime import date, timedelta
from statistics import mean

from db import get_db
from model import DOMAINS, ITEM_KEYS, domain_score
from services.bands import BANDS, WPI_SCALE_MAX, band_info, gauge_bands
from services.patients import PatientFilters, list_patients


def _avg(values, ndigits=1):
    values = [v for v in values if v is not None]
    return round(mean(values), ndigits) if values else None


def _scoped_assessments(clinic_id, admission_status):
    """Every assessment for patients in scope, ordered for grouping."""

    sql = """
        SELECT a.*, p.patient_id AS patient_code,
               p.first_name, p.last_name
        FROM assessments a
        JOIN patients p ON p.id = a.patient_id
        JOIN users u    ON u.id = p.created_by
        WHERE 1 = 1
    """
    params = []

    if clinic_id is not None:
        sql += " AND u.clinic_id = ?"
        params.append(clinic_id)

    if admission_status:
        sql += " AND p.admission_status = ?"
        params.append(admission_status)

    sql += " ORDER BY a.assessed_on, a.id"

    return get_db().execute(sql, params).fetchall()


def _monthly_trend(assessments):
    months = OrderedDict()

    for row in assessments:
        key = str(row["assessed_on"])[:7]
        months.setdefault(key, {"wpi": [], "walk": []})
        months[key]["wpi"].append(row["wpi"])
        months[key]["walk"].append(row["walk_prob"])

    labels = [date.fromisoformat(f"{k}-01").strftime("%b %Y") for k in months]

    return {
        "labels": labels,
        "wpi": [_avg(m["wpi"]) for m in months.values()],
        "walk": [_avg(m["walk"]) for m in months.values()],
        "count": [len(m["wpi"]) for m in months.values()],
    }


def _domain_averages(latest_rows):
    """Average functional attainment (0–100, higher = better) per domain."""

    result = []

    for domain in DOMAINS:
        scores = [
            domain_score({k: row[k] for k in ITEM_KEYS}, domain["id"]) * 100
            for row in latest_rows
        ]
        result.append(
            {
                "id": domain["id"],
                "name": domain["name"],
                "short": domain["short"],
                "pct": _avg(scores, 0),
            }
        )

    return result


def build_dashboard(clinic_id=None, admission_status="", recent_days=30):
    """
    Compute every dashboard metric for one hospital (or all hospitals when
    `clinic_id` is None). All "current" figures use each patient's most
    recent assessment.
    """

    people = list_patients(clinic_id, PatientFilters(admission_status=admission_status))
    assessments = _scoped_assessments(clinic_id, admission_status)

    latest_by_patient = {}
    for row in assessments:
        latest_by_patient[row["patient_id"]] = row  # ordered, so last wins

    latest_rows = list(latest_by_patient.values())
    assessed = [p for p in people if p["latest_wpi"] is not None]

    avg_wpi = _avg(p["latest_wpi"] for p in assessed)
    avg_walk = _avg(p["latest_walk_prob"] for p in assessed)
    avg_barrier = _avg(p["latest_barrier_score"] for p in assessed)

    since = (date.today() - timedelta(days=recent_days)).isoformat()

    band_counts = Counter(p["band"]["key"] for p in assessed)
    walking_counts = Counter(p["latest_walking_status"] for p in assessed)
    trend_counts = Counter(p["trend"] for p in people)
    cluster_counts = Counter(int(row["cluster"]) for row in latest_rows)
    diagnosis_counts = Counter(p["diag_std_subcat"] for p in people)

    needs_review = sorted(
        (p for p in assessed if p["band"]["key"] == "higher"),
        key=lambda p: p["latest_wpi"],
        reverse=True,
    )

    overdue_cutoff = (date.today() - timedelta(days=14)).isoformat()
    overdue = [
        p
        for p in people
        if p["admission_status"] == "active"
        and (p["latest_assessed_on"] is None or p["latest_assessed_on"] < overdue_cutoff)
    ]

    recent = [
        {
            "id": row["id"],
            "patient_code": row["patient_code"],
            "name": f"{row['first_name']} {row['last_name']}",
            "assessed_on": row["assessed_on"],
            "wpi": row["wpi"],
            "walk_prob": row["walk_prob"],
            "band": band_info(row["wpi"]),
        }
        for row in reversed(assessments[-6:])
    ]

    return {
        "kpis": {
            "patients": len(people),
            "active": sum(1 for p in people if p["admission_status"] == "active"),
            "discharged": sum(1 for p in people if p["admission_status"] == "discharged"),
            "assessed": len(assessed),
            "assessments": len(assessments),
            "recent_assessments": sum(1 for a in assessments if str(a["assessed_on"]) >= since),
            "improving": trend_counts.get("improving", 0),
            "declining": trend_counts.get("declining", 0),
            "needs_review": len(needs_review),
            "overdue": len(overdue),
        },
        "averages": {
            "wpi": avg_wpi,
            "walk": avg_walk,
            "barrier": avg_barrier,
            "band": band_info(avg_wpi),
        },
        "gauges": {
            "wpi": {
                "value": avg_wpi,
                "max": WPI_SCALE_MAX,
                "bands": gauge_bands(),
                "color": band_info(avg_wpi)["var"],
                "decimals": 1,
                "unit": "",
            },
            "walk": {
                "value": avg_walk,
                "max": 100,
                "color": "pink",
                "decimals": 1,
                "unit": "%",
            },
            "barrier": {
                "value": avg_barrier,
                "max": 10,
                "color": band_info(avg_wpi)["var"],
                "decimals": 1,
                "unit": "/10",
            },
        },
        "bands": [
            {"key": key, "label": label, "short": label.replace(" barrier burden", ""),
             "var": var, "count": band_counts.get(key, 0)}
            for key, label, var in BANDS
        ],
        "walking": {
            "labels": ["Walking", "Wheelchair", "Not assessed"],
            "values": [
                walking_counts.get("walking", 0),
                walking_counts.get("wheelchair", 0),
                len(people) - len(assessed),
            ],
            "colors": ["good", "warn", "border-dark"],
        },
        "domains": _domain_averages(latest_rows),
        "clusters": {
            "labels": [f"Cluster {c}" for c in sorted(cluster_counts)],
            "values": [cluster_counts[c] for c in sorted(cluster_counts)],
        },
        "diagnoses": {
            "labels": [d for d, _ in diagnosis_counts.most_common(8)],
            "values": [n for _, n in diagnosis_counts.most_common(8)],
        },
        "trend": _monthly_trend(assessments),
        "needs_review": needs_review[:5],
        "overdue": overdue[:5],
        "recent": recent,
        "recent_days": recent_days,
    }
