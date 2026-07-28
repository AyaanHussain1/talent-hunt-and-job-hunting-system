import streamlit as st
import pandas as pd

from ui_helpers import api_get, page_header, parse_json_field, render_sidebar

st.set_page_config(page_title="Jobs", page_icon="💼", layout="wide")
render_sidebar()
page_header("Job Listings", "Browse all open positions on the platform.", "💼")

ok, jobs, err = api_get("/jobs/")
if not ok:
    st.error(err)
elif not isinstance(jobs, list) or not jobs:
    st.info("No open job postings in the database.")
else:
    st.metric("Total Open Positions", len(jobs))

    search = st.text_input("Filter by title, company, or location", placeholder="e.g. Python, Remote")
    filtered = jobs
    if search.strip():
        q = search.strip().lower()
        filtered = [
            j for j in jobs
            if isinstance(j, dict)
            and q in " ".join(
                str(j.get(k, "")) for k in ("title", "company", "location", "job_type")
            ).lower()
        ]

    rows = []
    for j in filtered:
        if not isinstance(j, dict):
            continue
        skills = parse_json_field(j.get("required_skills") or j.get("skills")) or []
        rows.append(
            {
                "ID": j.get("id"),
                "Title": j.get("title"),
                "Company": j.get("company"),
                "Type": j.get("job_type"),
                "Location": j.get("location"),
                "Skills": ", ".join(skills) if isinstance(skills, list) else str(skills or "—"),
            }
        )

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown('<div class="section-header">Job Cards</div>', unsafe_allow_html=True)
        cols = st.columns(min(len(rows), 3))
        for i, row in enumerate(rows[:6]):
            with cols[i % 3]:
                st.markdown(
                    f"""
                    <div class="feature-card">
                        <h3>{row['Title']}</h3>
                        <p><strong>{row['Company']}</strong> · {row['Type']} · {row['Location']}</p>
                        <p style="margin-top:0.5rem;font-size:0.8rem;">{row['Skills'][:120]}{'…' if len(row['Skills']) > 120 else ''}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    else:
        st.warning("No jobs match your search.")
