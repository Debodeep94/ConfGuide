import streamlit as st
import pandas as pd
import json
import os
import time
import gspread
from google.oauth2.service_account import Credentials
from prepare_data import load_and_prepare_data

# === CONFIG & SETUP ===
st.set_page_config(page_title="Radiology Annotation Portal", layout="wide")

# Custom UI Styling
st.markdown("""
    <style>
    /* Radio button container */
    .stRadio [role=radiogroup]{
        padding: 10px; 
        border-radius: 8px; 
        background-color: #4a4a4a; /* Dark Grey */
    }
    
    /* Submit Button styling */
    div.stButton > button:first-child { 
        background-color: #007bff; 
        color: white !important; 
        border-radius: 8px; 
        font-weight: bold;
        height: 3.5em;
        border: none;
    }
    
    /* Evaluation Card - Paired Row */
    .eval-card {
        padding: 15px;
        border: 1px solid #333;
        border-radius: 10px;
        background-color: #1e1e1e; /* Black/Dark Background */
        margin-bottom: 20px;
        color: white;
    }
    
    .pathology-label {
        font-size: 1.2rem;
        font-weight: bold;
        color: #4dabf7; /* Light Blue for visibility on black */
        margin-bottom: 8px;
    }
    
    .guidance-box {
        padding: 10px;
        background-color: #2b2b2b;
        border-left: 4px solid #007bff;
        border-radius: 4px;
        font-size: 0.95rem;
    }
    </style>
    """, unsafe_allow_html=True)

# === Google Sheets Engine ===
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
        
        # Handle dynamic columns (new pathologies)
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

# === MAIN TRIAL LOGIC ===
# 1. Load the 20 randomized tasks (10 Blind + 10 Guided)
all_data = load_and_prepare_data(st.session_state.username)
done_uids = get_done_uids(st.session_state.username)

# 2. Track local session progress to avoid cache lag
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
    
    st.divider()
    if remaining_data:
        st.info(f"Current Trial Mode: **{remaining_data[0]['mode']}**")
    
    if st.button("Log Out", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

# --- CONTENT AREA ---
if not remaining_data:
    st.balloons()
    st.success("🎉 You have completed all 20 studies (10 Blind & 10 Guided). Thank you!")
else:
    current_case = remaining_data[0]
    uid, mode = current_case["uid"], current_case["mode"]
    metadata, guidance_dict = current_case["metadata"], current_case["guidance"]

    # 1. Display Image
    filename = os.path.basename(metadata["image_path"])
    image_path = os.path.join("images", filename)
    
    if os.path.exists(image_path):
        st.image(image_path, use_container_width=True)
    else:
        st.error(f"⚠️ Image file not found: {filename}")

    st.markdown("---")

    # 2. Paired Evaluation Cards (Horizontal Row Layout)
    flagged = metadata.get("flagged_pathologies", [])
    selections = {}

    for pathology in flagged:
        with st.container():
            # Apply custom CSS card
            st.markdown(f'<div class="eval-card">', unsafe_allow_html=True)
            
            # Split Card into Guidance (Left) and Evaluation (Right)
            col_guide, col_radio = st.columns([2, 1])
            
            with col_guide:
                st.markdown(f'<div class="pathology-label">{pathology}</div>', unsafe_allow_html=True)
                if mode == "Guided" and pathology in guidance_dict:
                    item = guidance_dict[pathology]
                    st.markdown(f"""
                    <div class="guidance-box">
                        <p style="margin-bottom:5px; color:#a5d6a7;"><b>Evidence For Presence of {pathology}:</b> {item.get('reasons for presence', 'N/A')}</p>
                        <p style="margin:0; color:red;"><b>Evidence Against Presence of {pathology}:</b> {item.get('reasons against presence', 'N/A')}</p>
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

    # 3. Submit
    if st.button("Confirm Findings & Proceed ➔", use_container_width=True, type="primary"):
        with st.spinner("Uploading to research database..."):
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
            
            # Immediate local update to bypass GSheet fetch lag
            st.session_state.locally_finished.add(uid)
            st.session_state.start_time = time.time()
            st.rerun()

# Initialize timer
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()