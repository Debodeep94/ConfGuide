import streamlit as st
import pandas as pd
import json
import os
import time
import gspread
from google.oauth2.service_account import Credentials
from prepare_data import load_and_prepare_data
from first_page import show_instructions

# 1. ALWAYS DO CONFIG FIRST
st.set_page_config(page_title="Radiology Annotation Portal", layout="wide")

# 2. GLOBAL CSS (Moves outside the IF block)
st.markdown("""
    <style>
    .stRadio [role=radiogroup]{padding: 10px; border-radius: 8px; background-color: #4a4a4a;}
    div.stButton > button:first-child { background-color: #007bff; color: white !important; border-radius: 8px; font-weight: bold; height: 3.5em; border: none;}
    .eval-card {padding: 15px; border: 1px solid #333; border-radius: 10px; background-color: #1e1e1e; margin-bottom: 20px; color: white;}
    .pathology-label {font-size: 1.2rem; font-weight: bold; color: #4dabf7; margin-bottom: 8px;}
    .guidance-box {padding: 10px; background-color: #2b2b2b; border-left: 4px solid #007bff; border-radius: 4px; font-size: 0.95rem;}
    </style>
    """, unsafe_allow_html=True)

# 3. GLOBAL FUNCTIONS (Moves outside the IF block)
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
    except Exception as e:
        st.error(f"GSheet Error: {e}")

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

# 4. AUTHENTICATION LOGIC
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

# 5. PAGE ROUTING (The Switch)
if "started" not in st.session_state:
    st.session_state.started = False

if not st.session_state.started:
    show_instructions()
    st.stop()

# 6. MAIN TRIAL LOGIC (Only runs if logged_in AND started)
all_data = load_and_prepare_data(st.session_state.username)
done_uids = get_done_uids(st.session_state.username)

if "locally_finished" not in st.session_state:
    st.session_state.locally_finished = set()

combined_done = done_uids.union(st.session_state.locally_finished)
remaining_data = [d for d in all_data if d["uid"] not in combined_done]

# --- SIDEBAR ---
with st.sidebar:
    st.markdown(f"## 🩺 Workstation")
    st.markdown(f"**Dr. {st.session_state.username}**")
    st.divider()
    done_count, total_count = len(combined_done), len(all_data)
    st.write(f"**Study Progress:** {done_count} / {total_count}")
    st.progress(done_count / total_count if total_count > 0 else 0)
    if st.button("Log Out", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.started = False
        st.rerun()

# --- CONTENT AREA ---
if not remaining_data:
    st.balloons()
    st.success("🎉 You have completed all studies. Thank you!")
else:
    current_case = remaining_data[0]
    uid, mode = current_case["uid"], current_case["mode"]
    metadata, guidance_dict = current_case["metadata"], current_case["guidance"]

    filename = os.path.basename(metadata["image_path"])
    image_path = os.path.join("images", filename)
    
    if os.path.exists(image_path):
        st.image(image_path, use_container_width=True)
    else:
        st.error(f"⚠️ Image not found: {filename}")

    st.markdown("---")
    
    flagged = metadata.get("flagged_pathologies", [])
    selections = {}

    for pathology in flagged:
        with st.container():
            st.markdown(f'<div class="eval-card">', unsafe_allow_html=True)
            col_guide, col_radio = st.columns([2, 1])
            with col_guide:
                st.markdown(f'<div class="pathology-label">{pathology}</div>', unsafe_allow_html=True)
                if mode == "Guided" and pathology in guidance_dict:
                    item = guidance_dict[pathology]
                    st.markdown(f"""
                    <div class="guidance-box">
                        <p style="margin-bottom:5px; color:beige;"><b>Evidence For:</b> {item.get('reasons for presence', 'N/A')}</p>
                        <p style="margin:0; color:#D6EAF8;"><b>Evidence Against:</b> {item.get('reasons against presence', 'N/A')}</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown('<div class="guidance-box"><i>Blind Mode: Clinical guidance suppressed.</i></div>', unsafe_allow_html=True)

            with col_radio:
                st.write("**Clinical Decision:**")
                selections[pathology] = st.radio(
                    f"Finding for {pathology}",
                    ["Yes", "No"],
                    key=f"{uid}_{pathology}",
                    horizontal=True,
                    label_visibility="collapsed"
                )
            st.markdown('</div>', unsafe_allow_html=True)

    if st.button("Confirm Findings & Proceed ➔", use_container_width=True, type="primary"):
        with st.spinner("Uploading..."):
            end_time = time.time()
            duration = round(end_time - st.session_state.get("start_time", end_time), 2)
            result_row = {
                "uid": uid,
                "image_file": filename,
                "annotator": st.session_state.username,
                "mode": mode,
                "duration_sec": duration,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                **{f"pathology_{k}": v for k, v in selections.items()}
            }
            append_to_gsheet("Annotations", result_row)
            st.session_state.locally_finished.add(uid)
            st.session_state.start_time = time.time()
            st.rerun()

if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()