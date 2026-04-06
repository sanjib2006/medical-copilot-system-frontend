"""
alerts.py – Alert Management & Threshold Evaluation
Module 25: ICU Vital Signs Monitoring

Manages threshold rules, deterioration alerts, and interventions.
Severity mapping aligns with NEWS2 risk bands:
  Yellow → Amber → Red → Code Blue
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING


def _now_utc() -> datetime:
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def _serialize_doc(doc):
    """Recursively convert all ObjectId values to strings so FastAPI can JSON-encode them."""
    if isinstance(doc, dict):
        return {k: _serialize_doc(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [_serialize_doc(v) for v in doc]
    if isinstance(doc, ObjectId):
        return str(doc)
    return doc


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------
def ensure_indexes(db):
    db.threshold_rules.create_index(
        [("patient_id", ASCENDING), ("parameter", ASCENDING)], unique=True
    )
    db.deterioration_alerts.create_index(
        [("patient_id", ASCENDING), ("status", ASCENDING)]
    )
    db.deterioration_alerts.create_index([("alert_datetime", DESCENDING)])
    db.deterioration_alerts.create_index([("severity", ASCENDING)])


# ---------------------------------------------------------------------------
# Threshold Rules (patient-specific or global)
# ---------------------------------------------------------------------------
DEFAULT_THRESHOLDS = {
    "heart_rate":    {"min_val": 60.0,  "max_val": 100.0},
    "systolic_bp":   {"min_val": 90.0,  "max_val": 140.0},
    "diastolic_bp":  {"min_val": 60.0,  "max_val": 90.0},
    "temperature":   {"min_val": 36.0,  "max_val": 38.5},
    "spo2":          {"min_val": 94.0,  "max_val": 100.0},
    "respiratory_rate": {"min_val": 12.0, "max_val": 20.0},
    "urine_output_ml_hr": {"min_val": 30.0, "max_val": None},
}


def set_threshold(
    db,
    patient_id: Any,
    parameter: str,
    min_val: Optional[float],
    max_val: Optional[float],
    adjusted_for_drugs: bool = False,
    adjustment_reason: str = "",
) -> Dict:
    rule = {
        "patient_id": patient_id,
        "parameter": parameter,
        "min_val": float(min_val) if min_val is not None else None,
        "max_val": float(max_val) if max_val is not None else None,
        "updated_at": _now_utc(),
        "adjusted_for_drugs": adjusted_for_drugs,
        "adjustment_reason": adjustment_reason,
    }

    result = db.threshold_rules.update_one(
        {"patient_id": patient_id, "parameter": parameter},
        {"$set": rule},
        upsert=True,
    )

    return {
        "matched_count":  result.matched_count,
        "modified_count": result.modified_count,
        "upserted_id":    str(result.upserted_id) if result.upserted_id else None,
    }


def get_thresholds(db, patient_id: Any) -> List[Dict]:
    return list(db.threshold_rules.find({"patient_id": patient_id}, {"_id": 0}))


def apply_drug_adjustment(
    db, patient_id: Any, drug_name: str, parameter: str, new_min: float, new_max: float
) -> Dict:
    """
    M23 (High-Risk Drug Monitor) calls this when a sedative/vasopressor is
    administered, to temporarily widen thresholds and prevent false alerts.
    """
    return set_threshold(
        db, patient_id, parameter, new_min, new_max,
        adjusted_for_drugs=True,
        adjustment_reason=f"Drug: {drug_name}",
    )


# ---------------------------------------------------------------------------
# Deterioration Alerts
# ---------------------------------------------------------------------------

def _news2_to_severity(news2_score: int) -> str:
    if news2_score >= 9:  return "code_blue"
    if news2_score >= 7:  return "red"
    if news2_score >= 5:  return "amber"
    return "yellow"


def create_alert(
    db,
    patient_id: Any,
    vital_sign_id: Any,
    alert_type: str,
    message: str,
    severity: str = "yellow",
    news2_score: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    alert_doc = {
        "patient_id":    patient_id,
        "vital_sign_id": vital_sign_id,
        "alert_type":    alert_type,
        "message":       message,
        "severity":      severity,           # yellow | amber | red | code_blue
        "status":        "Active",
        "acknowledged":  False,
        "news2_score":   news2_score,
        "created_at":    _now_utc(),
        "alert_datetime": _now_utc(),
        "interventions": [],
        "metadata":      metadata or {},
    }

    res = db.deterioration_alerts.insert_one(alert_doc)
    return str(res.inserted_id)


def get_active_alerts(db, patient_id: Optional[Any] = None) -> List[Dict]:
    q: Dict[str, Any] = {"status": "Active"}
    if patient_id is not None:
        q["patient_id"] = patient_id

    docs = list(db.deterioration_alerts.find(q).sort("alert_datetime", DESCENDING))
    return [_serialize_doc(d) for d in docs]


def acknowledge_alert(
    db, alert_id: str, acknowledged_by: Optional[str] = None
) -> int:
    result = db.deterioration_alerts.update_one(
        {"_id": ObjectId(alert_id)},
        {
            "$set": {
                "acknowledged":    True,
                "acknowledged_at": _now_utc(),
                "acknowledged_by": acknowledged_by,
            }
        },
    )
    return result.modified_count


def log_intervention(
    db,
    alert_id: str,
    intervention_type: str,
    notes: Optional[str] = None,
    performed_by: Optional[str] = None,
    resolve: bool = True,
) -> int:
    intervention = {
        "timestamp":         _now_utc(),
        "intervention_type": intervention_type,
        "notes":             notes or "",
        "performed_by":      performed_by,
    }

    update_ops: Dict[str, Any] = {"$push": {"interventions": intervention}}
    if resolve:
        update_ops["$set"] = {"status": "Resolved", "resolved_at": _now_utc()}

    result = db.deterioration_alerts.update_one(
        {"_id": ObjectId(alert_id)}, update_ops
    )
    return result.modified_count


# ---------------------------------------------------------------------------
# Threshold Evaluation (called after each vital sign insert)
# ---------------------------------------------------------------------------

_PARAM_ALIASES: Dict[str, str] = {
    "heart rate":       "heart_rate",
    "systolic bp":      "systolic_bp",
    "diastolic bp":     "diastolic_bp",
    "temperature":      "temperature",
    "ews score":        "news2_score",
    "spo2":             "spo2",
    "respiratory rate": "respiratory_rate",
    "urine output":     "urine_output_ml_hr",
}


def evaluate_alert(
    db,
    patient_id: Any,
    vital_sign_id: Any,
    current_vitals: Dict[str, Any],
    news2_score: Optional[int] = None,
) -> List[str]:
    """
    Evaluate all threshold rules for a patient against the latest vitals.
    Returns list of created alert IDs.
    """
    created_ids: List[str] = []
    rules = list(db.threshold_rules.find({"patient_id": patient_id}))

    if not rules:
        # Apply default global thresholds if no patient-specific rules set
        for param, bounds in DEFAULT_THRESHOLDS.items():
            raw = current_vitals.get(param)
            if raw is None:
                continue
            try:
                val = float(raw)
            except (ValueError, TypeError):
                continue

            min_v = bounds.get("min_val")
            max_v = bounds.get("max_val")
            direction = None

            if min_v is not None and val < min_v:
                direction = "low"
            elif max_v is not None and val > max_v:
                direction = "high"

            if direction:
                sev = _compute_severity(val, min_v, max_v, direction, news2_score)
                alert_id = create_alert(
                    db, patient_id, vital_sign_id,
                    alert_type=f"Threshold breach: {param} ({direction})",
                    message=f"{param} is {direction} (value={val}, allowed=[{min_v},{max_v}])",
                    severity=sev,
                    news2_score=news2_score,
                    metadata={"parameter": param, "value": val,
                              "min_val": min_v, "max_val": max_v, "direction": direction},
                )
                created_ids.append(alert_id)
        return created_ids

    normalized = {k.lower(): v for k, v in current_vitals.items()}

    for rule in rules:
        param = rule.get("parameter", "").lower()
        mapped = _PARAM_ALIASES.get(param, param)

        val_raw = normalized.get(mapped)
        if val_raw is None:
            continue

        try:
            val = float(val_raw)
        except (ValueError, TypeError):
            continue

        min_v = rule.get("min_val")
        max_v = rule.get("max_val")
        direction = None

        if min_v is not None and val < float(min_v):
            direction = "low"
        elif max_v is not None and val > float(max_v):
            direction = "high"

        if direction:
            sev = _compute_severity(val, min_v, max_v, direction, news2_score)
            alert_id = create_alert(
                db, patient_id, vital_sign_id,
                alert_type=f"Threshold breach: {rule.get('parameter')} ({direction})",
                message=(
                    f"{rule.get('parameter')} is {direction} "
                    f"(value={val}, allowed=[{min_v},{max_v}])"
                    + (f" — adjusted for drugs: {rule.get('adjustment_reason')}"
                       if rule.get("adjusted_for_drugs") else "")
                ),
                severity=sev,
                news2_score=news2_score,
                metadata={
                    "parameter":      rule.get("parameter"),
                    "observed_value": val,
                    "min_val":        min_v,
                    "max_val":        max_v,
                    "direction":      direction,
                    "drug_adjusted":  rule.get("adjusted_for_drugs", False),
                },
            )
            created_ids.append(alert_id)

    return created_ids


def _compute_severity(
    val: float,
    min_v: Optional[float],
    max_v: Optional[float],
    direction: str,
    news2_score: Optional[int],
) -> str:
    """Compute alert severity from NEWS2 score and deviation magnitude."""
    # If we have a NEWS2 score, use it as primary driver
    if news2_score is not None:
        return _news2_to_severity(news2_score)

    # Fallback: magnitude-based
    if min_v is not None and max_v is not None:
        span = float(max_v) - float(min_v)
        if span > 0:
            diff = (val - float(max_v)) if direction == "high" else (float(min_v) - val)
            rel = diff / span
            if rel >= 0.5: return "red"
            if rel >= 0.2: return "amber"
    return "yellow"