"""
vitals.py – Vital Signs CRUD + Scoring Pipeline
Module 25: ICU Vital Signs Monitoring

Handles high-frequency vital sign ingestion, NEWS2/SOFA/APACHE II calculation,
and deterioration event triggering.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from bson import ObjectId

from .scoring import calculate_news2, calculate_sofa, calculate_apache2, calculate_saps2
from . import deterioration as det


def _now_utc() -> datetime:
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def insert_vital_sign(
    db,
    patient_id: Any,
    # Core haemodynamic
    systolic_bp: float,
    diastolic_bp: float,
    heart_rate: int,
    # Respiratory
    respiratory_rate: int,
    spo2: float,
    supplemental_oxygen: bool = False,
    respiratory_support: str = "None",   # None | Low-flow O2 | High-flow | Ventilated
    # Neurological
    consciousness_level: str = "Alert",  # ACVPU
    # Metabolic / Renal
    temperature: float = 37.0,
    urine_output_ml_hr: Optional[float] = None,
    pain_score: int = 0,
    # Legacy / backwards compat
    use_spo2_scale2: bool = False,
    # Optional lab values (improve SOFA accuracy if available)
    platelet_count: Optional[float] = None,
    bilirubin_umol: Optional[float] = None,
    # Device
    device_id: Optional[Any] = None,
    # Patient demographics
    patient_age: int = 60,
    chronic_health_points: int = 0,
    admission_type: str = "Medical",
    # Additional Labs / ABG for APACHE II & SAPS II
    creatinine_mg_dl: Optional[float] = None,
    wbc_count: Optional[float] = None,
    hematocrit: Optional[float] = None,
    sodium: Optional[float] = None,
    potassium: Optional[float] = None,
    bun_mg_dl: Optional[float] = None,
    pao2_mmhg: Optional[float] = None,
    fio2_pct: Optional[float] = None,
    ph: Optional[float] = None,
    hco3_meq_l: Optional[float] = None,
) -> Tuple[ObjectId, Dict]:

    # ---- Scoring -----------------------------------------------------------
    news2 = calculate_news2(
        resp_rate=respiratory_rate,
        spo2=spo2,
        supplemental_o2=supplemental_oxygen,
        systolic_bp=systolic_bp,
        heart_rate=heart_rate,
        temp_c=temperature,
        consciousness=consciousness_level,
        use_spo2_scale2=use_spo2_scale2,
    )

    map_bp = round((systolic_bp + 2 * diastolic_bp) / 3, 1)

    sofa = calculate_sofa(
        spo2=spo2,
        supplemental_o2=supplemental_oxygen,
        systolic_bp=systolic_bp,
        consciousness=consciousness_level,
        urine_output_ml_hr=urine_output_ml_hr,
        platelet_count=platelet_count,
        bilirubin_umol=bilirubin_umol,
        map_bp=map_bp,
    )

    apache2 = calculate_apache2(
        age=patient_age,
        heart_rate=heart_rate,
        systolic_bp=systolic_bp,
        temp_c=temperature,
        resp_rate=respiratory_rate,
        consciousness=consciousness_level,
        chronic_health_points=chronic_health_points,
        spo2=spo2,
        pao2_mmhg=pao2_mmhg,
        fio2_pct=fio2_pct,
        ph=ph,
        sodium=sodium,
        potassium=potassium,
        creatinine_mg_dl=creatinine_mg_dl,
        hematocrit=hematocrit,
        wbc_count=wbc_count,
    )

    saps2 = calculate_saps2(
        age=patient_age,
        heart_rate=heart_rate,
        systolic_bp=systolic_bp,
        temp_c=temperature,
        consciousness=consciousness_level,
        urine_output_ml_hr=urine_output_ml_hr,
        bun_mg_dl=bun_mg_dl,
        wbc_count=wbc_count,
        potassium=potassium,
        sodium=sodium,
        hco3_meq_l=hco3_meq_l,
        bilirubin_umol=bilirubin_umol,
        pao2_mmhg=pao2_mmhg,
        fio2_pct=fio2_pct,
        admission_type=admission_type,
        chronic_diseases=(chronic_health_points > 0),
    )

    # ---- Build document ----------------------------------------------------
    record: Dict[str, Any] = {
        "patient_id": patient_id,
        "device_id": device_id,
        "recorded_datetime": _now_utc(),

        # Vital parameters
        "systolic_bp": systolic_bp,
        "diastolic_bp": diastolic_bp,
        "map_bp": map_bp,
        "heart_rate": heart_rate,
        "respiratory_rate": respiratory_rate,
        "spo2": spo2,
        "supplemental_oxygen": supplemental_oxygen,
        "respiratory_support": respiratory_support,
        "temperature": temperature,
        "consciousness_level": consciousness_level,
        "urine_output_ml_hr": urine_output_ml_hr,
        "pain_score": pain_score,

        # Clinical scores (embedded)
        "news2": news2,
        "sofa": sofa,
        "apache2": apache2,
        "saps2": saps2,

        # Convenience top-level flags
        "news2_score": news2["total_news2"],
        "news2_risk_band": news2["risk_band"],
        "sofa_score": sofa["total_sofa"],
        "apache2_score": apache2["apache2_score"],
        "saps2_score": saps2["saps2_score"],
        "multi_organ_dysfunction": sofa["multi_organ_dysfunction"],
        "deterioration_event_id": None,  # filled below if event is triggered
    }

    result = db.vital_signs.insert_one(record)
    record["_id"] = result.inserted_id

    # ---- Auto-trigger deterioration event ----------------------------------
    should_trigger = (
        news2["total_news2"] >= 7
        or (news2.get("any_single_param_critical") and news2["total_news2"] >= 5)
        or sofa["multi_organ_dysfunction"]
    )

    if should_trigger and not det.has_active_event(db, patient_id):
        trigger_src = "NEWS2" if news2["total_news2"] >= 7 else (
            "SOFA-MODS" if sofa["multi_organ_dysfunction"] else "NEWS2-Single-Param"
        )
        event_id = det.create_deterioration_event(
            db,
            patient_id=patient_id,
            vital_sign_id=result.inserted_id,
            news2_result=news2,
            sofa_result=sofa,
            trigger_source=trigger_src,
        )
        db.vital_signs.update_one(
            {"_id": result.inserted_id},
            {"$set": {"deterioration_event_id": event_id}},
        )
        record["deterioration_event_id"] = event_id

    return result.inserted_id, record


def get_latest_vitals(db, patient_id: Any) -> Optional[Dict]:
    """Return the most recent vital sign document for a patient."""
    doc = (
        db.vital_signs.find({"patient_id": patient_id})
        .sort("recorded_datetime", -1)
        .limit(1)
    )
    docs = list(doc)
    if not docs:
        return None
    d = docs[0]
    d["_id"] = str(d["_id"])
    return d


def get_trends(db, patient_id: Any, frequency: str = "hourly") -> List[Dict]:
    match_stage = {"$match": {"patient_id": patient_id}}

    if frequency == "hourly":
        group_id: Any = {
            "year":  {"$year":  "$recorded_datetime"},
            "month": {"$month": "$recorded_datetime"},
            "day":   {"$dayOfMonth": "$recorded_datetime"},
            "hour":  {"$hour":  "$recorded_datetime"},
        }
    elif frequency == "4hourly":
        group_id = {
            "$dateTrunc": {
                "date": "$recorded_datetime",
                "unit": "hour",
                "binSize": 4,
            }
        }
    else:
        raise ValueError("Invalid frequency: choose 'hourly' or '4hourly'")

    pipeline = [
        match_stage,
        {
            "$group": {
                "_id": group_id,
                "avg_hr":       {"$avg": "$heart_rate"},
                "avg_sys_bp":   {"$avg": "$systolic_bp"},
                "avg_dia_bp":   {"$avg": "$diastolic_bp"},
                "avg_temp":     {"$avg": "$temperature"},
                "avg_spo2":     {"$avg": "$spo2"},
                "avg_rr":       {"$avg": "$respiratory_rate"},
                "max_news2":    {"$max": "$news2_score"},
                "max_sofa":     {"$max": "$sofa_score"},
                "count":        {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    return list(db.vital_signs.aggregate(pipeline))


def create_indexes(db):
    db.vital_signs.create_index(
        [("patient_id", 1), ("recorded_datetime", -1)]
    )
    db.vital_signs.create_index(
        [("patient_id", 1), ("news2_score", -1)]
    )
    db.vital_signs.create_index(
        [("patient_id", 1), ("multi_organ_dysfunction", 1)]
    )


def predict_trend(db, patient_id: Any) -> Dict[str, Any]:
    """
    Calculate trajectory based on NEWS2 scores over the last 12 hours.
    Returns early prediction of imminent deterioration if slope is steep.
    """
    pipeline = [
        {"$match": {
            "patient_id": patient_id, 
            "recorded_datetime": {"$gte": _now_utc().replace(hour=_now_utc().hour - min(12, _now_utc().hour)) if _now_utc().hour >= 12 else _now_utc()} # Simplified time math: just get recent docs 
        }},
        {"$sort": {"recorded_datetime": 1}},
        {"$limit": 20}
    ]
    
    # Actually let's use a simpler safe query
    import datetime as dt
    cutoff = _now_utc() - dt.timedelta(hours=12)
    docs = list(db.vital_signs.find({
        "patient_id": patient_id,
        "recorded_datetime": {"$gte": cutoff}
    }).sort("recorded_datetime", 1))

    if len(docs) < 3:
        return {"trajectory": "Insufficient Data", "risk": "Unknown", "slope": 0, "slope_meaning": "Need at least 3 readings"}

    scores = [d["news2_score"] for d in docs]
    
    # Calculate simple linear regression slope over index
    n = len(scores)
    x_mean = (n - 1) / 2
    y_mean = sum(scores) / n
    numerator = sum((i - x_mean) * (scores[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    
    slope = numerator / denominator if denominator != 0 else 0
    
    # Prediction logic
    risk = "Low"
    trajectory = "Stable"
    
    if slope > 0.5:
        trajectory = "Rapidly Worsening"
        risk = "High"
    elif slope > 0.15:
        trajectory = "Worsening"
        risk = "Medium"
    elif slope < -0.2:
        trajectory = "Improving"
        
    last_score = scores[-1]
    predicted_next_score = round(last_score + slope, 1)

    return {
        "trajectory": trajectory,
        "risk": risk,
        "slope": round(slope, 3),
        "last_score": last_score,
        "predicted_next_score": predicted_next_score,
        "hours_analyzed": 12,
        "datapoints": n
    }