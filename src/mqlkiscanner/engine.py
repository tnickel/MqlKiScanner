# -*- coding: utf-8 -*-
"""Kern-Engine: laedt einen Trade-Export und faehrt die komplette
Forensik-Batterie darueber (Phase 1, doc/04_roadmap.md).

Regel (AGENTS.md Design 1): Diese Engine rechnet ALLE Zahlen. Das LLM
bekommt nur das fertige Befund-JSON (engine.analyze -> dict/JSON).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import compare, parser, stats
from .forensics import baskets, drawdown, exposure, martingale, news, stops


def analyze(path: str, stress_move: float | None = None) -> dict:
    """Vollstaendige Analyse eines Trade-Exports -> Befund-Dictionary."""
    parsed = parser.load_export(path)
    report = {
        "source": str(path),
        "source_format": parsed.source_format,
        "n_pendings": len(parsed.pendings),
        "n_balances": len(parsed.balances),
        "stats": stats.compute(parsed),
        "forensics": {
            "martingale": martingale.run(parsed),
            "exposure": exposure.run(parsed, stress_move=stress_move),
            "stops": stops.run(parsed),
            "drawdown": drawdown.run(parsed),
            "baskets": baskets.run(parsed),
            "news": news.run(parsed),
        },
    }
    return report


def compare_twin(mt4_path: str, mt5_path: str, since=None) -> dict:
    """MT4/MT5-Zwillingscheck (z. B. Gold Spike #2349227 vs. #2375480)."""
    return compare.run(parser.load_export(mt4_path), parser.load_export(mt5_path), since=since)


def analyze_to_json(path: str, out_path: str | None = None, stress_move: float | None = None) -> str:
    report = analyze(path, stress_move=stress_move)
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
    return text
