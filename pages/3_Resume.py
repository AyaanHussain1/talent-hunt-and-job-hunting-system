import streamlit as st

from ui_helpers import (
    api_get,
    api_post,
    page_header,
    render_score_bar,
    render_sidebar,
    require_candidate,
)

st.set_page_config(page_title="Resume & ATS", page_icon="📄", layout="wide")
render_sidebar()
page_header("Resume & ATS", "Upload PDF resumes and generate ATS optimization reports.", "📄")

cid = require_candidate()
if cid:
    st.markdown(f"Processing for candidate **#{cid}**")

    st.markdown('<div class="section-header">Upload Resume</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("PDF resume only", type=["pdf"], label_visibility="collapsed")

    if uploaded and st.button("Parse & Save Resume", type="primary"):
        with st.spinner("Extracting fields with LLM — this may take a minute..."):
            files = {"file": (uploaded.name, uploaded.getvalue(), "application/pdf")}
            ok, data, err = api_post(f"/candidates/{cid}/resume", files=files, timeout=180)
            if ok:
                st.success("Resume parsed and saved successfully.")
                m1, m2, m3 = st.columns(3)
                m1.metric("Skills Found", data.get("skills_found", 0))
                m2.metric("Projects Found", data.get("projects_found", 0))
                m3.metric("Education Found", data.get("education_found", 0))
            else:
                st.error(err)

    st.markdown('<div class="section-header">ATS Diagnostic Report</div>', unsafe_allow_html=True)

    if st.button("Generate ATS Report", type="primary"):
        with st.spinner("Analyzing resume for ATS compatibility..."):
            ok, report, err = api_get(f"/candidates/{cid}/ats", timeout=60)
            if ok and isinstance(report, dict):
                overall = report.get("overall_score", 0)
                st.metric("Overall ATS Score", f"{overall}/100")

                left, right = st.columns(2)
                score_fields = [
                    ("Contact", "contact_score"),
                    ("Summary", "summary_score"),
                    ("Skills", "skills_score"),
                    ("Experience", "experience_score"),
                    ("Education", "education_score"),
                    ("Projects", "projects_score"),
                    ("Certifications", "certifications_score"),
                    ("Formatting", "formatting_score"),
                ]
                with left:
                    for label, key in score_fields[:4]:
                        render_score_bar(label, report.get(key, 0))
                with right:
                    for label, key in score_fields[4:]:
                        render_score_bar(label, report.get(key, 0))

                rec = report.get("hiring_recommendation", "")
                if rec:
                    st.markdown(f"**Hiring Recommendation:** {rec}")

                if report.get("strengths"):
                    st.markdown("**Strengths**")
                    for s in report["strengths"]:
                        st.markdown(f"- ✅ {s}")

                if report.get("weaknesses"):
                    st.markdown("**Areas to Improve**")
                    for w in report["weaknesses"]:
                        st.markdown(f"- ⚠️ {w}")

                if report.get("suggestions"):
                    with st.expander("Detailed Suggestions"):
                        for s in report["suggestions"]:
                            st.markdown(f"- {s}")

                if report.get("missing_keywords"):
                    st.markdown("**Missing Keywords**")
                    st.write(", ".join(report["missing_keywords"]))
            else:
                st.error(err or "No ATS report available. Upload a resume first.")
