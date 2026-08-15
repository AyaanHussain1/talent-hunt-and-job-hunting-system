import streamlit as st
import pandas as pd

from ui_helpers import api_get, api_post, page_header, parse_json_field, render_sidebar


st.set_page_config(page_title="Jobs", layout="wide")
render_sidebar()
page_header("Job Listings", "Create job postings and manage the roles used for candidate matching.")

with st.expander("Add or update a job", expanded=True):
    st.caption("Submitting the same title and company updates that posting instead of creating a duplicate.")
    with st.form("job_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        title = c1.text_input("Job title", placeholder="Backend Developer")
        company = c2.text_input("Company", placeholder="Example Ltd")
        c3, c4 = st.columns(2)
        job_type = c3.selectbox("Job type", ["Full-Time", "Remote", "Freelance", "Client", "Internal", "Startup"])
        location = c4.text_input("Location", placeholder="Karachi or Remote")
        skills_text = st.text_input("Required skills", placeholder="Python, FastAPI, SQL, Docker")
        description = st.text_area("Job description", placeholder="Describe the responsibilities and requirements.")
        save_job = st.form_submit_button("Save Job", type="primary")
    if save_job:
        skills = [skill.strip() for skill in skills_text.split(",") if skill.strip()]
        if not title.strip() or not company.strip() or not skills:
            st.warning("Enter a title, company, and at least one required skill.")
        else:
            ok, data, err = api_post("/jobs/", json_body={"title": title, "company": company, "job_type": job_type, "required_skills": skills, "description": description, "location": location})
            if ok:
                st.success(data.get("message", "Job saved."))
            else:
                st.error(err)

st.markdown("#### All job postings")
ok, jobs, err = api_get("/jobs/")
if not ok:
    st.error(err)
elif not isinstance(jobs, list) or not jobs:
    st.info("No job postings in the database.")
else:
    search = st.text_input("Filter by title, company, location, or skill", placeholder="Python or Remote")
    query = search.strip().lower()
    rows = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        skills = parse_json_field(job.get("required_skills")) or []
        searchable = " ".join([str(job.get(key, "")) for key in ("title", "company", "location", "job_type")] + (skills if isinstance(skills, list) else []))
        if query and query not in searchable.lower():
            continue
        rows.append({"ID": job.get("id"), "Title": job.get("title"), "Company": job.get("company"), "Type": job.get("job_type"), "Location": job.get("location") or "Not specified", "Required Skills": ", ".join(skills) if isinstance(skills, list) else str(skills)})
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No jobs match your filter.")
