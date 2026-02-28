import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import time
from typing import List
import gspread
from google.oauth2.service_account import Credentials

# === CONFIG & SETUP ===
st.set_page_config(page_title="Radiology Annotation Portal", layout="wide")

# Google Sheets setup
SHEET_URL = st.secrets["gsheet"]["url"]

@st.cache_resource
def connect_gsheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    client = gspread.authorize(creds)
    return client.open_by_url(SHEET_URL)

def append_to_gsheet(worksheet_name, row_dict):
    try:
        sh = connect_gsheet()
        ws = sh.worksheet(worksheet_name)
        headers = ws.row_values(1)
        if not headers:
            headers = list(row_dict.keys())
            ws.append_row(headers)
        
        values = [str(row_dict.get(h, "")) for h in headers]
        ws.append_row(values)
    except Exception as e:
        st.error(f"Error saving to Google Sheets: {e}")

@st.cache_data(ttl=5)
def get_done_uids(user):
    """Fetches already completed UIDs from GSheets to prevent duplicates."""
    try:
        sh = connect_gsheet()
        ws = sh.worksheet("Annotations")
        df = pd.DataFrame(ws.get_all_records())
        if df.empty: return set()
        return set(df[df["annotator"] == user]["uid"].astype(str))
    except:
        return set()

# === DATA LOADING ===
@st.cache_data
def load_and_prepare_data():
    # Replace with your actual JSON filename
    with open("human_trial.json", "r") as f:
        data = json.load(f)
    
    prepared_data = []
    mid = len(data) // 2
    
    for i, entry in enumerate(data):
        # Assign mode: First half Blind, Second half Guided (or randomize)
        mode = "Blind" if i < mid else "Guided"
        
        # Create a unique ID for tracking
        img_name = entry['metadata']['image_path'].split('/')[-1]
        uid = f"{i}_{img_name}"
        
        prepared_data.append({
            "uid": uid,
            "mode": mode,
            "metadata": entry['metadata'],
            "guidance": entry.get('clinical_guidance', {}).get('results', [])
        })
    return prepared_data

# === AUTHENTICATION ===
USERS = st.secrets["credentials"]

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

def login():
    st.title("🔐 Radiology Portal Login")
    user = st.text_input("Username")
    pw = st.text_input("Password", type="password")
    if st.button("Login"):
        if user in USERS and USERS[user] == pw:
            st.session_state.logged_in = True
            st.session_state.username = user
            st.rerun()
        else:
            st.error("Invalid credentials")

if not st.session_state.logged_in:
    login()
    st.stop()

# === MAIN APP LOGIC ===
all_data = load_and_prepare_data()
done_uids = get_done_uids(st.session_state.username)
remaining_data = [d for d in all_data if d["uid"] not in done_uids]

# Progress Sidebar
st.sidebar.title(f"Welcome, Dr. {st.session_state.username}")
progress_val = len(done_uids) / len(all_data)
st.sidebar.progress(progress_val)
st.sidebar.write(f"Completed: {len(done_uids)} / {len(all_data)}")

if not remaining_data:
    st.success("🎉 You have completed all assigned cases!")
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
else:
    current_case = remaining_data[0]
    uid = current_case["uid"]
    mode = current_case["mode"]
    metadata = current_case["metadata"]
    guidance_list = current_case["guidance"]

    st.header(f"Case Study: {uid} ({mode} Mode)")
    
    # --- Layout: Image on Left, Logic on Right ---
    col_img, col_info = st.columns([1, 1])

    with col_img:
        st.subheader("X-Ray Image")
        img_path = metadata["image_path"]
        if os.path.exists(img_path):
            st.image(img_path, use_container_width=True)
        else:
            st.error(f"Image File Not Found: {img_path}")

    with col_info:
        # 1. Show AI guidance ONLY in Guided Mode
        if mode == "Guided":
            st.subheader("💡 Clinical Guidance (AI)")
            for item in guidance_list:
                with st.expander(f"Analysis for: {item['label']}", expanded=False):
                    st.markdown("**Reasons for presence:**")
                    st.info(item.get('reasons for presence', 'N/A'))
                    st.markdown("**Reasons against presence:**")
                    st.warning(item.get('reasons against presence', 'N/A'))
        else:
            st.info("ℹ️ **Blind Study Mode**: Please evaluate the image based on the listed pathologies below.")

        # 2. Annotation Form
        st.subheader("📋 Your Evaluation")
        st.write("Indicate presence for the flagged pathologies:")
        
        doctor_selections = {}
        flagged = metadata["flagged_pathologies"]
        
        # Create a dynamic form based on flagged pathologies in JSON
        for pathology in flagged:
            doctor_selections[pathology] = st.radio(
                f"Is **{pathology}** present?",
                ["Yes", "No", "Unsure"],
                key=f"{uid}_{pathology}",
                horizontal=True
            )

        comments = st.text_area("Additional Clinical Notes (Optional)", key=f"{uid}_notes")

        if st.button("💾 Save and Next"):
            start_time = st.session_state.get("start_time", time.time())
            duration = round(time.time() - start_time, 2)
            
            # Prepare result row
            result = {
                "uid": uid,
                "annotator": st.session_state.username,
                "mode": mode,
                "image_path": img_path,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_seconds": duration,
                "comments": comments,
                **{f"pathology_{k}": v for k, v in doctor_selections.items()}
            }
            
            append_to_gsheet("Annotations", result)
            st.session_state.start_time = time.time() # Reset timer
            st.success("Annotation Saved!")
            time.sleep(1)
            st.rerun()

# Set start time for the first load
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()