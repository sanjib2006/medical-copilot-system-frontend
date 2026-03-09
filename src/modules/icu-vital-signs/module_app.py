import streamlit as st
from pymongo import MongoClient

@st.cache_resource
def init_connection():
    return MongoClient(st.secrets["MONGO_URI"])

try:
    client = init_connection()
    db = client["icu_vital_signs"]

    st.title("Module 25: ICU Vital Signs Monitoring")
    st.success("Successfully connected to MongoDB Atlas! ")

except Exception as e:
    st.error(f"Failed to connect to the database: {e}")
