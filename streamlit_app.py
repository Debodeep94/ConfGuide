import streamlit as st
import pandas as pd
import json
import os
import time
import gspread
from google.oauth2.service_account import Credentials

# === CONFIG & SETUP ===
st.set_page_config(page_title="Radiology Annotation Portal", layout="wide")

# Custom CSS for a cleaner look
st.markdown("""
    <style>
    .stRadio [role=radiogroup]{padding: 10px; border-radius: 10px; background-color: #f0f2f6;}
    div.stButton > button:first-child { background-color: #007bff; color: white; border-radius: 8px;}
    </style>
    """, unsafe_allow_html=True)

# Google Sheets setup
SHEET_URL = st.secrets["gsheet"]["url"]

@st.cache_resource
def connect_gsheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    return client.open_by_url(SHEET_URL)

def append_to_gsheet(worksheet_name, row_dict):
    try:
        sh = connect_gsheet()
        ws = sh.worksheet(worksheet_name)
        
        # FIX: Dynamic Header Management
        headers = ws.row_values(1)
        if not headers:
            headers = list(row_dict.keys())
            ws.append_row(headers)
        
        new_keys = [k for k in row_dict.keys() if k not in headers]
        if new_keys:
            headers.extend(new_keys)
            # Efficiently update header row
            ws.update_cells([gspread.cell.Cell(1, i+1, val) for i, val in enumerate(headers)])
        
        values = [str(row_dict.get(h, "")) for h in headers]
        ws.append_row(values)
    except Exception as e:
        st.error(f"Error saving to Google Sheets: {e}")

@st.cache_data(ttl=2)
def get_done_uids(user):
    try:
        sh = connect_gsheet()
        ws = sh.worksheet("Annotations")
        df = pd.DataFrame(ws.get_all_records())
        if df.empty: return set()
        return set(df[df["annotator"] == user]["uid"].astype(str))
    except:
        return set()

@st.cache_data
def load_and_prepare_data():
    with open("human_trial.json", "r") as f:
        data = json.load(f)
    prepared_data = []
    mid = len(data) // 2
    for i, entry in enumerate(data):
        core_metadata = entry.get("data", entry.get("metadata", {}))
        mode = "Blind" if i < mid else "Guided"
        filename = os.path.basename(core_metadata.get("image_path", ""))
        uid = f"case_{i}_{filename}"
        prepared_data.append({
            "uid": uid, "mode": mode, "metadata": core_metadata,
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

# --- DECORATED SIDEBAR ---
with st.sidebar:
    st.markdown(f"## 🩺 Medical Workstation")
    st.markdown(f"**Practitioner:** Dr. {st.session_state.username}")
    st.divider()
    
    st.markdown("### 📊 Session Progress")
    done_count = len(done_uids)
    total_count = len(all_data)
    percent = int((done_count / total_count) * 100) if total_count > 0 else 0
    
    st.progress(percent / 100)
    st.write(f"**{percent}% Complete** ({done_count}/{total_count} cases)")
    
    st.divider()
    st.markdown("### 🛠️ Status")
    if remaining_data:
        curr_mode = remaining_data[0]["mode"]
        st.success(f"Current Phase: **{curr_mode}**")
        st.info("System: Ready for Input")
    else:
        st.balloons()
        st.success("All Tasks Finished")
    
    st.divider()
    if st.button("🚪 Log Out", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

# --- CONTENT AREA ---
if not remaining_data:
    st.success("🎉 All cases completed! Thank you.")
else:
    current_case = remaining_data[0]
    uid, mode = current_case["uid"], current_case["mode"]
    metadata, guidance_list = current_case["metadata"], current_case["guidance"]

    st.subheader(f"Evaluation Mode: {mode}")
    
    col_img, col_annot = st.columns([1.2, 1])

    with col_img:
        filename = os.path.basename(metadata["image_path"])
        image_path = os.path.join("images", filename)
        if os.path.exists(image_path):
            st.image(image_path, use_container_width=True, caption=f"Case ID: {uid}")
        else:
            st.error(f"⚠️ Image '{filename}' not found in /images folder.")

    with col_annot:
        if mode == "Guided":
            st.markdown("### 🔍 AI Clinical Guidance")
            for item in guidance_list:
                with st.expander(f"Pathology: {item['label']}", expanded=True):
                    st.markdown(f"**Reasons For:** \n{item.get('reasons for presence', 'N/A')}")
                    st.markdown(f"**Reasons Against:** \n{item.get('reasons against presence', 'N/A')}")
        else:
            st.info("💡 **Blind Evaluation**: Review the image and select findings without AI assistance.")

        st.markdown("---")
        st.markdown("### 📋 Diagnosis")
        
        flagged = metadata.get("flagged_pathologies", [])
        selections = {}
        for pathology in flagged:
            selections[pathology] = st.radio(
                f"**{pathology}**", ["Yes", "No", "Unsure"],
                key=f"{uid}_{pathology}", horizontal=True
            )

        st.markdown("##") 
        if st.button("Submit & Next Case ➔", use_container_width=True, type="primary"):
            duration = round(time.time() - st.session_state.get("start_time", time.time()), 2)
            result_row = {
                "uid": uid,
                "annotator": st.session_state.username,
                "mode": mode,
                "duration_sec": duration,
                **{f"pathology_{k}": v for k, v in selections.items()}
            }
            append_to_gsheet("Annotations", result_row)
            st.session_state.start_time = time.time()
            st.rerun()

if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()