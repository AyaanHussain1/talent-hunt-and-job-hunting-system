from urllib.parse import urlparse

import streamlit as st

from ui_helpers import api_get, api_post, page_header, render_sidebar, require_candidate


def github_username(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if "github.com" in value.lower():
        path = urlparse(value if "://" in value else f"https://{value}").path.strip("/")
        return path.split("/")[0] if path else ""
    return value.lstrip("@")


st.set_page_config(page_title="GitHub", layout="wide")
render_sidebar()
page_header("GitHub Analyzer", "Use an existing GitHub profile or save a new one for the selected candidate.")

cid = require_candidate()
if cid:
    ok, profile_data, err = api_get(f"/candidates/{cid}")
    if not ok or not isinstance(profile_data, dict):
        st.error(err or "Could not load the selected candidate.")
        st.stop()

    saved_github = profile_data.get("github") or {}
    saved_resume = profile_data.get("resume") or {}
    saved_username = saved_github.get("github_username") or github_username(saved_resume.get("github_url", ""))

    st.markdown("#### GitHub connection")
    if saved_github:
        c1, c2, c3 = st.columns(3)
        c1.metric("Saved Account", saved_github.get("github_username", "Not available"))
        c2.metric("Public Repositories", saved_github.get("public_repos", 0))
        c3.metric("Followers", saved_github.get("followers", 0))
        st.success("Saved GitHub data found for this candidate. Enter another profile only if you want to replace it.")
    elif saved_username:
        st.info(f"GitHub URL found in the stored resume: {saved_resume.get('github_url')}")
    else:
        st.warning("No GitHub profile is saved. Add a public GitHub username or profile URL to continue.")

    source = st.text_input(
        "GitHub username or profile URL",
        value=saved_username,
        placeholder="octocat or https://github.com/octocat",
    )
    username = github_username(source)
    if st.button("Save GitHub Data", type="primary", disabled=not username):
        with st.spinner("Fetching and saving GitHub data..."):
            ok, data, err = api_post(f"/candidates/{cid}/github", params={"github_username": username}, timeout=120)
            if ok:
                st.success(data.get("message", "GitHub data saved."))
                st.rerun()
            else:
                st.error(err)
