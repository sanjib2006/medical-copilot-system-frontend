from datetime import datetime
from typing import Any, Dict, List, Optional


def insert_patient_with_device(
    db,
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
) -> tuple:
    if db.patients.find_one({"patient_id": patient_id}):
        raise ValueError("Patient ID already exists.")

    record = {
        "patient_id": patient_id,
        "mrn": mrn or f"MRN-{patient_id}",   # Medical Record Number
        "first_name": first_name,
        "last_name": last_name,
        "gender": gender,
        "date_of_birth": dob,
        "admission_status": admission_status,   # ICU | Step-down | HDU | Step-up
        "acuity_level": acuity_level,           # 1=lowest, 4=highest acuity
        "admitting_diagnosis": admitting_diagnosis,
        "admission_datetime": datetime.utcnow(),
        "discharge_datetime": None,
        "monitoring_device": {
            "device_id": device_id,
            "device_type": device_type,
            "status": "Active",
            "assigned_at": datetime.utcnow(),
        },
    }

    result = db.patients.insert_one(record)
    return result.inserted_id, record


def get_all_patients(db) -> List[Dict]:
    return list(db.patients.find({"discharge_datetime": None}, {"_id": 0}))


def get_patient_by_id(db, patient_id: Any) -> Optional[Dict]:
    return db.patients.find_one({"patient_id": patient_id}, {"_id": 0})


def update_device_status(db, patient_id: Any, new_status: str) -> int:
    result = db.patients.update_one(
        {"patient_id": patient_id},
        {"$set": {"monitoring_device.status": new_status}},
    )
    return result.modified_count


def update_device_assignment(
    db, patient_id: Any, new_device_id: str, new_device_type: str
) -> int:
    result = db.patients.update_one(
        {"patient_id": patient_id},
        {
            "$set": {
                "monitoring_device": {
                    "device_id": new_device_id,
                    "device_type": new_device_type,
                    "status": "Active",
                    "assigned_at": datetime.utcnow(),
                }
            }
        },
    )
    return result.modified_count


def update_acuity(db, patient_id: Any, acuity_level: int) -> int:
    result = db.patients.update_one(
        {"patient_id": patient_id},
        {"$set": {"acuity_level": acuity_level}},
    )
    return result.modified_count


def update_admission_status(db, patient_id: Any, status: str) -> int:
    result = db.patients.update_one(
        {"patient_id": patient_id},
        {"$set": {"admission_status": status}},
    )
    return result.modified_count


def discharge_patient(db, patient_id: Any) -> int:
    result = db.patients.update_one(
        {"patient_id": patient_id},
        {
            "$set": {
                "discharge_datetime": datetime.utcnow(),
                "monitoring_device.status": "Removed",
            }
        },
    )
    return result.modified_count


def delete_patient(db, patient_id: Any) -> int:
    result = db.patients.delete_one({"patient_id": patient_id})
    return result.deleted_count