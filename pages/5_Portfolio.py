import streamlit as st

from ui_helpers import (
    api_get,
    api_post,
    page_header,
    render_score_bar,
    render_sidebar,
    render_skill_tags,
    require_candidate,
)

st.set_page_config(page_title="Portfolio", page_icon="📈", layout="wide")
render_sidebar()
page_header("Portfolio Scoring", "Evaluate project quality and engineering readiness.", "📈")

cid = require_candidate()
if cid:
    st.markdown(f"Analyzing candidate **#{cid}**")

    col_calc, col_fetch = st.columns(2)
    with col_calc:
        run_calc = st.button("Calculate Score", type="primary", use_container_width=True)
    with col_fetch:
        run_fetch = st.button("Load Saved Score", use_container_width=True)

    result = None
    if run_calc:
        with st.spinner("Running portfolio analysis..."):
            ok, result, err = api_post(f"/candidates/{cid}/portfolio", timeout=120)
            if not ok:
                st.error(err)
                result = None
            else:
                st.success("Portfolio score calculated and saved.")

    if run_fetch:
        ok, result, err = api_get(f"/candidates/{cid}/portfolio")
        if not ok:
            st.error(err)
            result = None

    if result and isinstance(result, dict):
        score = result.get("portfolio_score", 0)
        st.metric("Portfolio Score", f"{score:.1f} / 100")
        render_score_bar("Overall Quality", score)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Repos", result.get("total_repos", 0))
        c2.metric("Live Projects", result.get("live_projects_count", 0))
        c3.metric("Candidate ID", result.get("candidate_id", cid))

        langs = result.get("primary_languages") or []
        if isinstance(langs, list) and langs:
            render_skill_tags(langs, label="Primary Languages")

        s_col, w_col = st.columns(2)
        with s_col:
            if result.get("strengths"):
                st.markdown("**Strengths**")
                for s in result["strengths"]:
                    st.markdown(f"- ✅ {s}")
        with w_col:
            if result.get("weaknesses"):
                st.markdown("**Weaknesses**")
                for w in result["weaknesses"]:
                    st.markdown(f"- ⚠️ {w}")
