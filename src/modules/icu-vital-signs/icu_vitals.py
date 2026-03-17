import streamlit as st
from pymongo import MongoClient
from database import patients, vitals, alerts
import pandas as pd

@st.cache_resource
def init_connection():
    return MongoClient(st.secrets["MONGO_URI"])

try:
    client = init_connection()
    db = client["icu_database"]
except Exception as e:
    st.error(f"Database connection failed: {e}")

st.set_page_config(
    page_title="ICU Vital Signs Monitoring",
    page_icon="🩺",
    layout="wide"
)

st.title("Module 25: ICU Vital Signs Monitoring Database")

st.write(
"""
This dashboard demonstrates a **real-time ICU monitoring database system**.

Features:
- ICU patient admissions
- Monitoring device assignment
- High-frequency vital sign recording
- Early Warning Score (EWS) monitoring
"""
)

tab1, tab2, tab3 = st.tabs([
    "Patient Admissions",
    "Vitals & Trends",
    "Active Alerts"
])

with tab1:
    st.header("Admit New ICU Patient")
    st.write("Register a new ICU patient and assign monitoring device.")

    with st.form("admission_form"):
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Patient Demographics")
            p_id = st.text_input("Patient ID", placeholder="P-1001")
            f_name = st.text_input("First Name")
            l_name = st.text_input("Last Name")
            gender = st.selectbox("Gender", ["Male", "Female", "Other"])
            dob = st.date_input("Date of Birth")

        with col2:
            st.subheader("Monitoring Device")
            d_id = st.text_input("Device ID", placeholder="DEV-500")
            d_type = st.selectbox(
                "Device Type",
                [
                    "Cardiac Monitor",
                    "Ventilator",
                    "Pulse Oximeter",
                    "Blood Pressure Monitor"
                ]
            )

        submitted = st.form_submit_button("Admit Patient & Assign Device")

    if submitted:
        if p_id and f_name and d_id:
            try:
                inserted_id, doc = patients.insert_patient_with_device(
                    db,
                    p_id,
                    f_name,
                    l_name,
                    gender,
                    str(dob),
                    d_id,
                    d_type
                )
                
                st.success(f"Patient {f_name} admitted successfully.")
                st.info("Database Execution (MongoDB Insert Query)")
                st.code(f"db.patients.insert_one({doc})", language="json")
                
            except ValueError as e:
                st.error(f"Error {e}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")
        else:
            st.error("Please fill required fields (Patient ID, First Name, Device ID).")

    st.divider()

    st.subheader("Currently Admitted ICU Patients")

    if st.button("Refresh Patient List"):
        all_patients = patients.get_all_patients(db)
        if all_patients:
            st.dataframe(all_patients, use_container_width=True)
        else:
            st.warning("No patients currently admitted.")

with tab2:
    st.header("Vitals & Trends")

    patients_list = patients.get_all_patients(db)

    if not patients_list:
        st.warning("Please admit a patient first in 'Patient Admissions'.")
    else:
        patient_map = {
            p["patient_id"]: f"{p['first_name']} {p['last_name']}"
            for p in patients_list
        }

        selected_patient = st.selectbox(
            "Select Patient",
            options=list(patient_map.keys()),
            format_func=lambda x: patient_map[x]
        )

        with st.form("vitals_form"):
            st.subheader("Record Vital Signs")

            col1, col2, col3 = st.columns(3)

            with col1:
                hr = st.number_input("Heart Rate", 0, 300, 80)
                sys_bp = st.number_input("Systolic BP", 0, 300, 120)

            with col2:
                dia_bp = st.number_input("Diastolic BP", 0, 200, 80)
                resp_rate = st.number_input("Respiratory Rate", 0, 60, 16)

            with col3:
                temp = st.number_input("Temperature (°C)", 30.0, 45.0, 37.0)
                pain = st.slider("Pain Score", 0, 10, 0)

            submit = st.form_submit_button("Record Vitals")

        if submit:
            try:
                inserted_id, doc = vitals.insert_vital_sign(
                    db,
                    selected_patient,
                    sys_bp,
                    dia_bp,
                    temp,
                    hr,
                    resp_rate,
                    pain
                )

                score = doc["ews_score"]["total_ews"]
                risk = doc["ews_score"]["risk_level"]

                if risk == "High":
                    st.error(f"🚨 EWS Score: {score} ({risk})")
                elif risk == "Medium":
                    st.warning(f"⚠️ EWS Score: {score} ({risk})")
                else:
                    st.success(f"✅ EWS Score: {score} ({risk})")

                st.code(f"db.vital_signs.insert_one({doc})", language="json")

                current_vitals = {
                    "heart_rate": hr,
                    "systolic_bp": sys_bp,
                    "diastolic_bp": dia_bp,
                    "temperature": temp,
                    "ews_score": score,
                }
                triggered = alerts.evaluate_alert(db, selected_patient, inserted_id, current_vitals)
                if triggered:
                    st.warning(f"⚠️ {len(triggered)} deterioration alert(s) triggered. Check the Active Alerts tab.")

            except Exception as e:
                st.error(f"Error saving vitals: {e}")

        st.divider()

        st.subheader("Patient Trends")

        interval = st.selectbox("Select Frequency", ["hourly", "4hourly"])

        if st.button("Generate Trends"):
            data = vitals.get_trends(db, selected_patient, interval)

            if data:
                df = pd.DataFrame(data)

                if interval == "hourly":
                    df["time"] = df["_id"].apply(lambda x: f"{x['hour']}:00")
                else:
                    df["time"] = df["_id"].astype(str)

                df.set_index("time", inplace=True)
                st.line_chart(df[["avg_hr", "avg_sys_bp", "max_ews"]])

                pipeline_display = f"""db.vital_signs.aggregate([
    {{"$match": {{"patient_id": "{selected_patient}"}}}},
    {{"$group": {{"_id": "time_bucket", "avg_hr": {{"$avg": "$heart_rate"}}, "max_ews": {{"$max": "$ews_score.total_ews"}}}}}}
])"""
                st.info("Backend Query Executed:")
                st.code(pipeline_display, language="javascript")

            else:
                st.warning("No vitals recorded for this patient yet.")

