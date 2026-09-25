-- RehadAI schema
-- Rebuild with:  flask init-db      (empty)
--                flask seed-db      (empty + 5 dummy patients)

DROP TABLE IF EXISTS assessments; 
DROP TABLE IF EXISTS patients; 
DROP TABLE IF EXISTS users; 
DROP TABLE IF EXISTS clinics;


CREATE TABLE clinics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,

    name        TEXT NOT NULL UNIQUE,
    code        TEXT UNIQUE,

    level       INTEGER NOT NULL
                CHECK(level IN (0, 2, 3)),

    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Users (clinicians, admins)
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    first_name          TEXT NOT NULL,
    last_name           TEXT NOT NULL,

    email               TEXT NOT NULL UNIQUE,
    password_hash       TEXT NOT NULL,

    clinic_id           INTEGER
                        REFERENCES clinics(id)
                        ON DELETE RESTRICT,

    role                TEXT NOT NULL DEFAULT 'clinician'
                        CHECK(role IN ('admin', 'clinician', 'guest')),

    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Patients
-- ---------------------------------------------------------------------------
CREATE TABLE patients (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    patient_id          TEXT NOT NULL UNIQUE,
    nhs_number          TEXT NOT NULL UNIQUE,

    first_name          TEXT NOT NULL,
    last_name           TEXT NOT NULL,

    date_of_birth       TEXT NOT NULL,
    patient_gender      TEXT NOT NULL CHECK(patient_gender IN ('F','M','X')),

    diag_std_subcat     TEXT NOT NULL,

    admission_date      TEXT NOT NULL,

    admission_status    TEXT NOT NULL
                        CHECK(admission_status IN ('active', 'discharged')),

    created_by          INTEGER NOT NULL
                        REFERENCES users(id)
                        ON DELETE RESTRICT,

    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------------
-- Assessments: one row per prediction
--
-- The 28 UKROC items are stored as named columns rather than key/value pairs,
-- so the table can be directly used as a feature matrix for model training
-- and export.
-- ---------------------------------------------------------------------------
CREATE TABLE assessments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,

    patient_id  INTEGER NOT NULL
                REFERENCES patients(id)
                ON DELETE CASCADE,

    user_id INTEGER NOT NULL
                 REFERENCES users(id)
                 ON DELETE RESTRICT,

    assessed_on TEXT NOT NULL,

    created_at  TEXT NOT NULL DEFAULT (datetime('now')),

    walking_status TEXT NOT NULL
                    CHECK(walking_status IN ('walking', 'wheelchair')),

    -- -----------------------------------------------------------------------
    -- Mobility
    -- -----------------------------------------------------------------------

    -- FIM: 1-7
    fimfam_transfer_bed_adm
        INTEGER NOT NULL CHECK(fimfam_transfer_bed_adm BETWEEN 1 AND 7),

    fimfam_transfer_toilet_adm
        INTEGER NOT NULL CHECK(fimfam_transfer_toilet_adm BETWEEN 1 AND 7),

    fimfam_transfer_bath_adm
        INTEGER NOT NULL CHECK(fimfam_transfer_bath_adm BETWEEN 1 AND 7),

    fimfam_transfer_car_adm
        INTEGER NOT NULL CHECK(fimfam_transfer_car_adm BETWEEN 1 AND 7),

    -- NPDS 4-point: 0-4
    npds_mobility_adm
        INTEGER NOT NULL CHECK(npds_mobility_adm BETWEEN 0 AND 4),


    -- -----------------------------------------------------------------------
    -- ADL
    -- -----------------------------------------------------------------------

    -- FIM: 1-7
    fimfam_dress_upper_adm
        INTEGER NOT NULL CHECK(fimfam_dress_upper_adm BETWEEN 1 AND 7),

    fimfam_dress_lower_adm
        INTEGER NOT NULL CHECK(fimfam_dress_lower_adm BETWEEN 1 AND 7),

    fimfam_bathing_adm
        INTEGER NOT NULL CHECK(fimfam_bathing_adm BETWEEN 1 AND 7),

    fimfam_bladder_adm
        INTEGER NOT NULL CHECK(fimfam_bladder_adm BETWEEN 1 AND 7),

    fimfam_bowel_adm
        INTEGER NOT NULL CHECK(fimfam_bowel_adm BETWEEN 1 AND 7),

    fimfam_toileting_adm
        INTEGER NOT NULL CHECK(fimfam_toileting_adm BETWEEN 1 AND 7),

    -- NPDS: 0-5
    npds_bathing_adm
        INTEGER NOT NULL CHECK(npds_bathing_adm BETWEEN 0 AND 5),

    npds_skin_pressure_adm
        INTEGER NOT NULL CHECK(npds_skin_pressure_adm BETWEEN 0 AND 5),

    -- Binary NPDS: 0 or 5 only
    npds_pressure_adm
        INTEGER NOT NULL CHECK(npds_pressure_adm IN (0, 5)),


    -- -----------------------------------------------------------------------
    -- Cognitive / Communicative
    -- -----------------------------------------------------------------------

    -- FIM: 1-7
    fimfam_speech_adm
        INTEGER NOT NULL CHECK(fimfam_speech_adm BETWEEN 1 AND 7),

    fimfam_writing_adm
        INTEGER NOT NULL CHECK(fimfam_writing_adm BETWEEN 1 AND 7),

    -- NIS: 0-3
    nis_cognitive_adm
        INTEGER NOT NULL CHECK(nis_cognitive_adm BETWEEN 0 AND 3),

    nis_perceptual_adm
        INTEGER NOT NULL CHECK(nis_perceptual_adm BETWEEN 0 AND 3),

    -- NPDS 3-point: 0-3
    npds_safety_adm
        INTEGER NOT NULL CHECK(npds_safety_adm BETWEEN 0 AND 3),

    -- Binary NPDS: 0 or 5 only
    npds_specialing_adm
        INTEGER NOT NULL CHECK(npds_specialing_adm IN (0, 5)),


    -- -----------------------------------------------------------------------
    -- Physical Impairment
    -- -----------------------------------------------------------------------

    -- NIS: 0-3
    nis_fatigue_adm
        INTEGER NOT NULL CHECK(nis_fatigue_adm BETWEEN 0 AND 3),

    nis_motor_lower_left_adm
        INTEGER NOT NULL CHECK(nis_motor_lower_left_adm BETWEEN 0 AND 3),

    nis_motor_lower_right_adm
        INTEGER NOT NULL CHECK(nis_motor_lower_right_adm BETWEEN 0 AND 3),

    -- NIS special: 0-2
    nis_motor_trunk_adm
        INTEGER NOT NULL CHECK(nis_motor_trunk_adm BETWEEN 0 AND 2),

    nis_motor_upper_left_adm
        INTEGER NOT NULL CHECK(nis_motor_upper_left_adm BETWEEN 0 AND 3),

    nis_motor_upper_right_adm
        INTEGER NOT NULL CHECK(nis_motor_upper_right_adm BETWEEN 0 AND 3),

    nis_sensation_adm
        INTEGER NOT NULL CHECK(nis_sensation_adm BETWEEN 0 AND 3),

    nis_tone_adm
        INTEGER NOT NULL CHECK(nis_tone_adm BETWEEN 0 AND 3),


    -- -----------------------------------------------------------------------
    -- Computed outputs
    -- -----------------------------------------------------------------------

    wpi INTEGER NOT NULL,

    walk_prob REAL NOT NULL,

    barrier_score REAL NOT NULL,

    interpretation TEXT NOT NULL
);


-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX idx_users_name ON users(last_name, first_name); 
CREATE INDEX idx_users_clinic ON users(clinic_id); 
CREATE INDEX idx_patients_patient_id ON patients(patient_id); 
CREATE INDEX idx_patients_nhs_number ON patients(nhs_number); 
CREATE INDEX idx_patients_created_by ON patients(created_by); 
CREATE INDEX idx_assessments_patient ON assessments(patient_id, assessed_on); 
CREATE INDEX idx_assessments_user ON assessments(user_id); 
CREATE INDEX idx_assessments_date ON assessments(assessed_on);