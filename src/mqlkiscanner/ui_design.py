"""Shared visual language and contextual help; no network or business logic."""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

from mqlkiscanner.help_content import HELP_CONTENT


@lru_cache(maxsize=1)
def _stylesheet() -> str:
    asset = Path(__file__).resolve().parents[2] / "assets" / "radar-grid.svg"
    graphic = base64.b64encode(asset.read_bytes()).decode("ascii")
    # Native config owns the palette; scoped CSS supplies the requested
    # background illustration and yellow information controls.
    return """<style>
    .stApp { background-image: radial-gradient(ellipse at 95% 0%, #11354455, transparent 58%); }
    .st-key-page_hero { padding: 1.8rem 2rem; border: 1px solid #30445E;
      border-radius: 16px; background-color: #111F32;
      background-image: linear-gradient(90deg,#111F32 28%,#111F32B8 62%,#111F3210),url('data:image/svg+xml;base64,""" + graphic + """');
      background-position: center,right center; background-size: cover,auto 125%;
      background-repeat: no-repeat; margin-bottom: .5rem; }
    .st-key-page_hero h1 { letter-spacing: -.035em; padding-top: 0; }
    .st-key-page_hero p { max-width: 760px; }
    .st-key-page_hero [data-testid="stCaptionContainer"] { color: #79D8DA; letter-spacing: .12em; font-weight: 650; }
    [class*="st-key-ui_info_"] button { background: #F6C453 !important; color: #192438 !important;
      border: 1px solid #FFDC89 !important; border-radius: 50% !important;
      width: 2rem !important; min-width: 2rem !important; height: 2rem !important;
      min-height: 2rem !important; padding: 0 !important; box-shadow: none !important; }
    [class*="st-key-ui_info_"] button:hover { background: #FFE19A !important; }
    [class*="st-key-ui_info_"] button p { font-family: Georgia,serif; font-size: 1.05rem;
      font-weight: 700; font-style: italic; line-height: 1; margin: 0; }
    [class*="st-key-ui_info_"] button:focus-visible { outline: 3px solid #E7EEF7; outline-offset: 3px; }
    .st-key-sidebar_brand { border-bottom: 1px solid #30445E; padding-bottom: 1.2rem; }
    .st-key-sidebar_brand h2 { letter-spacing: -.04em; }
    [data-testid="stMetric"] { border: 1px solid #30445E; border-radius: 12px;
      background: #112034; padding: 1rem 1.15rem; }
    [data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
    .mks-stepnum { display: inline-flex; align-items: center; justify-content: center;
      min-width: 1.9rem; height: 1.9rem; padding: 0 .45rem; margin-right: .5rem;
      border-radius: 999px; background: #F6C453; color: #192438;
      font-weight: 800; font-size: 1.05rem; vertical-align: middle;
      border: 1px solid #FFDC89; }
    .mks-stepnum.mks-blink { animation: mks-pulse 1.3s ease-in-out infinite; }
    @keyframes mks-pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(246,196,83,.65); transform: scale(1); }
      50% { box-shadow: 0 0 0 .55rem rgba(246,196,83,0); transform: scale(1.09); }
    }
    [data-testid="stBottomBlockContainer"] { background: #0D1829F5; border-top: 1px solid #30445E; }
    [role="dialog"] { border: 1px solid #50627C; }
    @media(max-width:640px) {
      .st-key-page_hero { padding: 1.25rem; background-size: cover,auto 100%; }
      .st-key-page_hero h1 { font-size: 1.8rem; }
    }
    @media(prefers-reduced-motion:reduce) { .stApp * { scroll-behavior: auto !important; }
      .mks-stepnum.mks-blink { animation: none; } }
    </style>"""


def apply_theme() -> None:
    st.html(_stylesheet())


def page_header(eyebrow: str, title: str, description: str) -> None:
    with st.container(key="page_hero", gap="xsmall"):
        st.caption(eyebrow.upper())
        st.title(title)
        st.markdown(description)


def help_topics() -> dict[str, tuple[str, str]]:
    from mqlkiscanner.help_settings import HELP_SETTINGS
    from mqlkiscanner.help_scan import HELP_SCAN
    return {**HELP_CONTENT, **HELP_SETTINGS, **HELP_SCAN}


@st.dialog("Hilfe & Hintergrund", width="medium")
def _help_dialog(topic: str) -> None:
    title, content = help_topics()[topic]
    st.subheader(title)
    st.markdown(content)
    if st.session_state.get("scan_workflow", {}).get("status") == "running":
        st.caption("Mit dem Kreuz oder Escape schließen. Der aktuelle Lauf wird dadurch nicht neu gestartet.")
    elif st.button("Verstanden", key="ui_help_close", type="primary"):
        st.rerun()


@st.fragment
def info_button(topic: str, key: str | None = None) -> None:
    """Help reruns only this fragment, preserving the active page."""
    title = help_topics()[topic][0]
    if st.button("i", key=f"ui_info_{key or topic}", help=f"Erklärung: {title}"):
        _help_dialog(topic)


def action_button(label: str, *, key: str, help_key: str, type: str = "secondary",
                  disabled: bool = False, icon: str | None = None) -> bool:
    with st.container():
        action, explanation = st.columns([1, 0.16], gap="xsmall", vertical_alignment="center", wrap=False)
        with action:
            clicked = st.button(label, key=key, type=type, disabled=disabled, icon=icon, wrap=True)
        with explanation:
            info_button(help_key, key=f"{key}_help")
    return clicked


def section_header(title: str, description: str = "", help_key: str | None = None) -> None:
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.subheader(title, width="content")
        if help_key:
            info_button(help_key, key=f"section_{help_key}")
    if description:
        st.caption(description)
