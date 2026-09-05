"""Shared visual language and contextual help; no network or business logic."""
from __future__ import annotations

import base64
import html
import re
from functools import lru_cache
from pathlib import Path

import streamlit as st

from mqlkiscanner.help_content import HELP_CONTENT


@lru_cache(maxsize=1)
def _stylesheet() -> str:
    assets_dir = Path(__file__).resolve().parents[2] / "assets"
    
    marble_file = assets_dir / "dark_marble_bg.jpg"
    if not marble_file.exists():
        marble_file = assets_dir / "dark_marble_texture.jpg"
    marble_b64 = base64.b64encode(marble_file.read_bytes()).decode("ascii") if marble_file.exists() else ""
    
    radar_file = assets_dir / "radar-grid.svg"
    radar_b64 = base64.b64encode(radar_file.read_bytes()).decode("ascii") if radar_file.exists() else ""

    return f"""<style>
    /* Global Canvas: Deep Obsidian & Dark Marble Luxury Texture */
    .stApp {{
        background-color: #0A111E;
        background-image: 
            radial-gradient(ellipse at 85% 5%, rgba(0, 210, 211, 0.12), transparent 45%),
            radial-gradient(ellipse at 15% 95%, rgba(245, 158, 11, 0.08), transparent 40%),
            linear-gradient(180deg, rgba(10, 17, 30, 0.84) 0%, rgba(10, 17, 30, 0.94) 100%),
            url('data:image/jpeg;base64,{marble_b64}');
        background-size: auto, auto, auto, 1024px 1024px;
        background-repeat: no-repeat, no-repeat, no-repeat, repeat;
        background-attachment: fixed;
    }}

    /* Sidebar: Obsidian Glass over Marble */
    [data-testid="stSidebar"] {{
        background-color: #080E1A !important;
        background-image: 
            radial-gradient(ellipse at 50% 0%, rgba(0, 210, 211, 0.09), transparent 50%),
            linear-gradient(180deg, rgba(8, 14, 26, 0.88), rgba(8, 14, 26, 0.96)),
            url('data:image/jpeg;base64,{marble_b64}') !important;
        background-size: auto, auto, 1024px 1024px !important;
        background-repeat: no-repeat, no-repeat, repeat !important;
        border-right: 1px solid rgba(39, 62, 91, 0.6) !important;
    }}

    /* Glassmorphism for all standard bordered containers */
    [data-testid="stVerticalBlockBorderWrapper"] > div {{
        background: linear-gradient(145deg, rgba(18, 30, 48, 0.78) 0%, rgba(12, 20, 34, 0.88) 100%) !important;
        backdrop-filter: blur(14px) saturate(140%) !important;
        -webkit-backdrop-filter: blur(14px) saturate(140%) !important;
        border: 1px solid rgba(56, 189, 248, 0.16) !important;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.45), inset 0 1px 1px 0 rgba(255, 255, 255, 0.05) !important;
        border-radius: 14px !important;
        transition: border-color 0.25s ease, box-shadow 0.25s ease;
    }}
    [data-testid="stVerticalBlockBorderWrapper"] > div:hover {{
        border-color: rgba(56, 189, 248, 0.28) !important;
        box-shadow: 0 8px 26px -2px rgba(0, 0, 0, 0.55), inset 0 1px 1px 0 rgba(255, 255, 255, 0.08) !important;
    }}

    /* Page Hero: Executive Glass Header */
    .st-key-page_hero {{
        padding: 1.8rem 2.2rem;
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 18px;
        background-color: #0E1A2C;
        background-image: 
            linear-gradient(90deg, #0E1A2C 28%, #0E1A2CB8 62%, #0E1A2C10),
            url('data:image/svg+xml;base64,{radar_b64}');
        background-position: center, right center;
        background-size: cover, auto 125%;
        background-repeat: no-repeat;
        margin-bottom: 0.8rem;
        box-shadow: 0 12px 36px -4px rgba(0, 0, 0, 0.5), 0 0 20px rgba(0, 210, 211, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.08);
    }}
    .st-key-page_hero h1 {{
        letter-spacing: -.035em;
        padding-top: 0;
        color: #F8FAFC;
        text-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
    }}
    .st-key-page_hero p {{
        max-width: 780px;
        color: #CBD5E1;
        line-height: 1.5;
    }}
    .st-key-page_hero [data-testid="stCaptionContainer"] {{
        color: #00D2D3;
        letter-spacing: .14em;
        font-weight: 700;
    }}
    .st-key-page_hero img {{
        border-radius: 14px;
        border: 1px solid rgba(56, 189, 248, 0.3);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6), 0 0 16px rgba(0, 210, 211, 0.15);
    }}

    /* Info Icon Button (Gold Dial) */
    [class*="st-key-ui_info_"] button {{
        background: linear-gradient(135deg, #F59E0B 0%, #D97706 100%) !important;
        color: #0F172A !important;
        border: 1px solid #FCD34D !important;
        border-radius: 50% !important;
        width: 2rem !important;
        min-width: 2rem !important;
        height: 2rem !important;
        min-height: 2rem !important;
        padding: 0 !important;
        box-shadow: 0 2px 8px rgba(245, 158, 11, 0.3) !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }}
    [class*="st-key-ui_info_"] button:hover {{
        background: linear-gradient(135deg, #FBBF24 0%, #F59E0B 100%) !important;
        transform: scale(1.08) !important;
        box-shadow: 0 0 12px rgba(245, 158, 11, 0.55) !important;
    }}
    [class*="st-key-ui_info_"] button p {{
        font-family: Georgia, serif;
        font-size: 1.05rem;
        font-weight: 800;
        font-style: italic;
        line-height: 1;
        margin: 0;
    }}
    [class*="st-key-ui_info_"] button:focus-visible {{
        outline: 3px solid #00D2D3;
        outline-offset: 3px;
    }}

    .st-key-sidebar_brand {{
        border-bottom: 1px solid rgba(39, 62, 91, 0.7);
        padding-bottom: 1.2rem;
    }}
    .st-key-sidebar_brand h2 {{
        letter-spacing: -.04em;
        color: #F8FAFC;
    }}
    .st-key-sidebar_brand img {{
        border-radius: 12px;
        border: 1px solid rgba(245, 158, 11, 0.35);
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5), 0 0 14px rgba(245, 158, 11, 0.15);
        margin-bottom: 0.5rem;
    }}

    /* Metrics & KPIs: Slate Glass with Glowing Accents */
    [data-testid="stMetric"] {{
        border: 1px solid rgba(56, 189, 248, 0.16) !important;
        border-radius: 14px !important;
        background: linear-gradient(145deg, rgba(18, 32, 52, 0.75) 0%, rgba(11, 19, 32, 0.88) 100%) !important;
        backdrop-filter: blur(12px) !important;
        padding: 1.1rem 1.25rem !important;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
        transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease !important;
    }}
    [data-testid="stMetric"]:hover {{
        transform: translateY(-2px);
        border-color: rgba(0, 210, 211, 0.35) !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5), 0 0 14px rgba(0, 210, 211, 0.15) !important;
    }}
    [data-testid="stMetricValue"] {{
        font-variant-numeric: tabular-nums;
        font-weight: 750 !important;
        letter-spacing: -0.02em;
        color: #F8FAFC !important;
    }}
    [data-testid="stMetricLabel"] {{
        color: #94A3B8 !important;
        font-weight: 600 !important;
        letter-spacing: 0.03em;
        text-transform: uppercase;
        font-size: 0.78rem !important;
    }}

    /* Flow / Stations */
    .mks-flow {{
        display: flex;
        flex-wrap: wrap;
        align-items: stretch;
        gap: .65rem;
        margin: .35rem 0 0.15rem;
    }}
    .mks-flow-step {{
        flex: 1 1 9.5rem;
        display: flex;
        flex-direction: column;
        gap: .35rem;
        padding: .9rem 1.1rem;
        border: 1px solid rgba(56, 189, 248, 0.18);
        border-radius: 14px;
        background: linear-gradient(145deg, rgba(18, 32, 52, 0.78) 0%, rgba(11, 20, 33, 0.88) 100%);
        backdrop-filter: blur(12px);
        min-width: 0;
    }}
    .mks-flow-num {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.8rem;
        height: 1.8rem;
        border-radius: 999px;
        background: linear-gradient(135deg, #F59E0B, #D97706);
        color: #0F172A;
        font-weight: 850;
        font-size: .95rem;
        border: 1px solid #FCD34D;
        box-shadow: 0 2px 8px rgba(245, 158, 11, 0.3);
    }}
    .mks-flow-step strong {{
        color: #F8FAFC;
        font-size: 1.02rem;
        letter-spacing: -.01em;
    }}
    .mks-flow-text {{
        color: #94A3B8;
        font-size: .9rem;
        line-height: 1.35;
    }}
    .mks-flow-arrow {{
        align-self: center;
        color: #00D2D3;
        font-size: 1.35rem;
        font-weight: 700;
        padding: 0 .1rem;
    }}
    .mks-flow-note {{
        color: #94A3B8;
        font-size: .92rem;
        margin: .55rem 0 .2rem;
        max-width: 52rem;
    }}
    .st-key-scan_start_panel {{
        border-color: rgba(0, 210, 211, 0.35) !important;
    }}
    .mks-stepnum {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 2rem;
        height: 2rem;
        padding: 0 .45rem;
        margin-right: .55rem;
        border-radius: 999px;
        background: linear-gradient(135deg, #F59E0B 0%, #D97706 100%);
        color: #0F172A;
        font-weight: 850;
        font-size: 1.05rem;
        vertical-align: middle;
        border: 1px solid #FCD34D;
        box-shadow: 0 2px 8px rgba(245, 158, 11, 0.35);
    }}
    .mks-connector {{
        display: flex;
        align-items: center;
        justify-content: center;
        height: 2rem;
        margin-top: .15rem;
        color: #00D2D3;
        font-size: 1.4rem;
        font-weight: 800;
        user-select: none;
        text-shadow: 0 0 10px rgba(0, 210, 211, 0.45);
    }}
    .mks-stepnum.mks-blink {{
        animation: mks-pulse 1.3s ease-in-out infinite;
    }}
    @keyframes mks-pulse {{
        0%, 100% {{ box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.7); transform: scale(1); }}
        50% {{ box-shadow: 0 0 0 .55rem rgba(245, 158, 11, 0); transform: scale(1.09); }}
    }}

    /* Laufender Workflow-Schritt: cyan pulsierende Nummer + leuchtender Kartenrand */
    .mks-stepnum.mks-runnum {{
        background: linear-gradient(135deg, #00D2D3, #0891B2);
        color: #F8FAFC;
        border-color: #67E8F9;
        animation: mks-run 1.2s ease-in-out infinite;
    }}
    @keyframes mks-run {{
        0%, 100% {{ box-shadow: 0 0 0 0 rgba(0, 210, 211, 0.6); transform: scale(1); }}
        50% {{ box-shadow: 0 0 0 .5rem rgba(0, 210, 211, 0); transform: scale(1.1); }}
    }}
    @keyframes mks-card-glow {{
        0%, 100% {{
            border-color: rgba(0, 210, 211, 0.7);
            box-shadow: 0 0 0 1px rgba(0, 210, 211, 0.4), 0 0 1rem rgba(0, 210, 211, 0.3);
        }}
        50% {{
            border-color: #A5F3FC;
            box-shadow: 0 0 0 2px rgba(0, 210, 211, 0.65), 0 0 1.8rem rgba(0, 210, 211, 0.5);
        }}
    }}
    /* "Läuft"-Badge: Icon rotiert, Badge pulsiert */
    @keyframes mks-spin {{ to {{ transform: rotate(360deg); }} }}
    @keyframes mks-badge-glow {{
        0%, 100% {{ box-shadow: 0 0 0 0 rgba(0, 210, 211, 0.45); }}
        50% {{ box-shadow: 0 0 0 .35rem rgba(0, 210, 211, 0); }}
    }}

    /* Action Buttons */
    button[kind="primary"], .stButton > button[type="primary"] {{
        background: linear-gradient(135deg, #00D2D3 0%, #0891B2 100%) !important;
        color: #08111E !important;
        font-weight: 750 !important;
        border: 1px solid #67E8F9 !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 14px rgba(0, 210, 211, 0.35) !important;
        transition: all 0.2s ease !important;
    }}
    button[kind="primary"]:hover, .stButton > button[type="primary"]:hover {{
        background: linear-gradient(135deg, #26E0E0 0%, #0E7490 100%) !important;
        box-shadow: 0 6px 20px rgba(0, 210, 211, 0.5) !important;
        transform: translateY(-1px) !important;
    }}
    button[kind="secondary"], .stButton > button[type="secondary"] {{
        background: linear-gradient(145deg, rgba(20, 35, 56, 0.8) 0%, rgba(12, 22, 36, 0.9) 100%) !important;
        backdrop-filter: blur(10px) !important;
        color: #F1F5F9 !important;
        border: 1px solid rgba(56, 189, 248, 0.22) !important;
        border-radius: 10px !important;
        transition: all 0.2s ease !important;
    }}
    button[kind="secondary"]:hover, .stButton > button[type="secondary"]:hover {{
        border-color: rgba(0, 210, 211, 0.45) !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4) !important;
        transform: translateY(-1px) !important;
    }}

    /* Urteile in KI-Berichten: EMPFEHLUNG gruen · Watchlist gelb · Ablehnung rot */
    .mks-urteil-gruen {{ color: #10B981; font-weight: 750; text-shadow: 0 0 8px rgba(16, 185, 129, 0.3); }}
    .mks-urteil-gelb {{ color: #F59E0B; font-weight: 750; text-shadow: 0 0 8px rgba(245, 158, 11, 0.3); }}
    .mks-urteil-rot {{ color: #F43F5E; font-weight: 750; text-shadow: 0 0 8px rgba(244, 63, 94, 0.3); }}

    [data-testid="stBottomBlockContainer"] {{
        background: rgba(8, 14, 26, 0.92) !important;
        backdrop-filter: blur(16px) !important;
        border-top: 1px solid rgba(39, 62, 91, 0.7) !important;
    }}
    @media(max-width:720px) {{
        .mks-flow-arrow {{ display: none; }}
        .mks-connector {{ display: none; }}
        .mks-flow-step {{ flex: 1 1 100%; }}
    }}
    [role="dialog"] {{
        border: 1px solid rgba(56, 189, 248, 0.3);
        background: #0E1A2C !important;
    }}
    @media(max-width:640px) {{
        .st-key-page_hero {{ padding: 1.25rem; background-size: cover, auto 100%; }}
        .st-key-page_hero h1 {{ font-size: 1.8rem; }}
    }}
    @media(prefers-reduced-motion:reduce) {{
        .stApp * {{ scroll-behavior: auto !important; }}
        .mks-stepnum.mks-blink {{ animation: none; }}
        .mks-stepnum.mks-runnum, [class*="st-key-workflow_"] {{ animation: none !important; }}
        [class*="st-key-workflow_"] [data-testid="stBadge"],
        [class*="st-key-workflow_"] [data-testid="stIconMaterial"],
        [class*="st-key-workflow_"] [data-testid="stBadge"] svg {{ animation: none !important; }}
    }}
    </style>"""


