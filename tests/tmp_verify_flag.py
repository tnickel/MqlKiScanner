# -*- coding: utf-8 -*-
"""TEMPORAER — verifiziert den Flag-Tippfehler (ui_tree.py:936)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from streamlit.testing.v1 import AppTest  # noqa: E402
from mqlkiscanner.agenten import tageskette  # noqa: E402

# Echter Ablauf bis auf den Thread-Start: st.rerun() in
# agenten_komplett_ausfuehren wird NICHT entschärft.
aufrufe = {"n": 0}


def _fake_start(**kwargs):
    aufrufe["n"] += 1
    return {"gestartet": False, "grund": "kein Thread"}


tageskette.starte_komplettlauf = _fake_start

at = AppTest.from_file(str(ROOT / "app_pages" / "agenten.py"),
                       default_timeout=25)
try:
    at.run()
    print("erster Lauf ok, exception:", bool(at.exception))
    at.session_state["agenten_komplett_lauf"] = True
    at.run()
    print("nach Flag: exception:", [str(e) for e in at.exception])
    print("aufrufe von starte_komplettlauf:", aufrufe["n"])
    print("flag noch gesetzt:", at.session_state.get("agenten_komplett_lauf"))
except Exception as exc:  # Timeout/Endlosschleife
    print("EXCEPTION/ABBRUCH:", type(exc).__name__, str(exc)[:400])
    print("aufrufe:", aufrufe["n"])
