"""New assessment (prediction) and stored assessment results."""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from services import assessment as assessment_service
from services import clinics
from services import patients as patient_service
from utils.auth import login_required

bp = Blueprint("assessments", __name__, url_prefix="/patients/<patient_id>")


def _patient_or_404(patient_code):
    clinic_id, _clinic = clinics.resolve_scope(g.user)
    return patient_service.get_patient(patient_code, clinic_id)


@bp.route("/predict", methods=["GET", "POST"])
@login_required
def new(patient_id):
    patient = _patient_or_404(patient_id)
    history = patient_service.get_history(patient["id"])

    if request.method == "POST":
        assessment_id, state = assessment_service.create_assessment(
            patient, g.user["user_id"], request.form, history
        )

        if assessment_id is not None:
            return redirect(
                url_for("assessments.detail", patient_id=patient_id, assessment_id=assessment_id)
            )

        flash(assessment_service.error_message(state["errors"]))
        state["prefilled_from"] = None

    else:
        state = assessment_service.form_defaults(history, prefill=bool(request.args.get("prefill")))

    return render_template(
        "predict.html",
        p=patient,
        domains=assessment_service.form_domains(),
        state=state,
        previous=history[-1] if history else None,
    )


@bp.route("/a/<int:assessment_id>")
@login_required
def detail(patient_id, assessment_id):
    patient = _patient_or_404(patient_id)
    row = assessment_service.get_assessment(patient["id"], assessment_id)
    history = patient_service.get_history(patient["id"])

    return render_template(
        "result.html",
        p=patient,
        a=row,
        view=assessment_service.build_result_view(patient, row, history),
    )
