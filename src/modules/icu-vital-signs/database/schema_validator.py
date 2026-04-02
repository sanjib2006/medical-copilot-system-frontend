"""
schema_validator.py – MongoDB Schema Validation
Module 25: ICU Vital Signs Monitoring
"""

def apply_schema_validators(db):
    try:
        # Create collections if they don't exist
        existing = db.list_collection_names()
        if "vital_signs" not in existing:
            db.create_collection("vital_signs")
        if "patients" not in existing:
            db.create_collection("patients")

        # Apply schema to vital_signs
        vital_signs_validator = {
            "$jsonSchema": {
                "bsonType": "object",
                "required": [
                    "patient_id", "recorded_datetime", "heart_rate",
                    "systolic_bp", "diastolic_bp", "spo2",
                    "respiratory_rate", "temperature"
                ],
                "properties": {
                    "patient_id": {"bsonType": ["string", "int", "objectId"] },
                    "recorded_datetime": {"bsonType": "date"},
                    "heart_rate": {"bsonType": ["int", "double", "decimal"]},
                    "systolic_bp": {"bsonType": ["int", "double", "decimal"]},
                    "diastolic_bp": {"bsonType": ["int", "double", "decimal"]},
                    "spo2": {"bsonType": ["int", "double", "decimal"]},
                    "respiratory_rate": {"bsonType": ["int", "double", "decimal"]},
                    "temperature": {"bsonType": ["int", "double", "decimal"]},
                    "news2_score": {"bsonType": ["int", "double", "decimal"]},
                    "sofa_score": {"bsonType": ["int", "double", "decimal"]}
                }
            }
        }
        db.command("collMod", "vital_signs", validator=vital_signs_validator, validationLevel="moderate")

        # Apply schema to patients
        patients_validator = {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["patient_id", "first_name", "admission_status"],
                "properties": {
                    "patient_id": {"bsonType": ["string", "int", "objectId"]},
                    "first_name": {"bsonType": "string"},
                    "admission_status": {"bsonType": "string"}
                }
            }
        }
        db.command("collMod", "patients", validator=patients_validator, validationLevel="moderate")

        print("Applied MongoDB Schema Validators.")
    except Exception as e:
        print(f"Failed to apply schema validators: {e}")
