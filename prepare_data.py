import random
import hashlib
import json
import os
import streamlit as st

@st.cache_data
def load_and_prepare_data(username):
    with open("human_trial.json", "r") as f:
        samples = json.load(f)
    
    # We want 10 images, but 20 total tasks (10 Blind + 10 Guided)
    samples = samples[:10] 
    prepared_data = []
    
    for entry in samples:
        core_metadata = entry.get("data", entry.get("metadata", {}))
        filename = os.path.basename(core_metadata.get("image_path", ""))
        guidance_map = {res['label']: res for res in entry.get('clinical_guidance', {}).get('results', [])}
        
        # Add Blind version
        prepared_data.append({
            "uid": f"blind_{filename}", # CRITICAL: Mode in UID
            "mode": "Blind",
            "metadata": core_metadata,
            "guidance": guidance_map
        })
        # Add Guided version
        prepared_data.append({
            "uid": f"guided_{filename}", # CRITICAL: Mode in UID
            "mode": "Guided",
            "metadata": core_metadata,
            "guidance": guidance_map
        })
    
    # Randomize order unique to this doctor
    seed_value = int(hashlib.sha256(username.encode()).hexdigest(), 16) % (2**32)
    random.seed(seed_value)
    random.shuffle(prepared_data)
    
    return prepared_data