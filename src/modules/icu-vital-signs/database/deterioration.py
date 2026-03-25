"""
deterioration.py – ICU Deterioration Event Tracker
Module 25: ICU Vital Signs Monitoring

Collection: icu_deterioration_events

A deterioration event is a clinical episode where a patient's composite
scoring (NEWS2 >= 7 or SOFA worsens by >= 2) indicates imminent risk.
Each event has its own lifecycle: Active → Escalated → Resolved.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING


def _now_utc() -> datetime:
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def ensure_indexes(db):
    db.icu_deterioration_events.create_index(
        [("patient_id", ASCENDING), ("status", ASCENDING)]
    )
    db.icu_deterioration_events.create_index(
        [("triggered_at", DESCENDING)]
    )
    db.icu_deterioration_events.create_index(
        [("patient_id", ASCENDING), ("triggered_at", DESCENDING)]
    )


def create_deterioration_event(
    db,
    patient_id: Any,
    vital_sign_id: Any,
    news2_result: Dict,
    sofa_result: Dict,
    trigger_source: str = "NEWS2",
) -> str:
    """
    Create a new ICU deterioration event.

    trigger_source: 'NEWS2' | 'SOFA' | 'Manual' | 'Drug-Interaction'
    """
    doc = {
        "patient_id": patient_id,
        "vital_sign_id": vital_sign_id,
        "triggered_at": _now_utc(),
        "trigger_source": trigger_source,

        # Snapshot of scores at time of event
        "news2_score": news2_result.get("total_news2"),
        "news2_risk_band": news2_result.get("risk_band"),
        "news2_components": news2_result.get("components", {}),
        "sofa_score": sofa_result.get("total_sofa"),
        "sofa_risk_level": sofa_result.get("risk_level"),
        "sofa_organ_scores": sofa_result.get("organ_scores", {}),
        "multi_organ_dysfunction": sofa_result.get("multi_organ_dysfunction", False),

        # Severity derived from NEWS2 band
        "severity": _derive_severity(news2_result.get("risk_band", "Medium")),
        
        # Determine specific deterioration phenotype
        "deterioration_type": _classify_deterioration_type(news2_result, sofa_result),

        # Lifecycle
        "status": "Active",  # Active | Escalated | Resolved

        # Escalation audit trail
        "escalation_history": [],

        # Resolution
        "resolution": None,
    }

    res = db.icu_deterioration_events.insert_one(doc)
    return str(res.inserted_id)


def _derive_severity(news2_band: str) -> str:
    mapping = {
        "Low":         "Yellow",
        "Low-Medium":  "Yellow",
        "Medium":      "Amber",
        "High":        "Red",
    }
    return mapping.get(news2_band, "Amber")


def _classify_deterioration_type(news2_result: Dict, sofa_result: Dict) -> str:
    sofa_organs = sofa_result.get("organ_scores", {})
    news2_components = news2_result.get("components", {})
    
    # Check if multiple systems are highly deranged
    high_sofa_count = sum(1 for v in sofa_organs.values() if v >= 2)
    if high_sofa_count >= 2:
        return "Composite"
        
    # Cardiovascular
    if sofa_organs.get("cardiovascular", 0) >= 2 or news2_components.get("systolic_bp", 0) >= 3 or news2_components.get("heart_rate", 0) >= 3:
        return "Cardiovascular"
        
    # Respiratory
    if sofa_organs.get("respiratory", 0) >= 2 or news2_components.get("spo2", 0) >= 3 or news2_components.get("respiratory_rate", 0) >= 3:
        return "Respiratory"
        
    # Neurological
    if sofa_organs.get("cns", 0) >= 2 or news2_components.get("consciousness", 0) >= 3:
        return "Neurological"
        
    # Renal
    if sofa_organs.get("renal", 0) >= 2:
        return "Renal"
        
    # Hepatic
    if sofa_organs.get("liver", 0) >= 2:
        return "Hepatic"
        
    # Coagulation
    if sofa_organs.get("coagulation", 0) >= 2:
        return "Coagulation"
        
    return "Composite"


def get_active_deterioration_events(
    db, patient_id: Optional[Any] = None
) -> List[Dict]:
    """Fetch all Active or Escalated deterioration events."""
    q: Dict[str, Any] = {"status": {"$in": ["Active", "Escalated"]}}
    if patient_id is not None:
        q["patient_id"] = patient_id

    docs = list(
        db.icu_deterioration_events.find(q).sort("triggered_at", DESCENDING)
    )
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


def get_deterioration_history(
    db, patient_id: Any, limit: int = 50
) -> List[Dict]:
    """Full deterioration event history for a patient (all statuses)."""
    docs = list(
        db.icu_deterioration_events
        .find({"patient_id": patient_id})
        .sort("triggered_at", DESCENDING)
        .limit(limit)
    )
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


def escalate_event(
    db,
    event_id: str,
    escalated_to: str,
    note: str = "",
    escalated_by: Optional[str] = None,
) -> int:
    """
    Escalate a deterioration event.
    escalated_to: e.g. 'RRT', 'ICU Consultant', 'Attending Physician', 'Code Blue'
    """
    entry = {
        "escalated_at": _now_utc(),
        "escalated_to": escalated_to,
        "escalated_by": escalated_by,
        "note": note,
    }

    result = db.icu_deterioration_events.update_one(
        {"_id": ObjectId(event_id)},
        {
            "$push": {"escalation_history": entry},
            "$set": {
                "status": "Escalated",
                "last_escalated_at": _now_utc(),
                "last_escalated_to": escalated_to,
            },
        },
    )
    return result.modified_count


def resolve_event(
    db,
    event_id: str,
    outcome: str,
    resolved_by: Optional[str] = None,
    notes: str = "",
) -> int:
    """
    Resolve a deterioration event.
    outcome: e.g. 'Stabilised', 'Transferred to ICU', 'Transferred to HDU',
             'Palliative Care', 'Deceased', 'False Alarm'
    """
    resolution = {
        "resolved_at": _now_utc(),
        "outcome": outcome,
        "resolved_by": resolved_by,
        "notes": notes,
    }

    result = db.icu_deterioration_events.update_one(
        {"_id": ObjectId(event_id)},
        {"$set": {"status": "Resolved", "resolution": resolution}},
    )
    return result.modified_count


def get_event_by_id(db, event_id: str) -> Optional[Dict]:
    doc = db.icu_deterioration_events.find_one({"_id": ObjectId(event_id)})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def has_active_event(db, patient_id: Any) -> bool:
    """Check if patient already has an active/escalated deterioration event."""
    return bool(
        db.icu_deterioration_events.find_one(
            {"patient_id": patient_id, "status": {"$in": ["Active", "Escalated"]}}
        )
    )
