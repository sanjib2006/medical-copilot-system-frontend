from datetime import datetime

def insert_patient_with_device(db, patient_id, first_name, last_name, gender, dob, device_id, device_type):
    if db.patients.find_one({"patient_id": patient_id}):
        raise ValueError("Patient ID already exists.")

    record = {
        "patient_id": patient_id,
        "first_name": first_name,
        "last_name": last_name,
        "gender": gender,
        "date_of_birth": dob,
        "admission_datetime": datetime.utcnow(),
        "monitoring_device": {
            "device_id": device_id,
            "device_type": device_type,
            "status": "Active"
        }
    }

    result = db.patients.insert_one(record)
    return result.inserted_id, record

def get_all_patients(db):
    return list(db.patients.find({}, {"_id": 0}))

def get_patient_by_id(db, patient_id):
    return db.patients.find_one({"patient_id": patient_id}, {"_id": 0})

def update_device_status(db, patient_id, new_status):
    result = db.patients.update_one(
        {"patient_id": patient_id},
        {"$set": {"monitoring_device.status": new_status}}
    )
    return result.modified_count

def update_device_assignment(db, patient_id, new_device_id, new_device_type):
    result = db.patients.update_one(
        {"patient_id": patient_id},
        {
            "$set": {
                "monitoring_device": {
                    "device_id": new_device_id,
                    "device_type": new_device_type,
                    "status": "Active"
                }
            }
        }
    )
    return result.modified_count

def discharge_patient(db, patient_id):
    result = db.patients.update_one(
        {"patient_id": patient_id},
        {
            "$set": {
                "discharge_datetime": datetime.utcnow(),
                "monitoring_device.status": "Removed"
            }
        }
    )
    return result.modified_count

def delete_patient(db, patient_id):
    result = db.patients.delete_one({"patient_id": patient_id})
    return result.deleted_count