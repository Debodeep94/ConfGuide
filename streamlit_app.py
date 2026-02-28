import streamlit as st
import pandas as pd
import json
import os
import time
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
        
        # Ensure all values are strings for GSheets
        values = [str(row_dict.get(h, "")) for h in headers]
        ws.append_row(values)
    except Exception as e:
        st.error(f"Error saving to Google Sheets: {e}")

@st.cache_data(ttl=5)
def get_done_uids(user):
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
    # Load your JSON file
    with open("data.json", "r") as f:
        data = json.load(f)
    
    prepared_data = []
    # Simple split: first half Blind, second half Guided
    mid = len(data) // 2
    
    for i, entry in enumerate(data):
        # Accessing the 'data' key from your specific JSON snippet
        core_metadata = entry.get("data", entry.get("metadata", {}))
        mode = "Blind" if i < mid else "Guided"
        
        # Clean filename extraction
        original_path = core_metadata.get("image_path", "")
        filename = os.path.basename(original_path)
        uid = f"case_{i}_{filename}"
        
        prepared_data.append({
            "uid": uid,
            "mode": mode,
            "metadata": core_metadata,
            "guidance": entry.get('clinical_guidance', {}).get('results', [])
        })
    return prepared_data

# === AUTHENTICATION ===
USERS = st.secrets["credentials"]

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
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
    st.stop()

# === MAIN APP LOGIC ===
all_data = load_and_prepare_data()
done_uids = get_done_uids(st.session_state.username)
remaining_data = [d for d in all_data if d["uid"] not in done_uids]

# Sidebar Progress
st.sidebar.title(f"Dr. {st.session_state.username}")
done_count = len(done_uids)
total_count = len(all_data)
st.sidebar.progress(done_count / total_count if total_count > 0 else 0)
st.sidebar.write(f"Completed: {done_count} / {total_count}")

if not remaining_data:
    st.success("🎉 All cases completed! Thank you for your contribution.")
    if st.button("Log Out"):
        st.session_state.logged_in = False
        st.rerun()
else:
    current_case = remaining_data[0]
    uid = current_case["uid"]
    mode = current_case["mode"]
    metadata = current_case["metadata"]
    guidance_list = current_case["guidance"]

    st.subheader(f"Evaluation Mode: {mode}")
    
    col_img, col_annot = st.columns([1.2, 1])

    with col_img:
        # Robust Path Handling
        filename = os.path.basename(metadata["image_path"])
        # Attempt 1: images/filename | Attempt 2: filename | Attempt 3: absolute path
        possible_paths = [os.path.join("images", filename), filename, metadata["image_path"]]
        
        image_to_show = None
        for p in possible_paths:
            if os.path.exists(p):
                image_to_show = p
                break
        
        if image_to_show:
            st.image(image_to_show, use_container_width=True, caption=f"Case ID: {uid}")
        else:
            st.error(f"⚠️ Image not found. Please ensure '{filename}' is in the 'images/' folder.")

    with col_annot:
        # 1. Guided Logic
        if mode == "Guided":
            st.markdown("### 🔍 AI Clinical Guidance")
            for item in guidance_list:
                with st.expander(f"Pathology: {item['label']}", expanded=True):
                    st.write(f"**Reasons For:** {item.get('reasons for presence', 'N/A')}")
                    st.write(f"**Reasons Against:** {item.get('reasons against presence', 'N/A')}")
        else:
            st.info("💡 **Blind Evaluation**: Review the image and select pathologies based on clinical observation.")

        # 2. Annotation Form
        st.markdown("---")
        st.markdown("### 📋 Your Diagnosis")
        
        flagged = metadata.get("flagged_pathologies", [])
        selections = {}
        
        for pathology in flagged:
            selections[pathology] = st.selectbox(
                f"Status of {pathology}:",
                ["- Select -", "Present", "Absent", "Inconclusive"],
                key=f"{uid}_{pathology}"
            )

        notes = st.text_area("Observations/Notes", key=f"{uid}_notes")

        if st.button("Submit & Next Case"):
            # Validation: Ensure all pathologies are answered
            if any(v == "- Select -" for v in selections.values()):
                st.warning("Please provide a status for all flagged pathologies.")
            else:
                duration = round(time.time() - st.session_state.get("start_time", time.time()), 2)
                
                result_row = {
                    "uid": uid,
                    "annotator": st.session_state.username,
                    "mode": mode,
                    "duration_sec": duration,
                    "notes": notes,
                    **{f"pathology_{k}": v for k, v in selections.items()}
                }
                
                append_to_gsheet("Annotations", result_row)
                st.session_state.start_time = time.time() # Reset timer
                st.rerun()

# Initialize timer for the current case
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()