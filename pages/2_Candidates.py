import streamlit as st

from ui_helpers import api_get, api_post, page_header, parse_json_field, render_detail_card, render_sidebar, render_skill_tags


st.set_page_config(page_title="Candidates", layout="wide")
render_sidebar()
page_header("Candidate Management", "Register talent, view profiles, and choose the candidate used by analysis pages.")


def candidate_options(candidates: list[dict]) -> dict[str, int]:
    return {
        f"{candidate.get('full_name', 'Unnamed')} (#{candidate['id']})": candidate["id"]
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("id") is not None
    }


tab_register, tab_profile, tab_list = st.tabs(["Register", "Full Profile", "All Candidates"])

with tab_register:
    st.markdown("#### Create a candidate profile")
    with st.form("register_form", clear_on_submit=True):
        full_name = st.text_input("Full Name", placeholder="Jane Doe")
        email = st.text_input("Email", placeholder="jane@example.com")
        submit = st.form_submit_button("Create Candidate", type="primary")
    if submit:
        if not full_name.strip():
            st.warning("Full name is required.")
        else:
            ok, data, err = api_post("/candidates/", json_body={"full_name": full_name.strip(), "email": email.strip() or None})
            if ok:
                st.success(f"Candidate created with ID #{data.get('candidate_id')}.")
            else:
                st.error(err)

with tab_profile:
    ok, candidates, err = api_get("/candidates/")
    if not ok:
        st.error(err)
    elif not isinstance(candidates, list) or not candidates:
        st.info("No candidates registered yet.")
    else:
        options = candidate_options(candidates)
        labels = list(options)
        current_id = st.session_state.get("active_candidate_id")
        default_index = next((i for i, label in enumerate(labels) if options[label] == current_id), 0)
        selected_label = st.selectbox("Choose candidate", labels, index=default_index)
        selected_id = options[selected_label]
        if st.button("Activate Candidate", type="primary"):
            st.session_state["active_candidate_id"] = selected_id
            st.success(f"Candidate #{selected_id} is now active.")

        profile_id = st.session_state.get("active_candidate_id") or selected_id
        st.caption(f"Showing profile for candidate #{profile_id}.")
        st.markdown("#### Continue with this candidate")
        link1, link2, link3, link4 = st.columns(4)
        link1.page_link("pages/3_Resume.py", label="Resume and ATS", use_container_width=True)
        link2.page_link("pages/4_GitHub.py", label="GitHub", use_container_width=True)
        link3.page_link("pages/5_Portfolio.py", label="Portfolio", use_container_width=True)
        link4.page_link("pages/6_Job_Matching.py", label="Job Matching", use_container_width=True)
        ok, data, err = api_get(f"/candidates/{profile_id}")
        if not ok or not isinstance(data, dict):
            st.error(err)
        else:
            candidate = data.get("candidate") or {}
            resume = data.get("resume") or {}
            github = data.get("github") or {}
            portfolio = data.get("portfolio") or {}
            c1, c2, c3 = st.columns(3)
            with c1:
                render_detail_card("Candidate", candidate.get("full_name", "Not available"))
            with c2:
                render_detail_card("Email", candidate.get("email") or "Not available")
            with c3:
                has_portfolio_data = portfolio and int(portfolio.get("total_repos", 0) or 0) > 0
                score = portfolio.get("portfolio_score") if has_portfolio_data else None
                render_detail_card("Portfolio Score", f"{float(score):.1f} / 100" if score is not None else "Not available")
            if resume:
                st.markdown("#### Resume")
                skills = parse_json_field(resume.get("skills")) or []
                if isinstance(skills, list):
                    render_skill_tags(skills)
                for title, field in [("Education", "education"), ("Projects", "projects"), ("Experience", "experience")]:
                    items = parse_json_field(resume.get(field)) or []
                    if isinstance(items, list) and items:
                        with st.expander(title):
                            st.dataframe(items, use_container_width=True, hide_index=True)
            if github:
                st.markdown("#### GitHub")
                g1, g2, g3 = st.columns(3)
                g1.metric("Username", github.get("github_username", "Not available"))
                g2.metric("Public Repositories", github.get("public_repos", 0))
                g3.metric("Followers", github.get("followers", 0))
            if portfolio:
                st.markdown("#### Portfolio")
                strengths = parse_json_field(portfolio.get("strengths")) or []
                weaknesses = parse_json_field(portfolio.get("weaknesses")) or []
                left, right = st.columns(2)
                with left:
                    if isinstance(strengths, list) and strengths:
                        st.markdown("**Strengths**")
                        for item in strengths:
                            st.markdown(f"- {item}")
                with right:
                    if isinstance(weaknesses, list) and weaknesses:
                        st.markdown("**Areas to improve**")
                        for item in weaknesses:
                            st.markdown(f"- {item}")
            if not resume and not github and not portfolio:
                st.info("This candidate has no resume, GitHub, or portfolio data yet.")

with tab_list:
    ok, candidates, err = api_get("/candidates/")
    if not ok:
        st.error(err)
    elif not isinstance(candidates, list) or not candidates:
        st.info("No candidates in the database.")
    else:
        options = candidate_options(candidates)
        selected_label = st.selectbox("Candidate to activate", list(options), key="all_candidates_selection")
        if st.button("Activate Selected Candidate", type="primary"):
            st.session_state["active_candidate_id"] = options[selected_label]
            st.success(f"Candidate #{options[selected_label]} is now active.")
        rows = [{"ID": c.get("id"), "Name": c.get("full_name"), "Email": c.get("email") or "Not available", "Created": str(c.get("created_at", ""))[:19]} for c in candidates if isinstance(c, dict)]
        st.dataframe(rows, use_container_width=True, hide_index=True)
