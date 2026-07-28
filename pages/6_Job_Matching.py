import streamlit as st
import pandas as pd

from ui_helpers import (
    api_get,
    api_post,
    page_header,
    parse_json_field,
    render_sidebar,
    render_skill_tags,
    require_candidate,
)

st.set_page_config(page_title="Job Matching", page_icon="🎯", layout="wide")
render_sidebar()
page_header("Job Matching", "Two-stage vector + BM25 fusion matching engine.", "🎯")

cid = require_candidate()
if cid:
    st.markdown(f"Matching jobs for candidate **#{cid}**")

    if st.button("Run Matching Engine", type="primary"):
        with st.spinner("Computing reciprocal rank fusion scores..."):
            ok, data, err = api_post(f"/candidates/{cid}/match", timeout=180)
            if ok and isinstance(data, dict):
                st.success(
                    f"Evaluated **{data.get('total_jobs_evaluated', 0)}** jobs for "
                    f"**{data.get('candidate_name', 'candidate')}**"
                )
                matches = data.get("matches") or []
                if matches:
                    st.session_state[f"last_matches_{cid}"] = matches
                else:
                    st.info("No matches above threshold.")
            else:
                st.error(err)

    st.markdown('<div class="section-header">Saved Matches</div>', unsafe_allow_html=True)

    if st.button("Load Saved Matches"):
        ok, rows, err = api_get(f"/candidates/{cid}/matches")
        if ok:
            st.session_state[f"last_matches_{cid}"] = rows if isinstance(rows, list) else []
        else:
            st.error(err)

    matches = st.session_state.get(f"last_matches_{cid}")
    if matches:
        table_rows = []
        for m in matches:
            if not isinstance(m, dict):
                continue
            matched = parse_json_field(m.get("matched_skills")) or []
            missing = parse_json_field(m.get("missing_skills")) or []
            table_rows.append(
                {
                    "Score": round(float(m.get("match_score", 0)), 1),
                    "Title": m.get("title") or m.get("job_title", "—"),
                    "Company": m.get("company", "—"),
                    "Type": m.get("job_type", "—"),
                    "Location": m.get("location", "—"),
                    "Matched Skills": ", ".join(matched) if isinstance(matched, list) else str(matched),
                    "Missing Skills": ", ".join(missing) if isinstance(missing, list) else str(missing),
                }
            )

        if table_rows:
            df = pd.DataFrame(table_rows).sort_values("Score", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.markdown("#### Top Match Detail")
            top = matches[0] if isinstance(matches[0], dict) else {}
            t1, t2 = st.columns(2)
            with t1:
                matched = parse_json_field(top.get("matched_skills")) or []
                if isinstance(matched, list):
                    render_skill_tags(matched, label="Matched Skills")
            with t2:
                missing = parse_json_field(top.get("missing_skills")) or []
                if isinstance(missing, list) and missing:
                    st.markdown("**Skill Gaps**")
                    for sk in missing:
                        st.markdown(f"- ❌ {sk}")
        else:
            st.info("No match records to display.")
    else:
        st.info("Run the matching engine or load saved matches to see results.")
