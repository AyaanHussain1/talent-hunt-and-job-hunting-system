import streamlit as st

from ui_helpers import (
    api_post,
    page_header,
    render_sidebar,
    require_candidate,
)

st.set_page_config(page_title="GitHub", page_icon="🐙", layout="wide")
render_sidebar()
page_header("GitHub Analyzer", "Fetch developer profiles, repos, and technical signals.", "🐙")

cid = require_candidate()
if cid:
    st.markdown(f"Linked to candidate **#{cid}**")

    st.markdown('<div class="section-header">Extract GitHub Data</div>', unsafe_allow_html=True)

    username = st.text_input(
        "GitHub username",
        placeholder="octocat",
        help="Public GitHub username — no @ symbol needed",
    )

    if st.button("Fetch & Save Profile", type="primary", disabled=not username.strip()):
        with st.spinner("Fetching repos and profile metrics from GitHub..."):
            ok, data, err = api_post(
                f"/candidates/{cid}/github",
                params={"github_username": username.strip()},
                timeout=120,
            )
            if ok and isinstance(data, dict):
                st.success(data.get("message", "GitHub data saved."))
                profile = data.get("profile") or {}
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Repos Saved", data.get("repos_saved", 0))
                c2.metric("Public Repos", profile.get("public_repos", "—"))
                c3.metric("Followers", profile.get("followers", "—"))
                c4.metric("Stars", profile.get("total_stars", profile.get("stars", "—")))

                if profile.get("top_languages"):
                    langs = profile["top_languages"]
                    if isinstance(langs, str):
                        st.markdown(f"**Top Languages:** {langs}")
                    elif isinstance(langs, list):
                        st.markdown(f"**Top Languages:** {', '.join(langs)}")

                with st.expander("Raw profile data"):
                    st.json(data)
            else:
                st.error(err)

    st.info("Tip: Run portfolio scoring after GitHub extraction for a complete talent profile.")
