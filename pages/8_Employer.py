import streamlit as st
import pandas as pd

from ui_helpers import (
    api_get,
    page_header,
    parse_json_field,
    render_sidebar,
)

st.set_page_config(page_title="Employer Portal", page_icon="🏢", layout="wide")
render_sidebar()
page_header("Employer Portal", "Search talent by skill and rank candidates per job.", "🏢")

tab_search, tab_rankings = st.tabs(["Skill Search", "Rankings by Job"])

with tab_search:
    st.markdown("#### Find candidates by skill keyword")
    skill_query = st.text_input(
        "Skill",
        placeholder="Python, React, Machine Learning…",
        label_visibility="collapsed",
    )

    if st.button("Search Talent", type="primary"):
        params = {"skill": skill_query.strip()} if skill_query.strip() else None
        ok, results, err = api_get("/employer/candidates", params=params)
        if ok and isinstance(results, list):
            if results:
                rows = []
                for r in results:
                    if not isinstance(r, dict):
                        continue
                    skills = parse_json_field(r.get("skills")) or []
                    rows.append(
                        {
                            "ID": r.get("id"),
                            "Name": r.get("full_name"),
                            "Email": r.get("email"),
                            "Location": r.get("location", "—"),
                            "Portfolio": round(float(r["portfolio_score"]), 1)
                            if r.get("portfolio_score") is not None
                            else "—",
                            "Skills": ", ".join(skills[:8]) if isinstance(skills, list) else str(skills or "—"),
                        }
                    )
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                st.caption(f"{len(rows)} candidate(s) found")
            else:
                st.warning("No candidates matched your query.")
        else:
            st.error(err)

with tab_rankings:
    st.markdown("#### Candidate rankings for a specific role")
    ok_j, jobs, err_j = api_get("/jobs/")
    if not ok_j:
        st.error(err_j)
    elif not isinstance(jobs, list) or not jobs:
        st.info("No jobs available.")
    else:
        job_map = {
            f"{j['title']} @ {j.get('company', '?')} (#{j['id']})": j["id"]
            for j in jobs
            if isinstance(j, dict) and "id" in j and "title" in j
        }
        selected = st.selectbox("Select job position", options=list(job_map.keys()))
        job_id = job_map[selected]

        if st.button("Load Rankings", type="primary"):
            ok, rankings, err = api_get(f"/employer/jobs/{job_id}/candidates")
            if ok and isinstance(rankings, list):
                if rankings:
                    rows = []
                    for r in rankings:
                        if not isinstance(r, dict):
                            continue
                        matched = parse_json_field(r.get("matched_skills")) or []
                        missing = parse_json_field(r.get("missing_skills")) or []
                        rows.append(
                            {
                                "Rank": len(rows) + 1,
                                "Name": r.get("full_name"),
                                "Email": r.get("email"),
                                "Match %": round(float(r.get("match_score", 0)), 1),
                                "Portfolio": round(float(r["portfolio_score"]), 1)
                                if r.get("portfolio_score") is not None
                                else "—",
                                "Matched": ", ".join(matched) if isinstance(matched, list) else "—",
                                "Gaps": ", ".join(missing) if isinstance(missing, list) else "—",
                            }
                        )
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                    if rows:
                        top = rows[0]
                        st.success(
                            f"Top candidate: **{top['Name']}** — "
                            f"{top['Match %']}% match, portfolio {top['Portfolio']}"
                        )
                else:
                    st.info("No candidates ranked for this job yet. Run job matching first.")
            else:
                st.error(err)
