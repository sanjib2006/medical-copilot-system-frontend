import streamlit as st
from pymongo import MongoClient
from database import patients

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
    st.info("This section will record vital signs and compute Early Warning Scores.")
    st.write("Trends will be displayed here.")

with tab3:
    st.header("Active Alerts")
    st.info("This section will display ICU deterioration alerts and interventions.")
    st.write("Active alerts will be listed here.")
