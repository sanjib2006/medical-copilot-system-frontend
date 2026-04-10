"""
api_client.py – HTTP client for Module 25 ICU Vital Signs backend API
All Streamlit UI interactions go through this module; no direct DB access.

Base URL read from MODULE25_API_URL env var (default: http://localhost:8001)
"""

import os
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

_BASE_URL = os.getenv("MODULE25_API_URL", "http://localhost:8001").rstrip("/")


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _get(path: str, params: Optional[Dict] = None) -> Any:
    url = f"{_BASE_URL}{path}"
    r = requests.get(url, params=params, timeout=10)
    _raise_for_status(r)
    return r.json()


def _post(path: str, payload: Optional[Dict] = None) -> Any:
    url = f"{_BASE_URL}{path}"
    r = requests.post(url, json=payload or {}, timeout=10)
    _raise_for_status(r)
    return r.json()


def _put(path: str, payload: Optional[Dict] = None) -> Any:
    url = f"{_BASE_URL}{path}"
    r = requests.put(url, json=payload or {}, timeout=10)
    _raise_for_status(r)
    return r.json()


def _raise_for_status(r: requests.Response):
    if not r.ok:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(f"API error {r.status_code}: {detail}")


# ── Health ────────────────────────────────────────────────────────────────────

def health_check() -> Dict:
    return _get("/api/icu-vitals/health")


# ── Patients ──────────────────────────────────────────────────────────────────

def get_all_patients() -> List[Dict]:
    """Return list of all admitted ICU patients."""
    return _get("/api/icu-vitals/patients")


def admit_patient(
    patient_id: str,
    first_name: str,
    last_name: str,
    gender: str,
    dob: str,
    device_id: str,
    device_type: str,
    mrn: Optional[str] = None,
    admission_status: str = "ICU",
    acuity_level: int = 2,
    admitting_diagnosis: str = "",
) -> Dict:
    """Admit a new patient to the ICU."""
    payload = {
        "patient_id": patient_id,
        "first_name": first_name,
        "last_name": last_name,
        "gender": gender,
        "date_of_birth": dob,
        "device_id": device_id,
        "device_type": device_type,
        "mrn": mrn,
        "admission_status": admission_status,
        "acuity_level": acuity_level,
        "admitting_diagnosis": admitting_diagnosis,
    }
    return _post("/api/icu-vitals/patients", payload)


# ── Vital Signs ───────────────────────────────────────────────────────────────

def record_vitals(
    patient_id: str,
    systolic_bp: float,
    diastolic_bp: float,
    heart_rate: int,
    respiratory_rate: int,
    spo2: float,
    supplemental_oxygen: bool,
    respiratory_support: str,
    consciousness_level: str,
    temperature: float,
    urine_output_ml_hr: Optional[float],
    pain_score: int,
) -> Dict:
    """Submit manual vital signs entry; returns computed NEWS2/SOFA/APACHE II."""
    payload = {
        "patient_id": patient_id,
        "systolic_bp": systolic_bp,
        "diastolic_bp": diastolic_bp,
        "heart_rate": heart_rate,
        "respiratory_rate": respiratory_rate,
        "spo2": spo2,
        "supplemental_oxygen": supplemental_oxygen,
        "respiratory_support": respiratory_support,
        "consciousness_level": consciousness_level,
        "temperature": temperature,
        "urine_output_ml_hr": urine_output_ml_hr,
        "pain_score": pain_score,
    }
    return _post("/api/icu-vitals/manual-entry", payload)


def get_vitals(patient_id: str, limit: int = 50) -> List[Dict]:
    """Return paginated list of raw vital sign records for a patient."""
    return _get(f"/api/icu-vitals/patients/{patient_id}/vitals", {"limit": limit})


def get_trends(patient_id: str, interval: str = "hourly") -> Dict:
    """Return aggregated vital trend data."""
    return _get(f"/api/icu-vitals/patients/{patient_id}/trends", {"interval": interval})


def get_critical_patients() -> List[Dict]:
    """Return patients with NEWS2 >= 7 or MODS (Doctor/Admin view)."""
    return _get("/api/icu-vitals/views/critical-patients")


# ── Alerts ────────────────────────────────────────────────────────────────────

def get_active_alerts(patient_id: Optional[str] = None) -> List[Dict]:
    """Return all active threshold alerts, optionally filtered by patient."""
    params = {"patient_id": patient_id} if patient_id else {}
    return _get("/api/icu-vitals/alerts/active", params)


def save_threshold(
    patient_id: str,
    parameter: str,
    min_val: float,
    max_val: float,
    adjusted_for_drugs: bool = False,
    adjustment_reason: str = "",
) -> Dict:
    """Create or update a patient-specific threshold rule."""
    payload = {
        "patient_id": patient_id,
        "parameter": parameter,
        "min_val": min_val,
        "max_val": max_val,
        "adjusted_for_drugs": adjusted_for_drugs,
        "adjustment_reason": adjustment_reason,
    }
    return _post(f"/api/icu-vitals/patients/{patient_id}/thresholds", payload)


def log_intervention(
    alert_id: str,
    intervention_type: str,
    notes: str = "",
    performed_by: Optional[str] = None,
    resolve: bool = True,
) -> Dict:
    """Log a clinical intervention and optionally resolve the alert."""
    payload = {
        "intervention_type": intervention_type,
        "notes": notes,
        "performed_by": performed_by,
        "resolve": resolve,
    }
    return _post(f"/api/icu-vitals/alerts/{alert_id}/intervene", payload)


# ── Deterioration Events ──────────────────────────────────────────────────────

def get_active_deterioration(patient_id: Optional[str] = None) -> List[Dict]:
    """Return active/escalated ICU deterioration events."""
    params = {"patient_id": patient_id} if patient_id else {}
    return _get("/api/icu-vitals/deterioration", params)


def escalate_event(
    event_id: str,
    escalated_to: str,
    note: str = "",
) -> Dict:
    """Escalate a deterioration event."""
    return _post(f"/api/icu-vitals/deterioration/{event_id}/escalate", {
        "escalated_to": escalated_to,
        "note": note,
    })


def resolve_event(
    event_id: str,
    outcome: str,
    resolved_by: str = "",
    notes: str = "",
) -> Dict:
    """Resolve a deterioration event and record the clinical outcome."""
    return _post(f"/api/icu-vitals/deterioration/{event_id}/resolve", {
        "outcome": outcome,
        "resolved_by": resolved_by,
        "notes": notes,
    })


def get_deterioration_history(patient_id: str, limit: int = 50) -> List[Dict]:
    """Return the full deterioration timeline for a patient."""
    return _get(
        f"/api/icu-vitals/patients/{patient_id}/deterioration-history",
        {"limit": limit},
    )


# ── DB Engine (Tab 5) ─────────────────────────────────────────────────────────

def get_server_functions() -> str:
    """Return the JS stored procedures code block."""
    data = _get("/api/icu-vitals/db-info/server-functions")
    return data.get("js_code", "")
