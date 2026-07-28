import streamlit as st

from ui_helpers import (
    api_get,
    api_post,
    get_active_candidate_id,
    page_header,
    parse_json_field,
    render_sidebar,
    render_skill_tags,
)

st.set_page_config(page_title="Candidates", page_icon="👥", layout="wide")
render_sidebar()
page_header("Candidate Management", "Register new talent and explore unified profiles.", "👥")

tab_register, tab_profile, tab_list = st.tabs(
    ["Register", "Full Profile", "All Candidates"]
)

with tab_register:
    st.markdown("#### Create a new candidate profile")
    with st.form("register_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            full_name = st.text_input("Full Name", placeholder="Jane Doe")
        with c2:
            email = st.text_input("Email", placeholder="jane@example.com")
        submit = st.form_submit_button("Create Candidate", type="primary", use_container_width=True)

        if submit:
            if full_name.strip():
                ok, data, err = api_post(
                    "/candidates/",
                    json_body={"full_name": full_name.strip(), "email": email.strip() or None},
                )
                if ok:
                    new_id = data.get("candidate_id")
                    st.session_state["active_candidate_id"] = new_id
                    st.success(f"Candidate created with ID **#{new_id}**")
                    st.balloons()
                    st.rerun()
                else:
                    st.error(err)
            else:
                st.warning("Full name is required.")

with tab_profile:
    cid = get_active_candidate_id()
    if not cid:
        st.warning("Select an active candidate in the sidebar first.")
    else:
        st.info(f"Viewing profile for candidate **#{cid}**")
        if st.button("Load Full Profile", type="primary"):
            ok, data, err = api_get(f"/candidates/{cid}")
            if ok and isinstance(data, dict):
                candidate = data.get("candidate", {})
                resume = data.get("resume") or {}
                github = data.get("github") or {}
                portfolio = data.get("portfolio") or {}

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Name", candidate.get("full_name", "—"))
                with c2:
                    st.metric("Email", candidate.get("email", "—"))
                with c3:
                    score = portfolio.get("portfolio_score")
                    st.metric("Portfolio Score", f"{score:.1f}" if score is not None else "—")

                if resume:
                    st.markdown("##### Resume Data")
                    skills = parse_json_field(resume.get("skills")) or []
                    if isinstance(skills, list):
                        render_skill_tags(skills)
                    with st.expander("Education, Projects & Experience"):
                        for section, key in [
                            ("Education", "education"),
                            ("Projects", "projects"),
                            ("Experience", "experience"),
                        ]:
                            items = parse_json_field(resume.get(key)) or []
                            if items:
                                st.markdown(f"**{section}**")
                                st.json(items)

                if github:
                    st.markdown("##### GitHub Profile")
                    g1, g2, g3 = st.columns(3)
                    with g1:
                        st.metric("Username", github.get("github_username", "—"))
                    with g2:
                        st.metric("Public Repos", github.get("public_repos", "—"))
                    with g3:
                        st.metric("Followers", github.get("followers", "—"))

                if portfolio:
                    st.markdown("##### Portfolio Analysis")
                    st.json(portfolio)

                if not resume and not github and not portfolio:
                    st.info("Profile exists but no resume, GitHub, or portfolio data yet.")
            else:
                st.error(err)

with tab_list:
    ok, candidates, err = api_get("/candidates/")
    if ok and isinstance(candidates, list):
        if candidates:
            rows = [
                {
                    "ID": c.get("id"),
                    "Name": c.get("full_name"),
                    "Email": c.get("email", "—"),
                    "Created": str(c.get("created_at", ""))[:19],
                }
                for c in candidates
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)

            pick = st.selectbox(
                "Set active candidate",
                options=[f"{r['Name']} (#{r['ID']})" for r in rows],
            )
            if st.button("Select", type="primary"):
                picked_id = int(pick.split("#")[-1].rstrip(")"))
                st.session_state["active_candidate_id"] = picked_id
                st.success(f"Active candidate set to **#{picked_id}**")
                st.rerun()
        else:
            st.info("No candidates in the database.")
    else:
        st.error(err)
