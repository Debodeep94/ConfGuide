import streamlit as st

def show_instructions():
    st.title("🩺 Radiology AI-Assistance Human Trial")
    st.markdown("---")
    
    # Hero Section
    col_text, col_img = st.columns([2, 1])
    
    with col_text:
        st.subheader("📋 Study Protocol")
        st.write("""
        Welcome, and thank you for participating in this research. This study evaluates 
        how AI-generated clinical reasoning affects diagnostic decision-making in chest radiography.
        """)
        
        st.markdown("""
        **Trial Structure:**
        * **Total Cases:** 20 Studies.
        * **Format:** You will review 10 unique images, each presented twice.
        * **Conditions:** * **Blind:** Evaluating images based solely on your clinical judgment.
            * **Guided:** Evaluation supported by clinical 'Evidence For' and 'Against' findings.
        """)

    with col_img:
        st.info("""
        **⏱️ Time Tracking**
        The system records the time taken for each annotation. Please proceed at a 
        natural clinical pace.
        """)
        
    st.markdown("---")
    
    # Layout Explanation
    st.subheader("⌨️ Evaluation Interface")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.markdown("### 1. View")
        st.write("Examine the high-resolution X-ray image provided at the top of the page.")
        
    with c2:
        st.markdown("### 2. Analyze")
        st.write("In **Guided** mode, review the beige and silver insight boxes paired with each pathology.")
        
    with c3:
        st.markdown("### 3. Record")
        st.write("Select **Yes** or **No** for every flagged pathology and click submit to advance.")

    st.markdown("<br><br>", unsafe_allow_html=True)
    
    # The "Start" Button
    if st.button("🚀 Begin Clinical Evaluation", use_container_width=True, type="primary"):
        st.session_state.started = True
        st.rerun()