import streamlit as st

from ui_helpers import (
    api_get,
    get_active_candidate_id,
    inject_custom_css,
    init_session_state,
    render_metric_card,
    render_sidebar,
)

st.set_page_config(
    page_title="TalentAI — Home",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()
inject_custom_css()
render_sidebar()

st.markdown(
    """
    <div class="hero-banner">
        <div class="hero-badge">AI-Powered Hiring</div>
        <h1>⚡ TalentAI Platform</h1>
        <p>Discover top engineering talent with resume parsing, GitHub analysis,
        portfolio scoring, and intelligent job matching — all in one place.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

ok_c, candidates, _ = api_get("/candidates/", timeout=5)
ok_j, jobs, _ = api_get("/jobs/", timeout=5)

cand_count = len(candidates) if ok_c and isinstance(candidates, list) else "—"
job_count = len(jobs) if ok_j and isinstance(jobs, list) else "—"
active_id = get_active_candidate_id() or "None"

col1, col2, col3 = st.columns(3)
with col1:
    render_metric_card("Total Candidates", cand_count)
with col2:
    render_metric_card("Open Positions", job_count)
with col3:
    render_metric_card("Active Candidate", active_id)

st.markdown('<div class="section-header">Platform Modules</div>', unsafe_allow_html=True)

features = [
    ("📊", "Dashboard", "Real-time platform metrics and overview."),
    ("👥", "Candidates", "Register talent and inspect full profiles."),
    ("📄", "Resume & ATS", "Upload PDFs and get ATS optimization reports."),
    ("🐙", "GitHub", "Extract repos, languages, and dev activity."),
    ("📈", "Portfolio", "Score project quality and engineering readiness."),
    ("🎯", "Job Matching", "Vector + keyword fusion job recommendations."),
    ("💼", "Jobs", "Browse all open job postings."),
    ("🏢", "Employer", "Search by skill and rank candidates per role."),
]

row1 = st.columns(4)
row2 = st.columns(4)
for i, (icon, title, desc) in enumerate(features):
    col = row1[i] if i < 4 else row2[i - 4]
    with col:
        st.markdown(
            f"""
            <div class="feature-card">
                <div class="feature-icon">{icon}</div>
                <h3>{title}</h3>
                <p>{desc}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.divider()

if active_id != "None":
    st.success(f"Ready to go — active candidate **#{active_id}** is selected.")
else:
    st.info("Get started: open **Candidates** in the sidebar to register a profile, then select it above.")
