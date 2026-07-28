import streamlit as st

from ui_helpers import (
    api_get,
    get_active_candidate_id,
    page_header,
    render_metric_card,
    render_sidebar,
)

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
render_sidebar()
page_header("Dashboard", "Live platform metrics and system overview.", "📊")

active_id = get_active_candidate_id()

ok_c, candidates, err_c = api_get("/candidates/", timeout=5)
ok_j, jobs, err_j = api_get("/jobs/", timeout=5)

cand_count = len(candidates) if ok_c and isinstance(candidates, list) else "Error"
job_count = len(jobs) if ok_j and isinstance(jobs, list) else "Error"

col1, col2, col3, col4 = st.columns(4)
with col1:
    render_metric_card("Candidates", cand_count)
with col2:
    render_metric_card("Open Jobs", job_count)
with col3:
    render_metric_card("Active ID", active_id or "—")
with col4:
    api_status = "Online" if ok_c else "Offline"
    render_metric_card("API Status", api_status)

if not ok_c:
    st.error(f"Candidates API: {err_c}")
if not ok_j:
    st.error(f"Jobs API: {err_j}")

st.markdown('<div class="section-header">Recent Candidates</div>', unsafe_allow_html=True)

if ok_c and isinstance(candidates, list) and candidates:
    display_rows = [
        {
            "ID": c.get("id"),
            "Name": c.get("full_name"),
            "Email": c.get("email"),
            "Registered": c.get("created_at", "")[:10] if c.get("created_at") else "",
        }
        for c in candidates[:10]
        if isinstance(c, dict)
    ]
    st.dataframe(display_rows, use_container_width=True, hide_index=True)
else:
    st.info("No candidates registered yet.")

st.markdown('<div class="section-header">Latest Job Postings</div>', unsafe_allow_html=True)

if ok_j and isinstance(jobs, list) and jobs:
    job_rows = [
        {
            "ID": j.get("id"),
            "Title": j.get("title"),
            "Company": j.get("company"),
            "Type": j.get("job_type"),
            "Location": j.get("location"),
        }
        for j in jobs[:8]
        if isinstance(j, dict)
    ]
    st.dataframe(job_rows, use_container_width=True, hide_index=True)
else:
    st.info("No job postings found.")
