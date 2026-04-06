"""
schemas.py – Pydantic Request/Response Models
Module 25: ICU Vital Signs Monitoring | REST API Layer
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class DeteriorationType(str, Enum):
    RESPIRATORY = "Respiratory"
    CARDIOVASCULAR = "Cardiovascular"
    NEUROLOGICAL = "Neurological"
    RENAL = "Renal"
    HEPATIC = "Hepatic"
    COAGULATION = "Coagulation"
    COMPOSITE = "Composite"
    SEPSIS = "Sepsis"


# ---------------------------------------------------------------------------
# Vital Sign Ingestion
# ---------------------------------------------------------------------------

class VitalSignIngest(BaseModel):
    """POST /api/icu-vitals/ingest — from bedside monitor telemetry"""
    patient_id: str
    device_id: Optional[str] = None

    # Haemodynamic
    systolic_bp: float      = Field(..., ge=40,  le=300,  description="mmHg")
    diastolic_bp: float     = Field(..., ge=20,  le=200)
    heart_rate: int         = Field(..., ge=20,  le=300,  description="BPM")

    # Respiratory
    respiratory_rate: int   = Field(..., ge=1,   le=80,   description="breaths/min")
    spo2: float             = Field(..., ge=50,  le=100,  description="SpO2 %")
    supplemental_oxygen: bool = False
    respiratory_support: str  = "None"

    # Neurological
    consciousness_level: str  = Field("Alert", description="ACVPU scale")

    # Metabolic
    temperature: float      = Field(37.0, ge=28.0, le=45.0, description="Celsius")
    urine_output_ml_hr: Optional[float] = Field(None, ge=0)
    pain_score: int         = Field(0, ge=0, le=10)

    # Optional lab values (for APACHE II / SAPS II / SOFA)
    platelet_count: Optional[float] = None     # x10^3/μL
    bilirubin_umol: Optional[float] = None     # μmol/L
    creatinine_mg_dl: Optional[float] = None   # mg/dL
    wbc_count: Optional[float] = None          # x10^3/μL
    hematocrit: Optional[float] = None         # %
    sodium: Optional[float] = None             # mEq/L
    potassium: Optional[float] = None          # mEq/L
    bun_mg_dl: Optional[float] = None          # mg/dL
    
    # Blood Gas (ABG)
    pao2_mmhg: Optional[float] = None          # mmHg
    fio2_pct: Optional[float] = None           # % (21.0 to 100.0)
    ph: Optional[float] = None
    hco3_meq_l: Optional[float] = None         # mEq/L
    
    # Chronic health modifiers
    chronic_health_points: int = 0             # APACHE II chronic health points (0-5)
    admission_type: str = "Medical"            # SAPS II: Medical, ScheduledSurgical, UnscheduledSurgical
    
    # SpO2 scale override (for COPD/type-2 RF patients)
    use_spo2_scale2: bool = False


class ManualEntryRequest(BaseModel):
    """POST /api/icu-vitals/manual-entry — nurse manual documentation"""
    patient_id: str
    systolic_bp: float
    diastolic_bp: float
    heart_rate: int
    respiratory_rate: int
    spo2: float
    supplemental_oxygen: bool = False
    respiratory_support: str  = "None"
    consciousness_level: str  = "Alert"
    temperature: float        = 37.0
    urine_output_ml_hr: Optional[float] = None
    pain_score: int           = 0
    recorded_by: Optional[str] = None     # nurse/clinician name
    notes: Optional[str]      = None

class VitalSignUpdate(BaseModel):
    """PUT /api/icu-vitals/vitals/{vital_id} — partial vital signs update"""
    systolic_bp: Optional[float] = None
    diastolic_bp: Optional[float] = None
    heart_rate: Optional[int] = None
    respiratory_rate: Optional[int] = None
    spo2: Optional[float] = None
    supplemental_oxygen: Optional[bool] = None
    respiratory_support: Optional[str] = None
    consciousness_level: Optional[str] = None
    temperature: Optional[float] = None
    urine_output_ml_hr: Optional[float] = None
    pain_score: Optional[int] = None


# ---------------------------------------------------------------------------
# Alert Management
# ---------------------------------------------------------------------------

class AlertAcknowledge(BaseModel):
    """PUT /api/icu-vitals/alerts/{alert_id}/acknowledge"""
    acknowledged_by: Optional[str] = None


class AlertIntervention(BaseModel):
    """POST /api/icu-vitals/alerts/{alert_id}/intervene"""
    intervention_type: str
    notes: Optional[str]        = None
    performed_by: Optional[str] = None
    resolve: bool               = True


# ---------------------------------------------------------------------------
# Deterioration Events
# ---------------------------------------------------------------------------

class DeteriorationEscalate(BaseModel):
    """POST /api/icu-vitals/deterioration/{event_id}/escalate"""
    escalated_to: str          # 'RRT' | 'ICU Consultant' | 'Code Blue Team' | ...
    note: Optional[str]        = None
    escalated_by: Optional[str] = None


class DeteriorationResolve(BaseModel):
    """POST /api/icu-vitals/deterioration/{event_id}/resolve"""
    outcome: str               # 'Stabilised' | 'Transferred to ICU' | ...
    resolved_by: Optional[str] = None
    notes: Optional[str]       = None


# ---------------------------------------------------------------------------
# Inter-module Webhooks
# ---------------------------------------------------------------------------

class DrugAlertWebhook(BaseModel):
    """
    POST /api/icu-vitals/webhooks/drug-alert
    Received FROM Module 23 (High-Risk Drug Monitor).
    Adjusts vital sign thresholds when sedatives/vasopressors are administered.
    """
    patient_id: str
    drug_name: str             # e.g. 'Dexmedetomidine', 'Norepinephrine'
    drug_class: str            # e.g. 'Sedative', 'Vasopressor', 'Beta-blocker'
    administered_at: Optional[datetime] = None
    # Suggested threshold overrides
    heart_rate_min: Optional[float] = None
    heart_rate_max: Optional[float] = None
    systolic_bp_min: Optional[float] = None
    systolic_bp_max: Optional[float] = None
    respiratory_rate_min: Optional[float] = None
    respiratory_rate_max: Optional[float] = None


# ---------------------------------------------------------------------------
# Patient Admission
# ---------------------------------------------------------------------------

class PatientAdmit(BaseModel):
    """POST /api/icu-vitals/patients — admit a new ICU patient with device"""
    patient_id: str
    first_name: str
    last_name: Optional[str]          = ""
    gender: str                        = "Other"
    date_of_birth: Optional[str]       = None
    mrn: Optional[str]                 = None
    device_id: str
    device_type: str                   = "Multi-parameter Monitor"
    admission_status: str              = "ICU"
    acuity_level: int                  = Field(2, ge=1, le=4)
    admitting_diagnosis: Optional[str] = None


# ---------------------------------------------------------------------------
# Threshold Rule
# ---------------------------------------------------------------------------

class ThresholdRule(BaseModel):
    """POST /api/icu-vitals/patients/{patient_id}/thresholds"""
    patient_id: str
    parameter: str
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    adjusted_for_drugs: bool  = False
    adjustment_reason: Optional[str] = None
