from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any, List
from bson import ObjectId

def calculate_sofa_score(sys_bp: float, resp_rate: float) -> Dict[str, Any]:
    score = 0

    if sys_bp < 70:
        score += 3
    elif sys_bp < 100:
        score += 1

    if resp_rate >= 30:
        score += 3
    elif resp_rate >= 22:
        score += 2
    elif resp_rate >= 15:
        score += 1

    risk_level = "High" if score >= 3 else ("Medium" if score > 0 else "Low")

    return {
        "total_score": score,
        "risk_level": risk_level
    }

def calculate_ews(hr: int, sys_bp: float, resp_rate: int, temp: float, pain: int) -> Dict[str, Any]:
    score = 0

    if hr <= 40 or hr > 130:
        score += 3
    elif 41 <= hr <= 50 or 111 <= hr <= 130:
        score += 2
    elif 51 <= hr <= 60 or 101 <= hr <= 110:
        score += 1

    if sys_bp <= 70:
        score += 3
    elif sys_bp <= 80:
        score += 2
    elif sys_bp <= 100:
        score += 1

    if resp_rate <= 8 or resp_rate > 25:
        score += 3
    elif 9 <= resp_rate <= 11:
        score += 1
    elif 21 <= resp_rate <= 25:
        score += 2

    if temp < 35 or temp > 39:
        score += 2
    elif 35 <= temp < 36 or 38 <= temp <= 39:
        score += 1

    if pain >= 8:
        score += 1

    risk_level = "High" if score >= 6 else ("Medium" if score >= 3 else "Low")

    return {
        "total_ews": score,
        "risk_level": risk_level
    }

def insert_vital_sign(
    db,
    patient_id: int,
    sys_bp: float,
    dia_bp: float,
    temp: float,
    hr: int,
    resp_rate: int,
    pain: int,
    device_id: Optional[int] = None
) -> Tuple[ObjectId, Dict]:

    sofa = calculate_sofa_score(sys_bp, resp_rate)
    ews = calculate_ews(hr, sys_bp, resp_rate, temp, pain)

    record = {
        "patient_id": patient_id,
        "device_id": device_id,
        "recorded_datetime": datetime.utcnow().replace(tzinfo=timezone.utc),
        "systolic_bp": sys_bp,
        "diastolic_bp": dia_bp,
        "temperature": temp,
        "heart_rate": hr,
        "respiratory_rate": resp_rate,
        "pain_score": pain,
        "sofa_score": sofa,
        "ews_score": ews
    }

    result = db.vital_signs.insert_one(record)
    record["_id"] = result.inserted_id
    
    return result.inserted_id, record

def get_trends(db, patient_id: int, frequency: str = "hourly") -> List[Dict]:
    match_stage = {"$match": {"patient_id": patient_id}}

    if frequency == "hourly":
        group_id = {
            "year": {"$year": "$recorded_datetime"},
            "month": {"$month": "$recorded_datetime"},
            "day": {"$dayOfMonth": "$recorded_datetime"},
            "hour": {"$hour": "$recorded_datetime"}
        }
    elif frequency == "4hourly":
        group_id = {
            "$dateTrunc": {
                "date": "$recorded_datetime",
                "unit": "hour",
                "binSize": 4
            }
        }
    else:
        raise ValueError("Invalid frequency")

    pipeline = [
        match_stage,
        {
            "$group": {
                "_id": group_id,
                "avg_hr": {"$avg": "$heart_rate"},
                "avg_sys_bp": {"$avg": "$systolic_bp"},
                "avg_dia_bp": {"$avg": "$diastolic_bp"},
                "avg_temp": {"$avg": "$temperature"},
                "max_ews": {"$max": "$ews_score.total_ews"}
            }
        },
        {"$sort": {"_id": 1}}
    ]

    return list(db.vital_signs.aggregate(pipeline))

def remove_random_vitals(db, n: int = 70) -> int:
    pipeline = [
        {"$sample": {"size": n}},
        {"$project": {"_id": 1}}
    ]

    docs = list(db.vital_signs.aggregate(pipeline))
    ids = [doc["_id"] for doc in docs]

    if not ids:
        return 0

    result = db.vital_signs.delete_many({"_id": {"$in": ids}})
    return result.deleted_count

def create_indexes(db):
    db.vital_signs.create_index([("patient_id", 1), ("recorded_datetime", -1)])
    db.deterioration_alerts.create_index([("patient_id", 1), ("alert_datetime", -1)])