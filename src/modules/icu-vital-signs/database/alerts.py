from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId
from pymongo import ASCENDING

def _now_utc() -> datetime:
    return datetime.utcnow().replace(tzinfo=timezone.utc)

def ensure_indexes(db):
    db.threshold_rules.create_index([("patient_id", ASCENDING), ("parameter", ASCENDING)], unique=True)
    db.deterioration_alerts.create_index([("patient_id", ASCENDING), ("status", ASCENDING)])
    db.deterioration_alerts.create_index([("alert_datetime", ASCENDING)])

def set_threshold(db, patient_id: Any, parameter: str, min_val: float, max_val: float):
    rule = {
        "patient_id": patient_id,
        "parameter": parameter,
        "min_val": float(min_val),
        "max_val": float(max_val),
        "updated_at": _now_utc(),
    }

    result = db.threshold_rules.update_one(
        {"patient_id": patient_id, "parameter": parameter},
        {"$set": rule},
        upsert=True,
    )

    return {
        "matched_count": result.matched_count,
        "modified_count": result.modified_count,
        "upserted_id": str(result.upserted_id) if result.upserted_id else None,
    }

def get_thresholds(db, patient_id: Any):
    return list(db.threshold_rules.find({"patient_id": patient_id}, {"_id": 0}))

def create_alert(db, patient_id: Any, vital_sign_id: Any, alert_type: str, message: str, severity: str = "medium", metadata: Optional[Dict[str, Any]] = None):
    alert_doc = {
        "patient_id": patient_id,
        "vital_sign_id": vital_sign_id,
        "alert_type": alert_type,
        "message": message,
        "severity": severity,
        "status": "Active",
        "acknowledged": False,
        "created_at": _now_utc(),
        "alert_datetime": _now_utc(),
        "interventions": [],
        "metadata": metadata or {},
    }

    res = db.deterioration_alerts.insert_one(alert_doc)
    return str(res.inserted_id)

def get_active_alerts(db, patient_id: Optional[Any] = None):
    q = {"status": "Active"}
    if patient_id is not None:
        q["patient_id"] = patient_id

    docs = list(db.deterioration_alerts.find(q))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs

def acknowledge_alert(db, alert_id: str, acknowledged_by: Optional[str] = None):
    result = db.deterioration_alerts.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {"acknowledged": True, "acknowledged_at": _now_utc(), "acknowledged_by": acknowledged_by}},
    )
    return result.modified_count

def log_intervention(db, alert_id: str, intervention_type: str, notes: Optional[str] = None, performed_by: Optional[str] = None, resolve: bool = True):
    intervention = {
        "timestamp": _now_utc(),
        "intervention_type": intervention_type,
        "notes": notes or "",
        "performed_by": performed_by,
    }

    update_ops = {"$push": {"interventions": intervention}}
    if resolve:
        update_ops["$set"] = {"status": "Resolved", "resolved_at": _now_utc()}

    result = db.deterioration_alerts.update_one({"_id": ObjectId(alert_id)}, update_ops)
    return result.modified_count

def evaluate_alert(db, patient_id: Any, vital_sign_id: Any, current_vitals: Dict[str, Any]):
    created_alert_ids = []
    rules = list(db.threshold_rules.find({"patient_id": patient_id}))
    normalized_vitals = {k.lower(): v for k, v in current_vitals.items()}

    for rule in rules:
        param = rule.get("parameter", "").lower()
        if not param:
            continue

        syn_map = {
            "heart rate": "heart_rate",
            "systolic bp": "systolic_bp",
            "diastolic bp": "diastolic_bp",
            "temperature": "temperature",
            "ews score": "ews_score",
        }
        mapped = syn_map.get(param, param)

        if mapped in normalized_vitals:
            val = normalized_vitals[mapped]
        else:
            continue

        try:
            val_float = float(val)
        except ValueError:
            continue

        min_val = rule.get("min_val")
        max_val = rule.get("max_val")

        breached = False
        direction = "normal"
        if min_val is not None and val_float < float(min_val):
            breached = True
            direction = "low"
        elif max_val is not None and val_float > float(max_val):
            breached = True
            direction = "high"

        if breached:
            span = (float(max_val) - float(min_val)) if (max_val is not None and min_val is not None and float(max_val) > float(min_val)) else None
            severity = "medium"
            if span:
                diff = (val_float - float(max_val)) if direction == "high" else (float(min_val) - val_float)
                rel = diff / span
                if rel >= 0.5:
                    severity = "critical"
                elif rel >= 0.2:
                    severity = "high"

            alert_type = f"Threshold breach: {rule.get('parameter')} ({direction})"
            message = f"Parameter {rule.get('parameter')} is {direction} (value={val_float}, allowed=[{min_val},{max_val}])."
            
            metadata = {
                "parameter": rule.get("parameter"),
                "observed_value": val_float,
                "min_val": min_val,
                "max_val": max_val,
                "direction": direction,
            }

            alert_id = create_alert(db, patient_id, vital_sign_id, alert_type, message, severity, metadata)
            created_alert_ids.append(alert_id)

    return created_alert_ids