def apply_theme() -> None:
    st.html(_stylesheet())


# --------------------------------------------------------------- Urteile
# KI-Berichte nennen Urteile als Woerter (EMPFEHLUNG | WATCHLIST | ABLEHNUNG,
# Gross-/Kleinschreibung variabel). Beim Rendern werden sie sicher in farbige
# Spans verpackt: Erst HTML escapen, dann eigene Spans einsetzen.
_URTEIL_FARBE = {"empfehlung": "mks-urteil-gruen", "ablehnung": "mks-urteil-rot",
                 "watchlist": "mks-urteil-gelb"}
_URTEIL_WORT = re.compile(r"\b(empfehlung|ablehnung|watchlist)\b", re.I)
_URTEIL_AM_ANFANG = re.compile(
    r"^\s*(?:\*\*)?\s*(?:[⛔🔴🟡🟢]\s*)?(empfehlung|ablehnung|watchlist)\b", re.I)
_URTEIL_GROSS = re.compile(r"\b(EMPFEHLUNG|ABLEHNUNG|WATCHLIST)\b")


def _urteil_span(klasse: str, inhalt: str) -> str:
    return f'<span class="{klasse}">{inhalt}</span>'


def urteile_farbig(text: str) -> str:
    """Faerbt Urteils-Schluesselwoerter in KI-Markdown.

    - Tabellenzellen, die mit einem Urteil beginnen: die ganze Zelle faerben
      ("EMPFEHLUNG / Ertragstraeger" komplett gruen+fett).
    - Sonst im Fliesstext nur das Urteils-Wort selbst (GROSSCHREIBUNG, um
      Prosa wie "keine Empfehlung" nicht anzufaerben).
    HTML im Eingabetext wird zuerst escaped (keine Injektion via LLM-Text).
    """
    if not text:
        return text
    escaped = html.escape(text)
    out: list[str] = []
    for line in escaped.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and s.count("|") >= 2:
            cells = line.split("|")
            for i, cell in enumerate(cells):
                if not cell.strip():
                    continue
                start = _URTEIL_AM_ANFANG.search(cell)
                if start:
                    klasse = _URTEIL_FARBE[start.group(1).lower()]
                    cells[i] = _urteil_span(klasse, cell)
                else:
                    m = _URTEIL_WORT.search(cell)
                    if m:
                        cells[i] = _urteil_span(_URTEIL_FARBE[m.group(1).lower()], cell)
            out.append("|".join(cells))
        else:
            out.append(_URTEIL_GROSS.sub(
                lambda m: _urteil_span(_URTEIL_FARBE[m.group(0).lower()], m.group(0)),
                line))
    return "\n".join(out)


def page_header(eyebrow: str, title: str, description: str, *, image_path: str | None = None) -> None:
    with st.container(key="page_hero", gap="xsmall"):
        if image_path and Path(image_path).exists():
            c_text, c_img = st.columns([1.55, 1.45], gap="medium", vertical_alignment="center")
            with c_text:
                st.caption(f"✦ {eyebrow.upper()}")
                st.title(title)
                st.markdown(description)
            with c_img:
                st.image(str(image_path), use_container_width=True)
        else:
            st.caption(f"✦ {eyebrow.upper()}")
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
