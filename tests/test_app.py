# -*- coding: utf-8 -*-
"""Headless-Tests der Streamlit-App (st.testing.v1.AppTest).

Lauf:  python -m pytest tests/test_app.py -q   (oder direkt python tests/test_app.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from streamlit.testing.v1 import AppTest  # noqa: E402


def _run_main(timeout: int = 60) -> AppTest:
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=timeout)
    at.run()
    return at


def test_app_boots_without_exception():
    at = _run_main()
    assert not at.exception, at.exception
    assert at.sidebar.markdown, "Sidebar-Status fehlt"


def test_scan_page_renders_steps():
    at = _run_main()
    assert not at.exception
    body = "\n".join(md.value for md in at.markdown)
    assert "Listen lesen" in body and "LLM-Auswertung" in body


def test_verification_button_loads_raw_data():
    """Verifikations-Button: data/raw durch die Engine -> Ergebnisse im State."""
    at = _run_main(timeout=180)
    assert not at.exception
    buttons = [b for b in at.button if "Verifikations-Datensätze" in (b.label or "")]
    assert buttons, "Verifikations-Button nicht gefunden"
    buttons[0].click()
    at.run()
    assert not at.exception, at.exception
    results = at.session_state["scan_results"]
    assert len(results) == 9, f"erwartet 9 Datensaetze, bekommen {len(results)}"
    ampeln = [r.ampel for r in results]
    assert "🟢" in ampeln or "🟡" in ampeln, f"keine bewerteten Signale: {ampeln}"


def test_ergebnisse_page_renders_table_after_verification():
    at = _run_main(timeout=180)
    buttons = [b for b in at.button if "Verifikations-Datensätze" in (b.label or "")]
    buttons[0].click()
    at.run()
    assert not at.exception
    # Seite wechseln: Navigation via query? AppTest unterstuetzt page switching
    # ueber st.navigation nicht direkt — daher Seite direkt ausfuehren:
    at2 = AppTest.from_file(str(ROOT / "app_pages" / "ergebnisse.py"), default_timeout=60)
    at2.session_state["scan_results"] = at.session_state["scan_results"]
    at2.run()
    assert not at2.exception, at2.exception
    assert at2.dataframe, "Ergebnistabelle fehlt"


def test_admin_page_renders_and_masks_key():
    at = AppTest.from_file(str(ROOT / "app_pages" / "admin.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    # Der konfigurierte Key darf nie im Klartext im Frontend erscheinen
    from mqlkiscanner import secrets_store
    key = secrets_store.get_secret("glm_api_key")
    rendered = "\n".join([str(x) for x in at.success] + [md.value for md in at.markdown])
    assert not key or key not in rendered, "Key im Klartext gerendert!"
    masked = [s.value for s in at.success if "maskiert" in s.value]
    assert masked, "Maskierter-Key-Status fehlt"


if __name__ == "__main__":
    fails = 0
    for fn in (test_app_boots_without_exception, test_scan_page_renders_steps,
               test_verification_button_loads_raw_data,
               test_ergebnisse_page_renders_table_after_verification,
               test_admin_page_renders_and_masks_key):
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as exc:
            fails += 1
            print(f"FAIL  {fn.__name__}: {exc}")
    sys.exit(1 if fails else 0)
