"""
routes.py – FastAPI REST API
Module 25: ICU Vital Signs Monitoring | /api/icu-vitals/

Run:
  uvicorn api.routes:app --reload --port 8001

Swagger UI: http://localhost:8001/docs
"""

import os
import sys
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient

# Allow imports from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import patients, vitals, alerts, schema_validator
from database import deterioration as det
from api.schemas import (
    VitalSignIngest, ManualEntryRequest, VitalSignUpdate,
    AlertAcknowledge, AlertIntervention,
    DeteriorationEscalate, DeteriorationResolve,
    DrugAlertWebhook,
    PatientAdmit, ThresholdRule,
)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="M25 · ICU Vital Signs Monitoring API",
    description=(
        "REST API for Module 25 of the Medical Copilot System.\n\n"
        "Provides high-frequency vital sign ingestion, real-time NEWS2/SOFA scoring, "
        "deterioration event tracking, threshold alerts, and inter-module webhooks."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB connection ─────────────────────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv()
MONGO_URI = os.getenv("MODULE25_MONGO_URI", os.getenv("MONGO_URI", "mongodb://localhost:27017"))
_client: Optional[MongoClient] = None

def get_db():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client["icu_database"]

@app.on_event("startup")
def startup_db_initialization():
    print("Starting ICU Vital Signs Module...")
    try:
        db = get_db()
        vitals.create_indexes(db)
        alerts.ensure_indexes(db)
        schema_validator.apply_schema_validators(db)
    except Exception as e:
        print(f"Error initializing database: {e}")

# =============================================================================
# PATIENTS
# =============================================================================

@app.get("/api/icu-vitals/patients", tags=["Patients"])
def list_patients():
    """Return all admitted ICU patients."""
    db = get_db()
    return patients.get_all_patients(db)


@app.post("/api/icu-vitals/patients", tags=["Patients"], status_code=201)
def admit_patient(body: PatientAdmit):
    """Admit a new patient to the ICU and assign a monitoring device."""
    db = get_db()
    try:
        inserted_id, doc = patients.insert_patient_with_device(
            db,
            body.patient_id, body.first_name, body.last_name or "",
            body.gender, body.date_of_birth or "",
            body.device_id, body.device_type,
            mrn=body.mrn,
            admission_status=body.admission_status,
            acuity_level=body.acuity_level,
            admitting_diagnosis=body.admitting_diagnosis,
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {
        "inserted_id": str(inserted_id),
        "patient": {k: str(v) if not isinstance(v, (str, int, float, bool, dict, list, type(None))) else v
                    for k, v in doc.items()},
    }


# =============================================================================
# THRESHOLD RULES
# =============================================================================

@app.post("/api/icu-vitals/patients/{patient_id}/thresholds", tags=["Alerts"], status_code=200)
def set_threshold_rule(patient_id: str, body: ThresholdRule):
    """Create or update a vital sign threshold rule for a patient."""
    db = get_db()
    alerts.set_threshold(
        db, patient_id, body.parameter, body.min_val, body.max_val,
        adjusted_for_drugs=body.adjusted_for_drugs,
        adjustment_reason=body.adjustment_reason or "",
    )
    return {"saved": True, "patient_id": patient_id, "parameter": body.parameter}



@app.get("/api/icu-vitals/health", tags=["System"])
def health_check():
    """Health check endpoint. Module 26/29 can poll this."""
    try:
        db = get_db()
        db.command("ping")
        return {"status": "ok", "module": "M25-ICU-Vital-Signs", "db": "connected"}
    except Exception as e:
        raise HTTPException(503, f"DB unavailable: {e}")

@app.get("/api/icu-vitals/db-info/server-functions", tags=["System"])
def get_server_functions():
    """Returns the JS stored procedures definition."""
    import os
    file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "server_functions.js")
    try:
        with open(file_path, "r") as f:
            return {"js_code": f.read()}
    except Exception as e:
        raise HTTPException(500, f"Could not read server_functions.js: {e}")


# =============================================================================
# VITAL SIGN INGESTION
# =============================================================================

@app.post("/api/icu-vitals/ingest", tags=["Vitals"], status_code=201)
def ingest_vitals(body: VitalSignIngest):
    """
    Receive raw telemetry from a bedside monitor.
    Auto-calculates NEWS2, SOFA, APACHE II.
    Triggers deterioration event if NEWS2 >= 7 or MODS detected.
    Triggers threshold alerts based on patient or default rules.
    """
    db = get_db()

    if not patients.get_patient_by_id(db, body.patient_id):
        raise HTTPException(404, f"Patient '{body.patient_id}' not found.")

    v_id, doc = vitals.insert_vital_sign(
        db,
        patient_id=body.patient_id,
        systolic_bp=body.systolic_bp,
        diastolic_bp=body.diastolic_bp,
        heart_rate=body.heart_rate,
        respiratory_rate=body.respiratory_rate,
        spo2=body.spo2,
        supplemental_oxygen=body.supplemental_oxygen,
        respiratory_support=body.respiratory_support,
        consciousness_level=body.consciousness_level,
        temperature=body.temperature,
        urine_output_ml_hr=body.urine_output_ml_hr,
        pain_score=body.pain_score,
        use_spo2_scale2=body.use_spo2_scale2,
        platelet_count=body.platelet_count,
        bilirubin_umol=body.bilirubin_umol,
        device_id=body.device_id,
        creatinine_mg_dl=body.creatinine_mg_dl,
        wbc_count=body.wbc_count,
        hematocrit=body.hematocrit,
        sodium=body.sodium,
        potassium=body.potassium,
        bun_mg_dl=body.bun_mg_dl,
        pao2_mmhg=body.pao2_mmhg,
        fio2_pct=body.fio2_pct,
        ph=body.ph,
        hco3_meq_l=body.hco3_meq_l,
        chronic_health_points=body.chronic_health_points,
        admission_type=body.admission_type,
    )

    current_vitals_map = {
        "heart_rate": body.heart_rate,
        "systolic_bp": body.systolic_bp,
        "diastolic_bp": body.diastolic_bp,
        "temperature": body.temperature,
        "spo2": body.spo2,
        "respiratory_rate": body.respiratory_rate,
        "urine_output_ml_hr": body.urine_output_ml_hr,
        "news2_score": doc["news2_score"],
    }
    triggered_alerts = alerts.evaluate_alert(
        db, body.patient_id, v_id, current_vitals_map,
        news2_score=doc["news2_score"]
    )

    return {
        "vital_sign_id": str(v_id),
        "news2": doc["news2"],
        "sofa": doc["sofa"],
        "apache2": doc["apache2"],
        "saps2": doc.get("saps2"),
        "deterioration_event_id": doc.get("deterioration_event_id"),
        "alerts_triggered": len(triggered_alerts),
        "alert_ids": triggered_alerts,
    }


@app.post("/api/icu-vitals/manual-entry", tags=["Vitals"], status_code=201)
def manual_entry(body: ManualEntryRequest):
    """Nurse manual vital sign documentation (same pipeline as ingest)."""
    db = get_db()

    if not patients.get_patient_by_id(db, body.patient_id):
        raise HTTPException(404, f"Patient '{body.patient_id}' not found.")

    v_id, doc = vitals.insert_vital_sign(
        db,
        patient_id=body.patient_id,
        systolic_bp=body.systolic_bp,
        diastolic_bp=body.diastolic_bp,
        heart_rate=body.heart_rate,
        respiratory_rate=body.respiratory_rate,
        spo2=body.spo2,
        supplemental_oxygen=body.supplemental_oxygen,
        respiratory_support=body.respiratory_support,
        consciousness_level=body.consciousness_level,
        temperature=body.temperature,
        urine_output_ml_hr=body.urine_output_ml_hr,
        pain_score=body.pain_score,
    )

    current_vitals_map = {
        "heart_rate": body.heart_rate,
        "systolic_bp": body.systolic_bp,
        "diastolic_bp": body.diastolic_bp,
        "temperature": body.temperature,
        "spo2": body.spo2,
        "respiratory_rate": body.respiratory_rate,
        "urine_output_ml_hr": body.urine_output_ml_hr,
        "news2_score": doc["news2_score"],
    }
    triggered_alerts = alerts.evaluate_alert(
        db, body.patient_id, v_id, current_vitals_map,
        news2_score=doc["news2_score"]
    )

    return {
        "vital_sign_id": str(v_id),
        "news2_score": doc["news2_score"],
        "news2_risk_band": doc["news2_risk_band"],
        "sofa_score": doc["sofa_score"],
        "deterioration_event_id": doc.get("deterioration_event_id"),
        "news2": doc.get("news2"),
        "sofa": doc.get("sofa"),
        "apache2": doc.get("apache2"),
        "saps2": doc.get("saps2"),
        "alerts_triggered": len(triggered_alerts),
        "alert_ids": triggered_alerts,
    }

@app.put("/api/icu-vitals/vitals/{vital_id}", tags=["Vitals"])
def update_vital_sign(vital_id: str, body: VitalSignUpdate):
    db = get_db()
    update_data = body.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No fields to update")
    modified = vitals.update_vital_sign(db, vital_id, update_data)
    if not modified:
        raise HTTPException(404, "Vital sign not found")
    return {"updated": True, "vital_id": vital_id}

@app.delete("/api/icu-vitals/vitals/{vital_id}", tags=["Vitals"])
def delete_vital_sign(vital_id: str):
    db = get_db()
    deleted = vitals.delete_vital_sign(db, vital_id)
    if not deleted:
        raise HTTPException(404, "Vital sign not found")
    return {"deleted": True, "vital_id": vital_id}

@app.get("/api/icu-vitals/patients/{patient_id}/vitals", tags=["Vitals"])
def get_paginated_vitals(
    patient_id: str = Path(...), 
    limit: int = Query(50, ge=1, le=500)
):
    db = get_db()
    return vitals.list_all_vitals(db, patient_id, limit)


# =============================================================================
# CURRENT VITALS
# =============================================================================

@app.get("/api/icu-vitals/patients/{patient_id}/current", tags=["Vitals"])
def get_current_vitals(patient_id: str = Path(..., description="Patient ID")):
    """
    Return the latest vital sign snapshot with full NEWS2/SOFA scores.
    Used by M16 (Doctor Dashboard) and M27 (Cardiac ICU).
    """
    db = get_db()
    doc = vitals.get_latest_vitals(db, patient_id)
    if not doc:
        raise HTTPException(404, "No vitals recorded for this patient.")
        
    freq = doc.get("news2", {}).get("monitoring_frequency", "Minimum 12 hourly")
    doc["recommended_monitoring_frequency"] = freq
    return doc


# =============================================================================
# TRENDS
# =============================================================================

@app.get("/api/icu-vitals/patients/{patient_id}/trends", tags=["Vitals"])
def get_trends(
    patient_id: str = Path(...),
    interval: str = Query("hourly", enum=["hourly", "4hourly"],
                          description="Aggregation bucket size"),
):
    """
    Aggregated vital sign trends.
    Used by M30 (Time-Series Analysis) for predictive modelling.
    """
    db = get_db()
    data = vitals.get_trends(db, patient_id, interval)
    return {"patient_id": patient_id, "interval": interval, "data": data}

# =============================================================================
# VIEWS
# =============================================================================

@app.get("/api/icu-vitals/views/critical-patients", tags=["Views"])
def critical_patients_view():
    db = get_db()
    return vitals.get_critical_patients_view(db)

@app.get("/api/icu-vitals/views/nurse-summary", tags=["Views"])
def nurse_summary_view():
    db = get_db()
    return vitals.get_nurse_summary_view(db)


# =============================================================================
# PREDICTIONS
# =============================================================================

@app.get("/api/icu-vitals/patients/{patient_id}/predictions", tags=["Predictions"])
def get_deterioration_prediction(patient_id: str = Path(...)):
    """
    Get predictive trajectory based on recent vitals.
    """
    db = get_db()
    return vitals.predict_trend(db, patient_id)


# =============================================================================
# ALERTS
# =============================================================================

@app.get("/api/icu-vitals/alerts/active", tags=["Alerts"])
def get_active_alerts(patient_id: Optional[str] = Query(None)):
    """
    Get all active threshold alerts. Optionally filter by patient.
    Used by M29 (Threshold-Based Alerts) and central nursing dashboard.
    """
    db = get_db()
    return alerts.get_active_alerts(db, patient_id)


@app.put("/api/icu-vitals/alerts/{alert_id}/acknowledge", tags=["Alerts"])
def acknowledge_alert(
    alert_id: str = Path(...),
    body: AlertAcknowledge = AlertAcknowledge(),
):
    """Acknowledge an alert — does not resolve it."""
    db = get_db()
    modified = alerts.acknowledge_alert(db, alert_id, body.acknowledged_by)
    if not modified:
        raise HTTPException(404, "Alert not found or already acknowledged.")
    return {"acknowledged": True, "alert_id": alert_id}


@app.post("/api/icu-vitals/alerts/{alert_id}/intervene", tags=["Alerts"])
def log_intervention(alert_id: str, body: AlertIntervention):
    """Log a clinical intervention and optionally resolve the alert."""
    db = get_db()
    modified = alerts.log_intervention(
        db, alert_id, body.intervention_type,
        body.notes, body.performed_by, body.resolve
    )
    if not modified:
        raise HTTPException(404, "Alert not found.")
    return {"logged": True, "resolved": body.resolve}


# =============================================================================
# ICU DETERIORATION EVENTS
# =============================================================================

@app.get("/api/icu-vitals/deterioration", tags=["Deterioration"])
def get_deterioration_events(patient_id: Optional[str] = Query(None)):
    """
    Get all active/escalated ICU deterioration events.
    Used by M26 (ER Patient Alert) and M29 (Threshold-Based Alerts).
    """
    db = get_db()
    return det.get_active_deterioration_events(db, patient_id)


@app.get("/api/icu-vitals/deterioration/{event_id}", tags=["Deterioration"])
def get_deterioration_event(event_id: str = Path(...)):
    """Get a single deterioration event with full escalation history."""
    db = get_db()
    ev = det.get_event_by_id(db, event_id)
    if not ev:
        raise HTTPException(404, "Event not found.")
    return ev


@app.post("/api/icu-vitals/deterioration/{event_id}/escalate", tags=["Deterioration"])
def escalate_event(event_id: str, body: DeteriorationEscalate):
    """
    Escalate a deterioration event to RRT / ICU Consultant / Code Blue Team.
    Sends outbound webhook to M26 (ER Alert) on escalation.
    """
    db = get_db()
    modified = det.escalate_event(
        db, event_id, body.escalated_to, body.note or "", body.escalated_by
    )
    if not modified:
        raise HTTPException(404, "Event not found or already resolved.")

    # Outbound push to M26/M29 (stub)
    _push_to_downstream_modules(event_id, body.escalated_to)

    return {"escalated": True, "escalated_to": body.escalated_to}


@app.post("/api/icu-vitals/deterioration/{event_id}/resolve", tags=["Deterioration"])
def resolve_event(event_id: str, body: DeteriorationResolve):
    """Resolve a deterioration event and record clinical outcome."""
    db = get_db()
    modified = det.resolve_event(
        db, event_id, body.outcome, body.resolved_by, body.notes or ""
    )
    if not modified:
        raise HTTPException(404, "Event not found or already resolved.")
    return {"resolved": True, "outcome": body.outcome}


@app.get("/api/icu-vitals/patients/{patient_id}/deterioration-history", tags=["Deterioration"])
def get_deterioration_history(
    patient_id: str,
    limit: int = Query(50, ge=1, le=200),
):
    """
    Full deterioration timeline for a patient.
    Used by M30 (Time-Series Analysis) for risk trajectory modelling.
    """
    db = get_db()
    return det.get_deterioration_history(db, patient_id, limit)


# =============================================================================
# INTER-MODULE WEBHOOKS
# =============================================================================

@app.post("/api/icu-vitals/webhooks/drug-alert", tags=["Webhooks"])
def receive_drug_alert(body: DrugAlertWebhook):
    """
    Inbound webhook FROM Module 23 (High-Risk Drug Monitor).
    Adjusts patient-specific vital sign thresholds when a sedative or
    vasopressor is administered, preventing false alert storms.
    """
    db = get_db()
    adjusted: List[str] = []

    overrides = {
        "heart_rate":      (body.heart_rate_min,       body.heart_rate_max),
        "systolic_bp":     (body.systolic_bp_min,      body.systolic_bp_max),
        "respiratory_rate": (body.respiratory_rate_min, body.respiratory_rate_max),
    }

    for param, (mn, mx) in overrides.items():
        if mn is not None or mx is not None:
            # Fall back to defaults if only one bound provided
            defaults = alerts.DEFAULT_THRESHOLDS.get(param, {})
            alerts.apply_drug_adjustment(
                db, body.patient_id, body.drug_name, param,
                mn if mn is not None else defaults.get("min_val"),
                mx if mx is not None else defaults.get("max_val"),
            )
            adjusted.append(param)

    return {
        "acknowledged": True,
        "patient_id": body.patient_id,
        "drug": body.drug_name,
        "thresholds_adjusted": adjusted,
        "message": f"Thresholds temporarily widened for {body.drug_name}.",
    }


@app.post("/api/icu-vitals/webhooks/push-alert", tags=["Webhooks"])
def push_alert_to_downstream(payload: Dict[str, Any]):
    """
    Outbound stub TO Module 26 (ER Patient Alert) and Module 29 (Threshold Alerts).
    In production, this would POST to their respective /webhooks/receive endpoints.
    """
    # Stub — log and return confirm
    return {"pushed": True, "payload_received": payload,
            "note": "Stub endpoint. Route to M26/M29 in production."}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _push_to_downstream_modules(event_id: str, escalated_to: str):
    """
    Stub: push escalation notifications to M26 (ER Alert) and M29 (Threshold Alerts).
    In production: use httpx.post() to call their webhook endpoints.
    """
    # e.g. httpx.post("http://m26-service/webhooks/receive", json={...})
    pass