with tab3:
    st.header("Active Alerts & Interventions")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Set Threshold Rules")
        
        patients_list = patients.get_all_patients(db)
        
        if patients_list:
            patient_map = {p["patient_id"]: f"{p['first_name']} {p['last_name']}" for p in patients_list}
            
            selected_rule_patient = st.selectbox(
                "Select Patient",
                options=list(patient_map.keys()),
                format_func=lambda x: patient_map[x],
                key="threshold_patient"
            )

            with st.form("threshold_form"):
                param = st.selectbox("Parameter", ["heart_rate", "systolic_bp", "diastolic_bp", "temperature"])
                defaults = {
                    "heart_rate": (60.0, 100.0),
                    "systolic_bp": (90.0, 140.0),
                    "diastolic_bp": (60.0, 90.0),
                    "temperature": (36.0, 38.5),
                }
                default_min, default_max = defaults.get(param, (0.0, 100.0))
                min_v = st.number_input("Min Safe Value", value=default_min)
                max_v = st.number_input("Max Safe Value", value=default_max)
                submit_rule = st.form_submit_button("Save Rule")

            if submit_rule:
                alerts.set_threshold(db, selected_rule_patient, param, min_v, max_v)
                st.success(f"Rule saved for {param}.")
                
                query_display = f"""db.threshold_rules.update_one(
    {{"patient_id": "{selected_rule_patient}", "parameter": "{param}"}},
    {{"$set": {{"min_val": {min_v}, "max_val": {max_v}}}}},
    upsert=True
)"""
                st.info("Backend Query Executed (Upsert):")
                st.code(query_display, language="javascript")
        else:
            st.warning("Please admit a patient first.")

    with col2:
        st.subheader("Deterioration Alerts")

        if st.button("🔄 Refresh Alerts"):
            st.rerun()

        active_alerts = alerts.get_active_alerts(db)

        if not active_alerts:
            st.success("No active alerts. All patients are currently stable.")
        else:
            for alert in active_alerts:
                with st.expander(f"🚨 {alert['severity'].upper()} ALERT: {alert['alert_type']} | Patient: {alert['patient_id']}", expanded=True):
                    st.write(f"**Message:** {alert['message']}")
                    st.write(f"**Time:** {alert['alert_datetime']}")
                    
                    with st.form(f"resolve_form_{alert['_id']}"):
                        i_type = st.selectbox("Intervention Type", ["Administer Medication", "Adjust Ventilator", "Call Physician", "Other"])
                        notes = st.text_input("Clinical Notes")
                        resolve_btn = st.form_submit_button("Log Intervention & Resolve")
                        
                    if resolve_btn:
                        alerts.log_intervention(db, alert["_id"], i_type, notes)
                        st.success("Intervention logged and alert resolved.")
                        
                        push_query = f"""db.deterioration_alerts.update_one(
    {{"_id": ObjectId("{alert['_id']}")}},
    {{
        "$push": {{"interventions": {{"intervention_type": "{i_type}", "notes": "{notes}"}}}},
        "$set": {{"status": "Resolved"}}
    }}
)"""
                        st.info("Backend Query Executed ($push array update):")
                        st.code(push_query, language="javascript")
                        st.rerun()