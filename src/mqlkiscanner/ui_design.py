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
        border: 1.6px solid rgba(56, 189, 248, 0.28) !important;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.45), inset 0 1px 1px 0 rgba(255, 255, 255, 0.05) !important;
        border-radius: 14px !important;
        transition: border-color 0.25s ease, box-shadow 0.25s ease;
    }}
    [data-testid="stVerticalBlockBorderWrapper"] > div:hover {{
        border-color: rgba(56, 189, 248, 0.46) !important;
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

    /* Lauf-Zentrale: Statusleiste (Aktivität + Uhr) */
    .mks-strip {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
        margin: .1rem 0 .6rem;
    }}
    .mks-strip__main {{
        display: flex;
        align-items: center;
        gap: .65rem;
        min-width: 0;
    }}
    .mks-strip__text {{ min-width: 0; }}
    .mks-strip__text b {{ font-size: 1.04rem; color: #F1F5F9; }}
    .mks-strip__text small {{
        display: block;
        color: #94A3B8;
        font-size: .85rem;
        margin-top: .12rem;
        line-height: 1.35;
    }}
    .mks-strip__side {{
        display: flex;
        align-items: center;
        gap: .5rem;
        flex: 0 0 auto;
    }}
    .mks-dot {{
        flex: 0 0 auto;
        width: .8rem;
        height: .8rem;
        border-radius: 50%;
        background: #64748B;
        box-shadow: 0 0 0 3px rgba(100, 116, 139, .16);
    }}
    .mks-dot--running {{
        background: #00D2D3;
        box-shadow: 0 0 0 3px rgba(0, 210, 211, .18), 0 0 12px rgba(0, 210, 211, .6);
        animation: mks-dot-blink 1.4s ease-in-out infinite;
    }}
    .mks-dot--complete {{ background: #10B981; box-shadow: 0 0 0 3px rgba(16, 185, 129, .18); }}
    .mks-dot--warning {{ background: #F59E0B; box-shadow: 0 0 0 3px rgba(245, 158, 11, .18); }}
    .mks-dot--error {{ background: #F43F5E; box-shadow: 0 0 0 3px rgba(244, 63, 94, .18); }}
    @keyframes mks-dot-blink {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: .4; }} }}
    .mks-clock {{
        flex: 0 0 auto;
        font-variant-numeric: tabular-nums;
        font-weight: 700;
        color: #67E8F9;
        background: rgba(0, 210, 211, .1);
        border: 1px solid rgba(0, 210, 211, .3);
        padding: .16rem .62rem;
        border-radius: 99px;
        font-size: .85rem;
        white-space: nowrap;
    }}
    /* Stoppuhr der aktuellen Meldung: amber, zählt hoch bis zur nächsten Meldung */
    .mks-clock--wait {{
        color: #FCD34D;
        background: rgba(245, 158, 11, .12);
        border-color: rgba(245, 158, 11, .38);
    }}

    /* Stations-Stepper: Knoten + Fortschrittsschiene */
    .mks-stepper {{
        --mks-fill: 0%;
        position: relative;
        display: flex;
        gap: .5rem;
        padding: .3rem .2rem .15rem;
    }}
    .mks-rail {{
        position: absolute;
        top: 1.29rem;
        left: 10%;
        right: 10%;
        height: 5px;
        border-radius: 99px;
        background: rgba(148, 163, 184, .22);
        overflow: hidden;
    }}
    .mks-rail i {{
        display: block;
        height: 100%;
        width: var(--mks-fill);
        border-radius: inherit;
        background: linear-gradient(90deg, #0891B2, #22D3EE 70%, #67E8F9);
        box-shadow: 0 0 12px rgba(34, 211, 238, .75);
        transition: width .6s ease;
    }}
    .mks-step {{
        flex: 1 1 0;
        min-width: 0;
        display: flex;
        flex-direction: column;
        align-items: center;
        position: relative;
        z-index: 1;
    }}
    .mks-step-body {{
        display: flex;
        flex-direction: column;
        align-items: center;
        min-width: 0;
        flex: 1 1 auto;
    }}
    .mks-node {{
        width: 2.3rem;
        height: 2.3rem;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        font-size: 1rem;
        position: relative;
        border: 1px solid rgba(148, 163, 184, .28);
        background: #121E31;
        color: #64748B;
    }}
    .mks-step--running .mks-node {{
        background: linear-gradient(135deg, #00D2D3, #0891B2);
        color: #04262B;
        border-color: #67E8F9;
        box-shadow: 0 0 0 4px rgba(0, 210, 211, .15), 0 0 18px rgba(0, 210, 211, .45);
    }}
    .mks-step--running .mks-node::before {{
        content: "";
        position: absolute;
        inset: -7px;
        border-radius: 50%;
        border: 2px dashed rgba(103, 232, 249, .65);
        animation: mks-spin 3.2s linear infinite;
    }}
    .mks-step--complete .mks-node {{
        background: linear-gradient(135deg, #10B981, #059669);
        color: #03271C;
        border-color: #6EE7B7;
        box-shadow: 0 0 12px rgba(16, 185, 129, .35);
    }}
    .mks-step--warning .mks-node {{
        background: linear-gradient(135deg, #F59E0B, #D97706);
        color: #2B1A02;
        border-color: #FCD34D;
        box-shadow: 0 0 12px rgba(245, 158, 11, .35);
    }}
    .mks-step--error .mks-node {{
        background: linear-gradient(135deg, #F43F5E, #E11D48);
        color: #2B040D;
        border-color: #FDA4AF;
        box-shadow: 0 0 12px rgba(244, 63, 94, .35);
    }}
    .mks-step--skipped .mks-node {{ opacity: .55; }}
    .mks-step--idle-hint .mks-node {{ animation: mks-node-hint 2s ease-in-out infinite; }}
    @keyframes mks-node-hint {{
        0%, 100% {{ box-shadow: 0 0 0 0 rgba(245, 158, 11, .5); }}
        50% {{ box-shadow: 0 0 0 .5rem rgba(245, 158, 11, 0); }}
    }}
    .mks-step-title {{
        margin-top: .6rem;
        font-weight: 700;
        font-size: .95rem;
        color: #CBD5E1;
        max-width: 100%;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    .mks-step--running .mks-step-title {{ color: #67E8F9; }}
    .mks-step--complete .mks-step-title {{ color: #A7F3D0; }}
    .mks-step--warning .mks-step-title {{ color: #FDE68A; }}
    .mks-step--error .mks-step-title {{ color: #FDA4AF; }}
    .mks-step-meta {{
        font-size: .78rem;
        line-height: 1.3;
        color: #8CA0B8;
        max-width: 100%;
        margin-top: .12rem;
        min-height: 1.02em;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }}
    .mks-step--running .mks-step-meta {{ color: #A5F3FC; }}
    .mks-mini {{
        width: 100%;
        max-width: 7.5rem;
        height: 4px;
        margin-top: .5rem;
        border-radius: 99px;
        background: rgba(148, 163, 184, .18);
        overflow: hidden;
    }}
    .mks-mini i {{
        display: block;
        height: 100%;
        border-radius: inherit;
        background: linear-gradient(90deg, #0891B2, #22D3EE);
        box-shadow: 0 0 8px rgba(34, 211, 238, .5);
        transition: width .5s ease;
    }}

    /* Letzte Meldungen: kompakter Status-Feed statt Logfile-Wand */
    .mks-feed {{
        margin-top: 1rem;
        border-left: 2px solid rgba(0, 210, 211, .35);
        padding: .12rem 0 .12rem .8rem;
        display: flex;
        flex-direction: column;
        gap: .2rem;
    }}
    .mks-feed__line {{
        font-size: .8rem;
        color: #7C8DA6;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    .mks-feed__line::before {{ content: "· "; color: #00D2D3; font-weight: 800; }}
    @keyframes mks-spin {{ to {{ transform: rotate(360deg); }} }}

    .st-key-scan_control_panel > div {{
        border-color: rgba(0, 210, 211, 0.42) !important;
    }}

    /* Lauf-Modus: Hintergrundbeleuchtung für das ganze Zentrale-Panel.
       Die Selektoren injiziert das Live-Fragment nur während ein Workflow
       läuft (status=running); die Keyframes stehen immer bereit. */
    @keyframes mks-backlight {{
        0%, 100% {{ opacity: 0.5; }}
        50% {{ opacity: 1; }}
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
        .mks-stepper {{ flex-direction: column; gap: 1.05rem; }}
        .mks-rail {{ left: 1.03rem; right: auto; top: 1.45rem; bottom: 1.45rem; width: 4px; height: auto; }}
        .mks-rail i {{ width: 100%; height: var(--mks-fill); transition: height .6s ease; }}
        .mks-step {{ flex-direction: row; align-items: flex-start; gap: .85rem; }}
        .mks-step-body {{ align-items: flex-start; }}
        .mks-step-title {{ margin-top: .1rem; }}
        .mks-mini {{ max-width: 11rem; }}
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
        .mks-dot--running, .mks-step--idle-hint .mks-node,
        .mks-step--running .mks-node::before {{ animation: none !important; }}
        .mks-rail i, .mks-mini i {{ transition: none !important; }}
    }}
    </style>"""


def apply_theme() -> None:
    st.html(_stylesheet())


# ------------------------------------------------------- Workflow-Stepper
# Reine HTML/CSS-Fortschrittsanzeige: Knoten je Station (Zahl / Häkchen /
# Warndreieck), Fortschrittsschiene dahinter, Mini-Balken im laufenden Schritt.
_NODE_MARK = {
    "complete": '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" '
                'stroke="currentColor" stroke-width="3.4" stroke-linecap="round" '
                'stroke-linejoin="round" aria-hidden="true">'
                '<path d="M4.5 12.8l4.8 4.7L19.5 6.8"/></svg>',
    "warning": "!",
    "error": '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" '
             'stroke="currentColor" stroke-width="3.2" stroke-linecap="round" '
             'aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    "skipped": "–",
}


def workflow_stepper_html(steps: list[dict], overall: float = 0.0) -> str:
    """HTML für den Stations-Stepper.

    steps: [{nr, title, status, meta, frac}] — frac (0..1) steuert den
    Mini-Balken und wird nur bei laufenden Stationen angezeigt; overall
    (0..1) füllt die Schiene zwischen den Knoten proportional auf.
    """
    n = len(steps)
    fill = max(0.0, min(1.0, (overall * n - 0.5) / (n - 1))) if n > 1 else 0.0
    parts = [
        f'<div class="mks-stepper" style="--mks-fill:{fill * 100:.1f}%" '
        f'role="list" aria-label="Workflow-Fortschritt">',
        '<div class="mks-rail" aria-hidden="true"><i></i></div>',
    ]
    for s in steps:
        status = s.get("status", "pending")
        hint = " mks-step--idle-hint" if s.get("hint") else ""
        mark = _NODE_MARK.get(status, str(s["nr"]))
        title = html.escape(str(s["title"]))
        meta = html.escape(str(s.get("meta") or ""))
        aria = html.escape(f"Station {s['nr']} von {n}: {s.get('label', status)}")
        mini = ""
        if status == "running" and s.get("frac") is not None:
            mini = (f'<div class="mks-mini" aria-hidden="true">'
                    f'<i style="width:{s["frac"] * 100:.0f}%"></i></div>')
        parts.append(
            f'<div class="mks-step mks-step--{status}{hint}" role="listitem">'
            f'<div class="mks-node" role="img" aria-label="{aria}">{mark}</div>'
            f'<div class="mks-step-body">'
            f'<div class="mks-step-title">{title}</div>'
            f'<div class="mks-step-meta">{meta}</div>{mini}</div></div>')
    parts.append("</div>")
    return "".join(parts)


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
                st.image(str(image_path), width="stretch")
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
