# Module 25 ICU API Documentation

This folder contains the FastAPI service for **Module 25: ICU Vital Signs Monitoring**.

- Service file: `routes.py`
- Schema models: `schemas.py`
- OpenAPI docs: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

## 1) Run the API

From the module root (`src/modules/icu-vital-signs`):

```bash
pip install -r requirements.txt
uvicorn api.routes:app --reload --port 8001
```

## 2) Environment Variables

The API reads MongoDB connection from:

- `MODULE25_MONGO_URI` (preferred)
- fallback: `MONGO_URI`
- fallback default: `mongodb://localhost:27017`

Example (`api/.env.example`):

```env
MONGO_URI="your_mongo_uri_here"
MODULE25_API_URL="http://localhost:8001"
```

## 3) Base Path

All endpoints are under:

```text
/api/icu-vitals
```

## 4) Endpoint Reference

### System

| Method | Path | Description |
|---|---|---|
| GET | `/api/icu-vitals/health` | Health check and DB ping |
| GET | `/api/icu-vitals/db-info/server-functions` | Returns JS server functions source |

### Patients

| Method | Path | Description |
|---|---|---|
| GET | `/api/icu-vitals/patients` | List admitted ICU patients |
| POST | `/api/icu-vitals/patients` | Admit a patient and assign monitoring device |

Request model for `POST /patients`: `PatientAdmit`

### Vitals

| Method | Path | Description |
|---|---|---|
| POST | `/api/icu-vitals/ingest` | Ingest telemetry vitals and compute scores |
| POST | `/api/icu-vitals/manual-entry` | Manual nurse vitals entry |
| PUT | `/api/icu-vitals/vitals/{vital_id}` | Partial update to a vitals record |
| DELETE | `/api/icu-vitals/vitals/{vital_id}` | Delete a vitals record |
| GET | `/api/icu-vitals/patients/{patient_id}/vitals` | List latest vitals for a patient |
| GET | `/api/icu-vitals/patients/{patient_id}/current` | Latest vitals snapshot |
| GET | `/api/icu-vitals/patients/{patient_id}/trends` | Aggregated trends (`hourly` or `4hourly`) |
| GET | `/api/icu-vitals/patients/{patient_id}/predictions` | Trend-based deterioration prediction |

Request models:

- `VitalSignIngest`
- `ManualEntryRequest`
- `VitalSignUpdate`

### Views

| Method | Path | Description |
|---|---|---|
| GET | `/api/icu-vitals/views/critical-patients` | Aggregated critical patients view |
| GET | `/api/icu-vitals/views/nurse-summary` | Aggregated nurse summary view |

### Alerts

| Method | Path | Description |
|---|---|---|
| POST | `/api/icu-vitals/patients/{patient_id}/thresholds` | Create/update threshold rule |
| GET | `/api/icu-vitals/alerts/active` | Active threshold alerts (optional patient filter) |
| PUT | `/api/icu-vitals/alerts/{alert_id}/acknowledge` | Acknowledge alert |
| POST | `/api/icu-vitals/alerts/{alert_id}/intervene` | Log intervention and optionally resolve |

Request models:

- `ThresholdRule`
- `AlertAcknowledge`
- `AlertIntervention`

### Deterioration

| Method | Path | Description |
|---|---|---|
| GET | `/api/icu-vitals/deterioration` | Active/escalated deterioration events |
| GET | `/api/icu-vitals/deterioration/{event_id}` | Event details |
| POST | `/api/icu-vitals/deterioration/{event_id}/escalate` | Escalate event |
| POST | `/api/icu-vitals/deterioration/{event_id}/resolve` | Resolve event |
| GET | `/api/icu-vitals/patients/{patient_id}/deterioration-history` | Patient deterioration timeline |

Request models:

- `DeteriorationEscalate`
- `DeteriorationResolve`

### Webhooks

| Method | Path | Description |
|---|---|---|
| POST | `/api/icu-vitals/webhooks/drug-alert` | Inbound webhook from high-risk drug module |
| POST | `/api/icu-vitals/webhooks/push-alert` | Outbound stub endpoint for downstream routing |

Request model for drug webhook: `DrugAlertWebhook`

## 5) Common Query Parameters

- `GET /patients/{patient_id}/vitals`: `limit` (default `50`, range `1..500`)
- `GET /patients/{patient_id}/trends`: `interval` (`hourly` or `4hourly`)
- `GET /alerts/active`: `patient_id` (optional)
- `GET /deterioration`: `patient_id` (optional)
- `GET /patients/{patient_id}/deterioration-history`: `limit` (default `50`, range `1..200`)

## 6) Sample Requests

### Health

```bash
curl -X GET "http://localhost:8001/api/icu-vitals/health"
```

### Admit Patient

```bash
curl -X POST "http://localhost:8001/api/icu-vitals/patients" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "P-1001",
    "first_name": "Ava",
    "last_name": "Sharma",
    "gender": "Female",
    "device_id": "DEV-500",
    "device_type": "Multi-parameter Monitor",
    "admission_status": "ICU",
    "acuity_level": 2
  }'
```

### Manual Vitals Entry

```bash
curl -X POST "http://localhost:8001/api/icu-vitals/manual-entry" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "P-1001",
    "systolic_bp": 118,
    "diastolic_bp": 76,
    "heart_rate": 88,
    "respiratory_rate": 18,
    "spo2": 97,
    "supplemental_oxygen": false,
    "respiratory_support": "None",
    "consciousness_level": "Alert",
    "temperature": 37.1,
    "pain_score": 2
  }'
```

## 7) Notes

- Schema and request validation details are defined in `schemas.py`.
- API startup applies indexes and schema validation in MongoDB.
- For the latest payload examples and response shapes, prefer `/docs` since it is generated from live code.
