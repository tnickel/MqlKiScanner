# -*- coding: utf-8 -*-
"""Crawler: MQL5-Signal-Listen (MT4 + MT5) -> Kandidaten.

Quelle: https://www.mql5.com/en/signals/{mt4|mt5}(+ /pageN), ohne Login.
Seitenstruktur (Stand 09/2026, kalibriert gegen Live-HTML): Signalkarten
`div.signal-card` mit data-Attributen (id, name, price, weeks, balance)
sowie growth / subscribers / rating / author / algo-share.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import MQL5_BASE
from . import signal_stats
from .session import Mql5Session

_NUM = re.compile(r"[+-]?[\d.,]+")
CARD_SEL = "div.signal-card"


def _num(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = text.replace("\xa0", " ").replace(" ", "").replace("\u2212", "-")
    # Tausender-Kommas (1,403 / 1,403.03) entfernen — MQL5-EN-Karten
    cleaned = re.sub(r",(?=\d{3}(\D|$))", "", cleaned)
    m = _NUM.search(cleaned)
    if not m:
        return None
    raw = m.group(0).rstrip(".")
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_card(card) -> dict | None:
    a = card.find("a", class_="signal-card__wrapper")
    if a is None:
        return None
    href = a.get("href", "")
    m = re.search(r"/signals/(\d+)", href)
    if not m:
        return None
    signal_id = int(m.group(1))

    copy_block = card.find(class_="signal-card__copy") or {}
    title = card.find(class_="signal-card__title-wrapper")
    growth = card.find(class_="signal-card__growth-value")
    author = card.find(class_="signal-card__author__item")
    rating = card.find(class_="g-rating__info")
    subs = card.find(class_="signal-card__subscribers-value")
    rel = card.find(class_=re.compile(r"risk-bars-rel(\d+)"))
    algo = card.find(class_=re.compile(r"risk-bars-algo"))

    rel_level = None
    if rel is not None:
        classes = " ".join(rel.get("class", []))
        rm = re.search(r"risk-bars-rel(\d+)", classes)
        if rm:
            rel_level = int(rm.group(1))

    algo_pct = None
    if algo is not None:
        algo_pct = _num(algo.next_sibling.string if getattr(algo, "next_sibling", None) is not None and algo.next_sibling.string
                        else algo.parent.get_text(" ", strip=True))

    rating_value = None
    reviews = None
    if rating is not None:
        rm = re.match(r"\s*([\d.]+)\s*\((\d+)\)", rating.get_text())
        if rm:
            rating_value = float(rm.group(1))
            reviews = int(rm.group(2))

    growth_val = _num(growth.get_text()) if growth is not None else None
    if growth_val is not None and "%" not in (growth.get_text() or ""):
        growth_val = None

    mt = str(copy_block.get("data-mt") or "")
    return {
        "id": signal_id,
        "name": (copy_block.get("data-name") or (title.get_text(strip=True) if title else "")) or "",
        "platform": f"MT{mt}" if mt in ("4", "5") else "",
        "abo_preis_usd": _num(copy_block.get("data-price") or ""),
        "konto_balance": copy_block.get("data-balance") or "",
        "wochen": _num(copy_block.get("data-weeks")),
        "abonnenten": _num(subs.get_text()) if subs is not None else None,
        "growth_pct": growth_val,
        "autor": author.get_text(strip=True) if author is not None else "",
        "rating": rating_value,
        "reviews": reviews,
        "reliability_level": rel_level,
        "algo_trading_pct": algo_pct,
        "url": urljoin(MQL5_BASE, f"/en/signals/{signal_id}"),
    }


def parse_list_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for card in soup.select(CARD_SEL):
        item = _parse_card(card)
        if item and item["id"] not in {o["id"] for o in out}:
            out.append(item)
    return out


def crawl_lists(session: Mql5Session, seiten_pro_liste: int = 2,
                on_progress=None) -> list[dict]:
    """Laedt die Signal-Listen MT4+MT5 (je `seiten_pro_liste` Seiten).

    Rate-Limit liegt in session.limiter; zusaetzlich 1 s Pause pro Seite.
    on_progress(fertig, gesamt, text) fuer die GUI-Fortschrittsanzeige.
    """
    lists = [("mt5", "https://www.mql5.com/en/signals/mt5"),
             ("mt4", "https://www.mql5.com/en/signals/mt4")]
    jobs = [(plattform, base if page == 1 else f"{base}/page{page}")
            for plattform, base in lists
            for page in range(1, max(1, seiten_pro_liste) + 1)]
    signals: dict[int, dict] = {}
    for i, (plattform, url) in enumerate(jobs):
        r = session.get(url, extra_pause_s=1.0)
        page_signals = parse_list_html(r.text)
        for s in page_signals:
            if not s["platform"]:
                s["platform"] = plattform.upper()
            signals[s["id"]] = s
        if on_progress:
            page_no = url.rsplit("page", 1)[-1] or "1"
            on_progress(i + 1, len(jobs),
                        f"{plattform.upper()} Seite {page_no}: "
                        f"{len(page_signals)} Signale (gesamt {len(signals)})")
    return sorted(signals.values(), key=lambda s: -(s.get("abonnenten") or 0))


_PREIS_RE = re.compile(r"([\d.,]+)\s*USD\s+per\s+month", re.IGNORECASE)
_NAME_RE = re.compile(r"Copy trades of the (.+?) trading signal", re.IGNORECASE)
_AUTOR_RE = re.compile(r"per\s+month\s+[-–]\s+(.+?)\s*$", re.IGNORECASE)
_MT_RE = re.compile(r"MetaTrader\s*([45])", re.IGNORECASE)


def fetch_signal_overview(session: Mql5Session, signal_id: int) -> dict:
    """Einzelsignal von der Detailseite — fuer Fix-IDs ausserhalb der Top-Listen.

    Liefert die Kandidatenform von parse_list_html (id, name, platform,
    wochen, abonnenten …). Die Kennzahlen holt die Forensik-Station spaeter
    ohnehin frisch von derselben Seite; hier genuegt das Geruest fuer
    Anzeige und Persistenz. Plattform entscheidet den Export-Pfad
    (MT4=/history, MT5=/positions) und wird deshalb zweifach gesichert:
    data-mt-Attribut des Copy-Widgets, Fallback Seitentitel.
    """
    r = session.get(f"/en/signals/{signal_id}", extra_pause_s=1.0)
    soup = BeautifulSoup(r.text, "html.parser")
    titel = soup.title.get_text(" ", strip=True) if soup.title else ""

    mt = None
    marker = soup.find(attrs={"data-mt": re.compile(r"^[45]$")})
    if marker is not None:
        mt = marker.get("data-mt")
    if mt not in ("4", "5"):
        mt_match = _MT_RE.search(titel)
        mt = mt_match.group(1) if mt_match else None

    name_match = _NAME_RE.search(titel)
    autor_match = _AUTOR_RE.search(titel)
    preis_match = _PREIS_RE.search(titel)
    stats = signal_stats.parse_detail_html(r.text)
    return {
        "id": int(signal_id),
        "name": (name_match.group(1).strip() if name_match else "") or f"Signal {signal_id}",
        "platform": f"MT{mt}" if mt in ("4", "5") else "",
        "abo_preis_usd": _num(preis_match.group(1)) if preis_match else None,
        "konto_balance": "",
        "wochen": stats.get("weeks"),
        "abonnenten": _num(stats.get("raw", {}).get("Subscribers:", "")),
        "growth_pct": stats.get("growth_pct"),
        "autor": autor_match.group(1).strip() if autor_match else "",
        "rating": None,
        "reviews": None,
        "reliability_level": None,
        "algo_trading_pct": None,
        "url": urljoin(MQL5_BASE, f"/en/signals/{signal_id}"),
    }
