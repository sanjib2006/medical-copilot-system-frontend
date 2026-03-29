"""
icu_vitals.py – Module 25: ICU Vital Signs Monitoring Dashboard
Medical Copilot System | Streamlit Frontend

Tabs:
  1. Patient Admissions
  2. Vitals & Trends          (NEWS2, SOFA, APACHE II)
  3. Active Alerts
  4. ICU Deterioration Events
"""

import streamlit as st
from pymongo import MongoClient
from database import patients, vitals, alerts
from database import deterioration as det
import pandas as pd

# ── Connection ────────────────────────────────────────────────────────────────

@st.cache_resource
def init_connection():
    return MongoClient(st.secrets["MONGO_URI"])

try:
    client = init_connection()
    db = client["icu_database"]
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.stop()

# ── Page CONFIG ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="M25 · ICU Vital Signs",
    page_icon="🏥",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .risk-low    { background:#1a7a1a; color:#fff; padding:8px 16px; border-radius:8px; font-weight:700; }
  .risk-medium { background:#b87800; color:#fff; padding:8px 16px; border-radius:8px; font-weight:700; }
  .risk-high   { background:#c0392b; color:#fff; padding:8px 16px; border-radius:8px; font-weight:700; }
  .risk-critical { background:#6c0e0e; color:#fff; padding:8px 16px; border-radius:8px; font-weight:700; animation: blinker 1s linear infinite; }
  @keyframes blinker { 50% { opacity:0.4; } }
  .score-table td { padding: 4px 12px; }
  .organ-ok  { color:#27ae60; font-weight:600; }
  .organ-bad { color:#e74c3c; font-weight:600; }
</style>
""", unsafe_allow_html=True)

st.title("🏥 Module 25 · ICU Vital Signs Monitoring")
st.caption("Real-time ICU Monitoring | NEWS2 · SOFA · APACHE II | Deterioration Tracking")

# ── Helper: risk banner ───────────────────────────────────────────────────────

def news2_banner(score: int, band: str, action: str, freq: str):
    if band == "High":
        cls, icon = "risk-critical", "🚨"
    elif band == "Medium":
        cls, icon = "risk-high", "🔴"
    elif band in ("Low-Medium",):
        cls, icon = "risk-medium", "⚠️"
    else:
        cls, icon = "risk-low", "✅"

    st.markdown(
        f'<div class="{cls}">{icon} NEWS2 Score: <b>{score}</b> — {band} Risk<br>'
        f'<small>Action: {action} | Frequency: {freq}</small></div>',
        unsafe_allow_html=True,
    )
    st.write("")

def severity_badge(sev: str) -> str:
    m = {
        "yellow":    "🟡 Yellow",
        "amber":     "🟠 Amber",
        "red":       "🔴 Red",
        "code_blue": "🔵 CODE BLUE",
        "Yellow":    "🟡 Yellow",
        "Amber":     "🟠 Amber",
        "Red":       "🔴 Red",
    }
    return m.get(sev, sev)

# ── TABS ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "🛏 Patient Admissions",
    "📊 Vitals & Trends",
    "🚨 Active Alerts",
    "📉 ICU Deterioration",
])

# =============================================================================
# TAB 1 – Patient Admissions
# =============================================================================
with tab1:
    st.header("Admit New ICU Patient")

    with st.form("admission_form"):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader("Demographics")
            p_id   = st.text_input("Patient ID *", placeholder="P-1001")
            mrn    = st.text_input("MRN (Medical Record No.)", placeholder="MRN-2025-001")
            f_name = st.text_input("First Name *")
            l_name = st.text_input("Last Name")
            gender = st.selectbox("Gender", ["Male", "Female", "Other"])
            dob    = st.date_input("Date of Birth")

        with col2:
            st.subheader("Admission Details")
            adm_status  = st.selectbox("Admission Status", ["ICU", "HDU", "Step-down", "Step-up"])
            acuity      = st.slider("Acuity Level", 1, 4, 2,
                                    help="1=Low, 4=Immediate life threat")
            diagnosis   = st.text_input("Admitting Diagnosis", placeholder="e.g. Septic shock")

        with col3:
            st.subheader("Monitoring Device")
            d_id   = st.text_input("Device ID *", placeholder="DEV-500")
            d_type = st.selectbox("Device Type", [
                "Cardiac Monitor", "Ventilator", "Pulse Oximeter",
                "Blood Pressure Monitor", "Multi-parameter Monitor",
            ])

        submitted = st.form_submit_button("✅ Admit Patient & Assign Device")

    if submitted:
        if p_id and f_name and d_id:
            try:
                inserted_id, doc = patients.insert_patient_with_device(
                    db, p_id, f_name, l_name, gender, str(dob),
                    d_id, d_type,
                    mrn=mrn or None,
                    admission_status=adm_status,
                    acuity_level=acuity,
                    admitting_diagnosis=diagnosis,
                )
                st.success(f"✅ Patient **{f_name} {l_name}** admitted to **{adm_status}** (Acuity {acuity}).")
                st.info("MongoDB document inserted:")
                st.json({k: str(v) if not isinstance(v, (str, int, float, bool, dict, list, type(None))) else v
                         for k, v in doc.items()})
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Unexpected error: {e}")
        else:
            st.error("Patient ID, First Name and Device ID are required.")

    st.divider()
    st.subheader("Currently Admitted ICU Patients")
    if st.button("🔄 Refresh List"):
        all_p = patients.get_all_patients(db)
        if all_p:
            df = pd.DataFrame(all_p)
            display_cols = [c for c in ["patient_id","mrn","first_name","last_name",
                              "admission_status","acuity_level","admitting_diagnosis",
                              "admission_datetime"] if c in df.columns]
            st.dataframe(df[display_cols], use_container_width=True)
        else:
            st.warning("No active patients.")

# =============================================================================
# TAB 2 – Vitals & Trends
# =============================================================================
with tab2:
    st.header("Record Vital Signs")

    patients_list = patients.get_all_patients(db)
    if not patients_list:
        st.warning("Admit a patient first (Tab 1).")
    else:
        patient_map = {p["patient_id"]: f"{p['first_name']} {p['last_name']}" for p in patients_list}
        sel_pid = st.selectbox("Select Patient", list(patient_map.keys()),
                               format_func=lambda x: patient_map[x])

        with st.form("vitals_form"):
            st.subheader("Haemodynamic")
            c1, c2, c3 = st.columns(3)
            with c1:
                hr      = st.number_input("Heart Rate (bpm)",   20, 300, 80)
                sys_bp  = st.number_input("Systolic BP (mmHg)", 40, 300, 120)
                dia_bp  = st.number_input("Diastolic BP (mmHg)",20, 200, 80)
            with c2:
                temp    = st.number_input("Temperature (°C)", 28.0, 45.0, 37.0, step=0.1)
                resp    = st.number_input("Respiratory Rate (breaths/min)", 1, 80, 16)
                pain    = st.slider("Pain Score (0–10)", 0, 10, 0)
            with c3:
                spo2    = st.number_input("SpO₂ (%)", 50.0, 100.0, 98.0, step=0.5)
                supp_o2 = st.checkbox("Supplemental Oxygen")
                resp_support = st.selectbox("Respiratory Support",
                    ["None", "Low-flow O2", "High-flow O2 (HFNC)", "Non-invasive (CPAP/BiPAP)", "Ventilated"])

            st.subheader("Neurological & Renal")
            c4, c5 = st.columns(2)
            with c4:
                acvpu   = st.selectbox("Consciousness (ACVPU)",
                    ["Alert", "Confusion", "Voice", "Pain", "Unresponsive"])
            with c5:
                urine   = st.number_input("Urine Output (ml/hr) — leave 0 if unmeasured",
                                          0.0, 999.0, 50.0, step=5.0)
                urine_val = urine if urine > 0 else None

            submit_v = st.form_submit_button("💉 Record Vitals & Score")

        if submit_v:
            try:
                v_id, doc = vitals.insert_vital_sign(
                    db,
                    patient_id=sel_pid,
                    systolic_bp=sys_bp, diastolic_bp=dia_bp, heart_rate=hr,
                    respiratory_rate=resp, spo2=spo2,
                    supplemental_oxygen=supp_o2, respiratory_support=resp_support,
                    consciousness_level=acvpu, temperature=temp,
                    urine_output_ml_hr=urine_val, pain_score=pain,
                )

                n2  = doc["news2"]
                sf  = doc["sofa"]
                ap2 = doc["apache2"]

                # ── NEWS2 banner
                news2_banner(
                    n2["total_news2"], n2["risk_band"],
                    n2["escalation_action"], n2["monitoring_frequency"]
                )

                # ── Score columns
                col_n, col_s, col_a = st.columns(3)

                with col_n:
                    st.metric("NEWS2 Score", n2["total_news2"])
                    st.write("**Component Breakdown**")
                    comp_df = pd.DataFrame(
                        [{"Parameter": k.replace("_"," ").title(), "Score": v}
                         for k, v in n2["components"].items()]
                    )
                    st.dataframe(comp_df, use_container_width=True, hide_index=True)

                with col_s:
                    st.metric("SOFA Score", sf["total_sofa"],
                              delta=f"Mortality est. {sf['estimated_mortality']}",
                              delta_color="off")
                    st.write("**Organ Scores**")
                    organ_df = pd.DataFrame(
                        [{"Organ": k.title(), "Score": v,
                          "Status": "⚠️ Dysfunctional" if v >= 2 else "✅ Normal"}
                         for k, v in sf["organ_scores"].items()]
                    )
                    st.dataframe(organ_df, use_container_width=True, hide_index=True)
                    if sf["multi_organ_dysfunction"]:
                        st.error("⚠️ **Multi-Organ Dysfunction Syndrome (MODS) detected**")

                with col_a:
                    st.metric("APACHE II Score", ap2["apache2_score"],
                              delta=f"Mortality est. {ap2['estimated_hospital_mortality_pct']}%",
                              delta_color="off")
                    st.caption(ap2["note"])

                # ── Threshold alert evaluation
                current_vitals_map = {
                    "heart_rate": hr, "systolic_bp": sys_bp, "diastolic_bp": dia_bp,
                    "temperature": temp, "spo2": spo2,
                    "respiratory_rate": resp, "urine_output_ml_hr": urine_val,
                    "news2_score": n2["total_news2"],
                }
                triggered = alerts.evaluate_alert(
                    db, sel_pid, v_id, current_vitals_map,
                    news2_score=n2["total_news2"]
                )
                if triggered:
                    st.warning(f"⚠️ {len(triggered)} threshold alert(s) triggered — check **Active Alerts** tab.")

                # ── Deterioration event notification
                if doc.get("deterioration_event_id"):
                    st.error(
                        f"🚨 **ICU Deterioration Event created** "
                        f"(NEWS2={n2['total_news2']}, SOFA={sf['total_sofa']}) — "
                        f"see **ICU Deterioration** tab."
                    )

                # ── Raw MongoDB query shown
                st.info("MongoDB insert executed:")
                st.code(
                    f"db.vital_signs.insert_one({{ patient_id: '{sel_pid}', "
                    f"news2_score: {n2['total_news2']}, sofa_score: {sf['total_sofa']}, "
                    f"spo2: {spo2}, consciousness_level: '{acvpu}', ... }})",
                    language="javascript"
                )

            except Exception as e:
                st.error(f"Error saving vitals: {e}")

        st.divider()
        st.subheader("📈 Trend Analysis")
        interval = st.selectbox("Aggregation Interval", ["hourly", "4hourly"])

        if st.button("Generate Trend Chart"):
            data = vitals.get_trends(db, sel_pid, interval)
            if data:
                df = pd.DataFrame(data)
                if interval == "hourly":
                    df["time"] = df["_id"].apply(
                        lambda x: f"{x.get('hour',0):02d}:00" if isinstance(x, dict) else str(x)
                    )
                else:
                    df["time"] = df["_id"].astype(str)
                df.set_index("time", inplace=True)

                chart_cols = [c for c in ["avg_hr","avg_sys_bp","avg_spo2","max_news2"] if c in df.columns]
                st.line_chart(df[chart_cols])
                st.caption("avg_hr=Heart Rate, avg_sys_bp=Systolic BP, avg_spo2=SpO₂, max_news2=Peak NEWS2")

                pipeline_shown = f"""db.vital_signs.aggregate([
  {{ "$match": {{ "patient_id": "{sel_pid}" }} }},
  {{ "$group": {{ "_id": "time_bucket",
      "avg_hr": {{ "$avg": "$heart_rate" }},
      "avg_spo2": {{ "$avg": "$spo2" }},
      "max_news2": {{ "$max": "$news2_score" }} }} }},
  {{ "$sort": {{ "_id": 1 }} }}
])"""
                st.code(pipeline_shown, language="javascript")
            else:
                st.warning("No vitals recorded yet.")

# =============================================================================
# TAB 3 – Active Alerts
# =============================================================================
with tab3:
    st.header("Active Threshold Alerts")

    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("Threshold Rules")
        p_list = patients.get_all_patients(db)
        if p_list:
            pm = {p["patient_id"]: f"{p['first_name']} {p['last_name']}" for p in p_list}
            rule_pid = st.selectbox("Patient", list(pm.keys()),
                                     format_func=lambda x: pm[x], key="rule_pid")

            with st.form("threshold_form"):
                param = st.selectbox("Parameter", [
                    "heart_rate", "systolic_bp", "diastolic_bp",
                    "temperature", "spo2", "respiratory_rate", "urine_output_ml_hr"
                ])
                defaults = alerts.DEFAULT_THRESHOLDS.get(param, {"min_val": 0.0, "max_val": 100.0})
                min_v = st.number_input("Min Safe Value", value=float(defaults.get("min_val") or 0))
                max_v = st.number_input("Max Safe Value", value=float(defaults.get("max_val") or 100))
                drug_adj = st.checkbox("Drug adjustment? (from M23)")
                drug_note = st.text_input("Drug name (if adjusted)", disabled=not drug_adj)
                save_rule = st.form_submit_button("💾 Save Rule")

            if save_rule:
                alerts.set_threshold(db, rule_pid, param, min_v, max_v,
                                     adjusted_for_drugs=drug_adj,
                                     adjustment_reason=drug_note)
                st.success(f"Rule saved for **{param}**.")
                st.code(
                    f"db.threshold_rules.update_one(\n"
                    f"  {{ patient_id: '{rule_pid}', parameter: '{param}' }},\n"
                    f"  {{ $set: {{ min_val: {min_v}, max_val: {max_v} }} }},\n"
                    f"  {{ upsert: true }}\n)",
                    language="javascript"
                )
        else:
            st.warning("Admit a patient first.")

    with col_right:
        st.subheader("Active Alerts Dashboard")
        if st.button("🔄 Refresh Alerts"):
            st.rerun()

        active = alerts.get_active_alerts(db)
        if not active:
            st.success("✅ No active alerts — all patients stable.")
        else:
            for alert in active:
                sev = alert.get("severity", "yellow")
                label = severity_badge(sev)
                with st.expander(
                    f"{label} | {alert['alert_type']} | Patient: {alert['patient_id']}",
                    expanded=(sev in ("red", "code_blue"))
                ):
                    st.write(f"**Message:** {alert['message']}")
                    st.write(f"**Time:** {alert.get('alert_datetime','')}")
                    if alert.get("news2_score") is not None:
                        st.write(f"**NEWS2 at alert:** {alert['news2_score']}")

                    with st.form(f"resolve_{alert['_id']}"):
                        i_type = st.selectbox("Intervention", [
                            "Fluid bolus", "Oxygen therapy", "Administer Medication",
                            "Adjust Ventilator", "Call Physician", "Activate RRT", "Other"
                        ])
                        notes = st.text_input("Clinical Notes")
                        resolve_btn = st.form_submit_button("✅ Log & Resolve")

                    if resolve_btn:
                        alerts.log_intervention(db, alert["_id"], i_type, notes)
                        st.success("Intervention logged and alert resolved.")
                        st.rerun()

# =============================================================================
# TAB 4 – ICU Deterioration Events
# =============================================================================
with tab4:
    st.header("📉 ICU Deterioration Events")
    st.write(
        "Auto-triggered when **NEWS2 ≥ 7**, **ANY single parameter scores 3** (with NEWS2 ≥ 5), "
        "or **Multi-Organ Dysfunction Syndrome (SOFAS ≥ 6)** is detected."
    )

    if st.button("🔄 Refresh Events"):
        st.rerun()

    events = det.get_active_deterioration_events(db)

    if not events:
        st.success("✅ No active deterioration events.")
    else:
        st.error(f"🚨 **{len(events)} active ICU deterioration event(s)**")

    for ev in events:
        sev_label = severity_badge(ev.get("severity", "Amber"))
        status_icon = "🔴" if ev["status"] == "Active" else "🔵"

        with st.expander(
            f"{status_icon} {sev_label} | Patient: {ev['patient_id']} | "
            f"NEWS2={ev.get('news2_score','?')} | SOFA={ev.get('sofa_score','?')} | "
            f"{ev['status']}",
            expanded=True
        ):
            col_info, col_scores = st.columns(2)

            with col_info:
                st.write(f"**Triggered:** {ev.get('triggered_at','')}")
                st.write(f"**Source:** {ev.get('trigger_source','')}")
                st.write(f"**Status:** {ev['status']}")
                if ev.get("multi_organ_dysfunction"):
                    st.error("⚠️ **MULTI-ORGAN DYSFUNCTION SYNDROME**")

                esc_hist = ev.get("escalation_history", [])
                if esc_hist:
                    st.write("**Escalation History:**")
                    for e in esc_hist:
                        st.write(f"- {e.get('escalated_at','')} → **{e.get('escalated_to','')}**: {e.get('note','')}")

            with col_scores:
                # NEWS2 component display
                n2_comp = ev.get("news2_components", {})
                if n2_comp:
                    st.write("**NEWS2 Components:**")
                    comp_df = pd.DataFrame(
                        [{"Parameter": k.replace("_"," ").title(), "Score": v}
                         for k, v in n2_comp.items()]
                    )
                    st.dataframe(comp_df, use_container_width=True, hide_index=True)

                # SOFA organ display
                organ_sc = ev.get("sofa_organ_scores", {})
                if organ_sc:
                    st.write("**SOFA Organ Scores:**")
                    organ_df = pd.DataFrame(
                        [{"Organ": k.title(), "Score": v,
                          "Status": "⚠️" if v >= 2 else "✅"}
                         for k, v in organ_sc.items()]
                    )
                    st.dataframe(organ_df, use_container_width=True, hide_index=True)

            st.divider()
            col_esc, col_res = st.columns(2)

            with col_esc:
                with st.form(f"escalate_{ev['_id']}"):
                    st.subheader("Escalate")
                    escalate_to = st.selectbox("Escalate To", [
                        "Rapid Response Team (RRT)",
                        "ICU Consultant",
                        "Attending Physician",
                        "Cardiology",
                        "Code Blue Team",
                    ])
                    esc_note = st.text_area("Clinical Note", height=80)
                    esc_btn = st.form_submit_button("📡 Escalate Now")

                if esc_btn:
                    det.escalate_event(db, ev["_id"], escalate_to, esc_note)
                    st.warning(f"Escalated to **{escalate_to}**.")
                    st.code(
                        f"db.icu_deterioration_events.update_one(\n"
                        f"  {{ _id: ObjectId('{ev['_id']}') }},\n"
                        f"  {{ $push: {{ escalation_history: {{ escalated_to: '{escalate_to}' }} }},\n"
                        f"    $set: {{ status: 'Escalated' }} }}\n)",
                        language="javascript"
                    )
                    st.rerun()

            with col_res:
                with st.form(f"resolve_det_{ev['_id']}"):
                    st.subheader("Resolve Event")
                    outcome = st.selectbox("Outcome", [
                        "Stabilised on ward",
                        "Transferred to ICU",
                        "Transferred to HDU",
                        "Transferred to Theatre",
                        "Palliative Care",
                        "Deceased",
                        "False Alarm / Artefact",
                    ])
                    res_notes = st.text_area("Resolution Notes", height=80)
                    res_by = st.text_input("Resolved By (clinician name)")
                    res_btn = st.form_submit_button("✅ Resolve Event")

                if res_btn:
                    det.resolve_event(db, ev["_id"], outcome, res_by, res_notes)
                    st.success(f"Event resolved: **{outcome}**")
                    st.rerun()

    # ── History section
    st.divider()
    st.subheader("📋 Deterioration History (Per Patient)")
    p_list2 = patients.get_all_patients(db)
    if p_list2:
        pm2 = {p["patient_id"]: f"{p['first_name']} {p['last_name']}" for p in p_list2}
        hist_pid = st.selectbox("Select Patient", list(pm2.keys()),
                                 format_func=lambda x: pm2[x], key="hist_pid")
        if st.button("Load History"):
            history = det.get_deterioration_history(db, hist_pid)
            if history:
                hist_df = pd.DataFrame([{
                    "Date":         h.get("triggered_at",""),
                    "NEWS2":        h.get("news2_score",""),
                    "SOFA":         h.get("sofa_score",""),
                    "Severity":     h.get("severity",""),
                    "Trigger":      h.get("trigger_source",""),
                    "Status":       h.get("status",""),
                    "Escalated To": h.get("last_escalated_to","—"),
                    "Outcome":      h.get("resolution",{}).get("outcome","—") if h.get("resolution") else "—",
                } for h in history])
                st.dataframe(hist_df, use_container_width=True, hide_index=True)
            else:
                st.info("No deterioration events recorded for this patient.")