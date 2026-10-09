"""Patient list, record, add and edit."""

from asyncio.log import logger

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from services import clinics
from services import patients as patient_service
from services.assessment import build_patient_view
from services.bands import BANDS
from utils.auth import login_required

bp = Blueprint("patients", __name__, url_prefix="/patients")


def _scope():
    """Hospital scope for the current user (admins may pass ?clinic=)."""

    return clinics.resolve_scope(g.user, request.args.get("clinic"))


def _patient_or_404(patient_code):
    clinic_id, _clinic = clinics.resolve_scope(g.user)
    return patient_service.get_patient(patient_code, clinic_id)


@bp.route("")
@login_required
def index():
    clinic_id, clinic = _scope()
    filters = patient_service.PatientFilters.from_args(request.args)

    logger.info(
        patient_service.list_patients(clinic_id, filters)
    )

    return render_template(
        "patients.html",
        people=patient_service.list_patients(clinic_id, filters),
        total=patient_service.count_patients(clinic_id),
        filters=filters,
        diagnoses=patient_service.list_diagnoses(clinic_id),
        bands=BANDS,
        trends=patient_service.TRENDS,
        sorts=patient_service.SORTS,
        clinic=clinic,
        scope_label=clinics.scope_label(g.user, clinic),
        clinic_options=clinics.list_clinics() if g.user["is_admin"] else [],
    )


@bp.route("/add", methods=["GET", "POST"])
@login_required
def create():
    form_data = {}

    if request.method == "POST":
        form_data, errors = patient_service.parse_patient_form(request.form)

        if not errors:
            ok, message = patient_service.create_patient(form_data, g.user["user_id"])

            if ok:
                flash("Patient added successfully.")
                return redirect(url_for("patients.detail", patient_id=form_data["patient_id"]))

            errors.append(message)

        for message in errors:
            flash(message)

    return render_template(
        "patient_form.html",
        p=form_data,
        editing=False,
        diagnoses=patient_service.diagnosis_choices(form_data.get("diag_std_subcat")),
        genders=patient_service.GENDERS,
    )


@bp.route("/<patient_id>/edit", methods=["GET", "POST"])
@login_required
def edit(patient_id):
    patient = _patient_or_404(patient_id)
    form_data = patient

    if request.method == "POST":
        form_data, errors = patient_service.parse_patient_form(request.form, existing=patient)

        if not errors:
            patient_service.update_patient(patient, form_data)
            flash("Patient details updated successfully.")
            return redirect(url_for("patients.detail", patient_id=patient["patient_id"]))

        for message in errors:
            flash(message)

    return render_template(
        "patient_form.html",
        p=form_data,
        editing=True,
        diagnoses=patient_service.diagnosis_choices(form_data.get("diag_std_subcat")),
        genders=patient_service.GENDERS,
    )


@bp.route("/<patient_id>")
@login_required
def detail(patient_id):
    patient = _patient_or_404(patient_id)
    history = patient_service.get_history(patient["id"])

    return render_template(
        "patient.html",
        p=patient,
        history=history,
        latest=history[-1] if history else None,
        view=build_patient_view(history),
    )
