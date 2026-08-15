"""Shared UI components, styling, and API helpers for the Streamlit frontend."""

from __future__ import annotations

import json
from html import escape
from typing import Any

import requests
import streamlit as st

DEFAULT_API_URL = "http://127.0.0.1:8000"


def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        #MainMenu, footer { visibility: hidden; }

        /* Keep Streamlit's native sidebar toggle available at all times. */
        header[data-testid="stHeader"] {
            background: rgba(15, 23, 42, 0.88);
            border-bottom: 1px solid rgba(148, 163, 184, 0.14);
        }

        [data-testid="stSidebarCollapsedControl"] {
            display: flex !important;
            visibility: visible !important;
            background: #6366F1 !important;
            border-radius: 8px;
            color: white !important;
            margin: 0.35rem;
        }

        [data-testid="stSidebarCollapseButton"] {
            display: flex !important;
            visibility: visible !important;
        }

        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }

        .hero-banner {
            background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 45%, #06B6D4 100%);
            padding: 2.5rem 2rem;
            border-radius: 20px;
            color: white;
            margin-bottom: 1.5rem;
            box-shadow: 0 20px 40px rgba(99, 102, 241, 0.25);
        }

        .hero-banner h1 {
            font-size: 2.2rem;
            font-weight: 800;
            margin: 0 0 0.5rem 0;
            letter-spacing: -0.02em;
        }

        .hero-banner p {
            font-size: 1.05rem;
            opacity: 0.92;
            margin: 0;
            line-height: 1.6;
        }

        .hero-badge {
            display: inline-block;
            background: rgba(255,255,255,0.2);
            backdrop-filter: blur(8px);
            padding: 0.35rem 0.85rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin-bottom: 0.75rem;
        }

        .metric-card {
            background: linear-gradient(145deg, #1E293B 0%, #0F172A 100%);
            border: 1px solid rgba(99, 102, 241, 0.25);
            border-radius: 16px;
            padding: 1.25rem 1.5rem;
            text-align: center;
            box-shadow: 0 8px 24px rgba(0,0,0,0.2);
        }

        .metric-card .value {
            font-size: 2rem;
            font-weight: 800;
            background: linear-gradient(90deg, #818CF8, #22D3EE);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .metric-card .label {
            font-size: 0.85rem;
            color: #94A3B8;
            font-weight: 500;
            margin-top: 0.25rem;
        }

        .feature-card {
            background: #1E293B;
            border: 1px solid rgba(148, 163, 184, 0.15);
            border-radius: 16px;
            padding: 1.5rem;
            height: 100%;
            transition: border-color 0.2s;
        }

        .feature-card:hover {
            border-color: rgba(99, 102, 241, 0.5);
        }

        .feature-card h3 {
            font-size: 1.05rem;
            font-weight: 700;
            margin: 0 0 0.5rem 0;
            color: #F1F5F9;
        }

        .feature-card p {
            font-size: 0.88rem;
            color: #94A3B8;
            margin: 0;
            line-height: 1.5;
        }

        .feature-icon {
            font-size: 1.75rem;
            margin-bottom: 0.75rem;
        }

        .section-header {
            font-size: 1.35rem;
            font-weight: 700;
            color: #F1F5F9;
            margin: 1.5rem 0 1rem 0;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid rgba(99, 102, 241, 0.3);
        }

        .status-pill {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
        }

        .status-online { background: rgba(34, 197, 94, 0.15); color: #4ADE80; }
        .status-offline { background: rgba(239, 68, 68, 0.15); color: #F87171; }

        div[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%);
            border-right: 1px solid rgba(99, 102, 241, 0.2);
        }

        .detail-card {
            background: #162235;
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 14px;
            padding: 1rem 1.1rem;
            min-height: 92px;
        }

        .detail-card .label {
            color: #94A3B8;
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .detail-card .value {
            color: #F8FAFC;
            font-size: 1.1rem;
            font-weight: 700;
            margin-top: 0.45rem;
            overflow-wrap: anywhere;
        }

        div[data-testid="stSidebar"] > div:first-child {
            padding-top: 1rem;
        }

        div[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            padding-top: 0.5rem;
        }

        div[data-testid="stSidebar"] .stMarkdown h1 {
            font-size: 1.1rem;
            font-weight: 800;
            background: linear-gradient(90deg, #818CF8, #22D3EE);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .stButton > button[kind="primary"] {
            background: linear-gradient(90deg, #6366F1, #8B5CF6);
            border: none;
            border-radius: 10px;
            font-weight: 600;
            transition: opacity 0.2s, transform 0.1s;
        }

        .stButton > button[kind="primary"]:hover {
            opacity: 0.9;
            transform: translateY(-1px);
        }

        .score-ring-label {
            text-align: center;
            font-size: 0.85rem;
            color: #94A3B8;
            margin-top: 0.25rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session_state() -> None:
    if "api_base_url" not in st.session_state:
        st.session_state["api_base_url"] = DEFAULT_API_URL
    if "active_candidate_id" not in st.session_state:
        st.session_state["active_candidate_id"] = None


def get_base_url() -> str:
    init_session_state()
    return st.session_state["api_base_url"].rstrip("/")


def get_active_candidate_id() -> int | None:
    init_session_state()
    return st.session_state.get("active_candidate_id")


def render_candidate_selector(key: str = "module_candidate_selector") -> int | None:
    """Show a local candidate picker on a page and return its active candidate ID."""
    init_session_state()
    ok, candidates, err = api_get("/candidates/", timeout=5)
    if not ok:
        st.error(err)
        return None
    if not isinstance(candidates, list) or not candidates:
        st.info("No candidates are available. Create one from the Candidates page.")
        return None

    options = {
        f"{candidate.get('full_name', 'Unnamed')} (#{candidate['id']})": candidate["id"]
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("id") is not None
    }
    if not options:
        st.info("No valid candidates are available.")
        return None

    labels = list(options)
    current = st.session_state.get("active_candidate_id")
    default_index = next((i for i, label in enumerate(labels) if options[label] == current), 0)
    selected = st.selectbox("Candidate", labels, index=default_index, key=key)
    selected_id = options[selected]
    if st.button("Select Candidate", type="primary", key=f"{key}_button"):
        st.session_state["active_candidate_id"] = selected_id
        st.rerun()

    active_id = st.session_state.get("active_candidate_id")
    if active_id:
        st.caption(f"Current candidate: #{active_id}")
    else:
        st.caption("Choose a candidate, then select Use Selected Candidate.")
    return active_id


def api_get(path: str, *, params: dict | None = None, timeout: int = 30) -> tuple[bool, Any, str]:
    """Returns (success, data_or_none, error_message)."""
    try:
        res = requests.get(f"{get_base_url()}{path}", params=params, timeout=timeout)
        if res.status_code == 200:
            return True, res.json(), ""
        return False, None, f"HTTP {res.status_code}: {res.text}"
    except requests.exceptions.ConnectionError:
        return False, None, f"Cannot connect to API at {get_base_url()}"
    except Exception as exc:
        return False, None, str(exc)


def api_post(
    path: str,
    *,
    json_body: dict | None = None,
    params: dict | None = None,
    files: dict | None = None,
    timeout: int = 120,
) -> tuple[bool, Any, str]:
    try:
        res = requests.post(
            f"{get_base_url()}{path}",
            json=json_body,
            params=params,
            files=files,
            timeout=timeout,
        )
        if res.status_code == 200:
            return True, res.json(), ""
        return False, None, f"HTTP {res.status_code}: {res.text}"
    except requests.exceptions.ConnectionError:
        return False, None, f"Cannot connect to API at {get_base_url()}"
    except Exception as exc:
        return False, None, str(exc)


def check_api_health() -> bool:
    ok, _, _ = api_get("/candidates/", timeout=5)
    return ok


def render_sidebar() -> None:
    init_session_state()
    with st.sidebar:
        st.markdown("# TalentAI")
        st.caption("AI Talent Discovery Platform")
        st.divider()

        st.session_state["api_base_url"] = st.text_input(
            "API Base URL",
            value=st.session_state["api_base_url"],
            help="FastAPI backend address",
        )

        online = check_api_health()
        status_class = "status-online" if online else "status-offline"
        status_text = "API Online" if online else "API Offline"
        st.markdown(
            f'<span class="status-pill {status_class}">{status_text}</span>',
            unsafe_allow_html=True,
        )


def page_header(title: str, subtitle: str) -> None:
    inject_custom_css()
    st.markdown(
        f"""
        <div class="hero-banner">
            <div class="hero-badge">Startup Platform</div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label: str, value: str | int | float) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="value">{value}</div>
            <div class="label">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_detail_card(label: str, value: str | int | float) -> None:
    st.markdown(
        f'<div class="detail-card"><div class="label">{escape(str(label))}</div><div class="value">{escape(str(value))}</div></div>',
        unsafe_allow_html=True,
    )


def require_candidate(message: str = "Select an active candidate from Candidates > Full Profile to continue.") -> int | None:
    cid = render_candidate_selector()
    if not cid:
        st.warning(message)
    return cid


def parse_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def render_score_bar(label: str, score: int | float, max_score: int = 100) -> None:
    pct = min(max(float(score) / max_score, 0.0), 1.0)
    st.markdown(f"**{label}** — {score}/{max_score}")
    st.progress(pct)


def render_skill_tags(skills: list[str], *, label: str = "Skills") -> None:
    if not skills:
        return
    st.markdown(f"**{label}**")
    cols = st.columns(min(len(skills), 6) or 1)
    for i, skill in enumerate(skills[:12]):
        with cols[i % len(cols)]:
            st.markdown(
                f'<span class="status-pill status-online">{skill}</span>',
                unsafe_allow_html=True,
            )
    if len(skills) > 12:
        st.caption(f"+ {len(skills) - 12} more")
