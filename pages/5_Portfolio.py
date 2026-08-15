import streamlit as st

from ui_helpers import api_get, api_post, page_header, parse_json_field, render_score_bar, render_sidebar, render_skill_tags, require_candidate


def render_portfolio_result(result: dict) -> None:
    score = float(result.get("portfolio_score", 0))
    total_repos = int(result.get("total_repos", 0) or 0)
    live_projects = int(result.get("live_projects_count", 0) or 0)
    if total_repos == 0:
        st.warning("A saved portfolio calculation exists, but it has no repositories to evaluate. Save GitHub data first, then recalculate.")
        return

    st.markdown("#### Saved portfolio score")
    c1, c2, c3 = st.columns(3)
    c1.metric("Portfolio Score", f"{score:.1f} / 100")
    c2.metric("Repositories Analyzed", total_repos)
    c3.metric("Live Projects", live_projects)
    render_score_bar("Portfolio Quality", score)

    languages = parse_json_field(result.get("primary_languages")) or []
    if isinstance(languages, list) and languages:
        render_skill_tags(languages, label="Primary Languages")

    strengths = parse_json_field(result.get("strengths")) or []
    weaknesses = parse_json_field(result.get("weaknesses")) or []
    left, right = st.columns(2)
    with left:
        st.markdown("**Strengths**")
        if isinstance(strengths, list) and strengths:
            for item in strengths:
                st.markdown(f"- {item}")
        else:
            st.caption("No strengths were recorded.")
    with right:
        st.markdown("**Areas to improve**")
        if isinstance(weaknesses, list) and weaknesses:
            for item in weaknesses:
                st.markdown(f"- {item}")
        else:
            st.caption("No improvement areas were recorded.")


st.set_page_config(page_title="Portfolio", layout="wide")
render_sidebar()
page_header("Portfolio Scoring", "View saved portfolio analysis or calculate a score from the candidate's saved GitHub repositories.")

cid = require_candidate()
if cid:
    ok, profile_data, err = api_get(f"/candidates/{cid}")
    if not ok or not isinstance(profile_data, dict):
        st.error(err or "Could not load the selected candidate.")
        st.stop()

    github = profile_data.get("github") or {}
    saved_portfolio = profile_data.get("portfolio") or {}
    st.markdown("#### Portfolio status")
    if not github:
        st.warning("No saved GitHub profile was found for this candidate. Open the GitHub page and save a profile before calculating a portfolio score.")
        st.page_link("pages/4_GitHub.py", label="Open GitHub", use_container_width=True)
    elif saved_portfolio:
        st.success("Saved portfolio analysis found for this candidate.")
        render_portfolio_result(saved_portfolio)
    else:
        st.info("No portfolio score is saved yet. Calculate one from the saved GitHub repositories.")

    if github:
        action_label = "Recalculate Portfolio Score" if saved_portfolio else "Calculate Portfolio Score"
        if st.button(action_label, type="primary"):
            with st.spinner("Calculating portfolio score from saved repositories..."):
                ok, result, err = api_post(f"/candidates/{cid}/portfolio", timeout=120)
                if ok and isinstance(result, dict):
                    st.success("Portfolio score saved.")
                    render_portfolio_result(result)
                else:
                    st.error(err or "Portfolio calculation failed.")
