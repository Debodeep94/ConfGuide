import streamlit as st
import pandas as pd
import json
import os
import time
import gspread
from google.oauth2.service_account import Credentials

# === CONFIG & SETUP ===
st.set_page_config(page_title="Radiology Annotation Portal", layout="wide")

# Custom UI styling for better ergonomics
st.markdown("""
    <style>
    .stRadio [role=radiogroup]{padding: 8px; border-radius: 8px; background-color: #f8f9fa; border: 1px solid #e9ecef;}
    div.stButton > button:first-child { background-color: #007bff; color: white; border-radius: 8px; border: none; height: 3em; font-weight: bold;}
    .reportview-container .main .block-container{ padding-top: 1rem; }
    /* Make expanders more compact */
    .streamlit-expanderHeader { font-size: 0.9rem; font-weight: 600; }
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
    sh = connect_gsheet()
    ws = sh.worksheet(worksheet_name)
    headers = ws.row_values(1)
    if not headers:
        headers = list(row_dict.keys())
        ws.append_row(headers)
    
    new_keys = [k for k in row_dict.keys() if k not in headers]
    if new_keys:
        headers.extend(new_keys)
        ws.update_cells([gspread.cell.Cell(1, i+1, val) for i, val in enumerate(headers)])
    
    values = [str(row_dict.get(h, "")) for h in headers]
    ws.append_row(values)

@st.cache_data(ttl=1)
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

if "locally_finished" not in st.session_state:
    st.session_state.locally_finished = set()

combined_done = done_uids.union(st.session_state.locally_finished)
remaining_data = [d for d in all_data if d["uid"] not in combined_done]

# --- SIDEBAR ---
with st.sidebar:
    st.markdown(f"## 🩺 Case Workstation")
    st.markdown(f"**Dr. {st.session_state.username}**")
    st.divider()
    done_count, total_count = len(combined_done), len(all_data)
    percent = int((done_count / total_count) * 100) if total_count > 0 else 0
    st.progress(percent / 100)
    st.write(f"**Progress:** {done_count}/{total_count} ({percent}%)")
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

    # Main Layout
    col_left, col_right = st.columns([1.4, 1], gap="large")

    with col_left:
        # 1. Image View
        st.markdown(f"#### 🖼️ Case View: {uid}")
        filename = os.path.basename(metadata["image_path"])
        image_path = os.path.join("images", filename)
        if os.path.exists(image_path):
            st.image(image_path, use_container_width=True)
        else:
            st.error(f"Missing File: {filename}")

        # 2. Guidance below Image
        if mode == "Guided":
            st.markdown("---")
            st.markdown("### 🔍 AI Clinical Guidance")
            # Displaying in 2 columns to save more vertical space if list is long
            g_col1, g_col2 = st.columns(2)
            for i, item in enumerate(guidance_list):
                target_col = g_col1 if i % 2 == 0 else g_col2
                with target_col:
                    with st.expander(f"**{item['label']}**", expanded=True):
                        st.markdown(f"<small>**For:** {item.get('reasons for presence', 'N/A')}</small>", unsafe_allow_html=True)
                        st.markdown(f"<small>**Against:** {item.get('reasons against presence', 'N/A')}</small>", unsafe_allow_html=True)
        else:
            st.info("💡 **Blind Study**: Reasoning guidance is hidden for this case.")

    with col_right:
        # 3. Evaluation Form
        st.markdown(f"### 📋 Diagnosis ({mode})")
        st.write("Please evaluate the findings based on clinical observation.")
        
        flagged = metadata.get("flagged_pathologies", [])
        selections = {}
        
        # Form Container for visual grouping
        with st.container():
            for pathology in flagged:
                selections[pathology] = st.radio(
                    f"Presence of **{pathology}**?",
                    ["Yes", "No", "Unsure"],
                    key=f"{uid}_{pathology}",
                    horizontal=True
                )
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("Save & Next Case ➔", use_container_width=True, type="primary"):
            with st.spinner("Submitting..."):
                duration = round(time.time() - st.session_state.get("start_time", time.time()), 2)
                result_row = {
                    "uid": uid,
                    "annotator": st.session_state.username,
                    "mode": mode,
                    "duration_sec": duration,
                    **{f"pathology_{k}": v for k, v in selections.items()}
                }
                append_to_gsheet("Annotations", result_row)
                st.session_state.locally_finished.add(uid)
                st.session_state.start_time = time.time()
                st.rerun()

if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()