import streamlit as st
import pandas as pd
import json
import os
import time
import gspread
from google.oauth2.service_account import Credentials

# === CONFIG & SETUP ===
st.set_page_config(page_title="Radiology Annotation Portal", layout="wide")

# Custom UI for paired Evaluation Cards
st.markdown("""
    <style>
    .stRadio [role=radiogroup]{padding: 5px; border-radius: 5px; background-color: black;}
    div.stButton > button:first-child { background-color: #007bff; color: black; border-radius: 8px; font-weight: bold;}
    
    /* Card for Paired Guidance + Annotation */
    .eval-card {
        padding: 20px;
        border: 1px solid #e1e4e8;
        border-radius: 10px;
        background-color: black;
        margin-bottom: 25px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .pathology-label {
        font-size: 1.2rem;
        font-weight: bold;
        color: #1a73e8;
        margin-bottom: 10px;
        border-bottom: 2px solid #f1f3f4;
        padding-bottom: 5px;
    }
    .guidance-box {
        margin-bottom: 15px;
        padding: 10px;
        background-color: black;
        border-radius: 5px;
    }
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
            "guidance": {res['label']: res for res in entry.get('clinical_guidance', {}).get('results', [])}
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
    st.markdown(f"## 🩺 Workstation")
    st.markdown(f"**Dr. {st.session_state.username}**")
    st.divider()
    done_count, total_count = len(combined_done), len(all_data)
    st.write(f"**Progress:** {done_count}/{total_count}")
    st.progress(done_count / total_count if total_count > 0 else 0)
    st.divider()
    if st.button("Log Out"):
        st.session_state.logged_in = False
        st.rerun()

# --- CONTENT AREA ---
if not remaining_data:
    st.success("🎉 All cases completed!")
else:
    current_case = remaining_data[0]
    uid, mode = current_case["uid"], current_case["mode"]
    metadata, guidance_dict = current_case["metadata"], current_case["guidance"]

    # 1. Image (Always Top)
    st.markdown(f"#### 🖼️ Case ID: {uid} | Mode: {mode}")
    filename = os.path.basename(metadata["image_path"])
    image_path = os.path.join("images", filename)
    if os.path.exists(image_path):
        st.image(image_path, use_container_width=True)
    else:
        st.error(f"Image not found: {filename}")

    st.markdown("---")

    # 2. Paired Evaluation Sections
    flagged = metadata.get("flagged_pathologies", [])
    selections = {}

    for pathology in flagged:
        # Create a visual card for each pathology
        with st.container():
            st.markdown(f'<div class="eval-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="pathology-label">{pathology}</div>', unsafe_allow_html=True)
            
            # Show guidance if in Guided mode and data exists
            if mode == "Guided" and pathology in guidance_dict:
                item = guidance_dict[pathology]
                st.markdown(f"""
                <div class="guidance-box">
                    <p style="margin-bottom:5px;"><b>Evidence For:</b> {item.get('reasons for presence', 'N/A')}</p>
                    <p style="margin:0;"><b>Evidence Against:</b> {item.get('reasons against presence', 'N/A')}</p>
                </div>
                """, unsafe_allow_html=True)
            
            # Show the radio buttons immediately after the guidance
            selections[pathology] = st.radio(
                f"Evaluation for {pathology}",
                ["Yes", "No"],
                key=f"{uid}_{pathology}",
                horizontal=True,
                label_visibility="collapsed" # Hiding label because the card title handles it
            )
            st.markdown('</div>', unsafe_allow_html=True)

    # 3. Submit Button
    if st.button("Submit & Proceed ➔", use_container_width=True, type="primary"):
        with st.spinner("Recording..."):
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