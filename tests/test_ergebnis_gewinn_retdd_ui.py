"""Eigene Monatsrendite und gemessene Equity bleiben in der UI unterscheidbar."""
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT
from mqlkiscanner import app_ui, config, pipeline


def _result(signal_id, dd, *, gain=6.0, name=None, schranke=False):
    return pipeline.ScanResult(
        id=signal_id, name=name or str(signal_id),
        equity_dd_rekonstruiert_pct=dd, ertrag_monat_geom_pct=gain,
        ertrag_monat_pct=99.0, trading_dd_pct=1.0, dd_equity_pct=35.0,
        retdd_monat=99.0, forensik_vorhanden=True,
        schranke_verletzt=schranke)


def test_table_serializes_colors_and_formats_without_losing_values(monkeypatch):
    config.save_settings({'schranke_eq_dd_pct': 20.0})
    captured = []
    original = app_ui.st.dataframe

    def dataframe(styled, *args, **kwargs):
        captured.append((styled, kwargs))
        return original(styled, *args, **kwargs)

    monkeypatch.setattr(app_ui.st, 'dataframe', dataframe)
    rows = [_result(1, 16.0), _result(2, 20.0), _result(3, 20.01),
            _result(4, None), _result(5, 0.0)]
    at = AppTest.from_string(
        'import streamlit as st\n'
        'from mqlkiscanner.app_ui import render_results_table\n'
        'render_results_table(st.session_state.rows)', default_timeout=30)
    at.session_state['rows'] = rows
    at.run()
    assert not at.exception
    frame = at.dataframe[0].value
    assert list(frame['Gewinn %/Monat']) == [6.0] * 5
    assert frame.loc[1, 'TrueRetDD'] == pytest.approx(0.3)
    assert frame['TrueRetDD'].isna().tolist() == [False, False, False, True, True]

    styled, options = captured[-1]
    order = options['column_order']
    # Nutzer 03.10.: die DREI Drawdown-Werte stehen direkt nebeneinander;
    # Gewinn/RetDD folgen danach, Equity-Messung nur in „Alle Kennzahlen".
    dd_pos = order.index('Max-Drawdown %')
    assert order[dd_pos:dd_pos + 3] == [
        'Max-Drawdown %', 'Trading-DD % (geschlossen)', 'Drawdown % (Plattform)']
    assert 'Equity-Messung' not in order
    assert order.index('Gewinn %/Monat') > order.index('Drawdown % (Plattform)')
    assert options['column_config']['Gewinn %/Monat']['type_config']['format'] == '%.2f%%'
    assert options['column_config']['TrueRetDD']['type_config']['format'] == '%.2f'
    assert options['selection_mode'] == 'single-row'
    # Dezente Hinterlegung: schwache rgba-Fläche + farbiger Text, fehlende
    # Messung (None) ganz ohne Stil — kein pastellfarbener Block.
    col = styled.data.columns.get_loc('Max-Drawdown %')
    styles = styled._compute().ctx
    farben = [dict(styles[(i, col)])['background-color'] if (i, col) in styles
              else None for i in range(5)]
    assert farben == ['rgba(34,197,94,0.10)', 'rgba(249,115,22,0.12)',
                      'rgba(239,68,68,0.16)', None, 'rgba(34,197,94,0.10)']
    textfarben = [dict(styles[(i, col)])['color'] if (i, col) in styles else None
                  for i in range(5)]
    assert textfarben == ['#4ade80', '#fb923c', '#f87171', None, '#4ade80']
    assert all('font-weight' not in dict(styles[(i, col)])
               for i in range(5) if (i, col) in styles)
    css = at.dataframe[0].proto.arrow_data.styler.styles
    assert all(color in css for color in
               ('rgba(34,197,94,0.10)', 'rgba(249,115,22,0.12)',
                'rgba(239,68,68,0.16)'))

    # A settings change must move the threshold without rebuilding the rows.
    config.save_settings({'schranke_eq_dd_pct': 30.0})
    at.run()
    assert not at.exception
    styled, _ = captured[-1]
    assert dict(styled._compute().ctx[(1, col)])['background-color'] == \
        'rgba(34,197,94,0.10)'
    # Row 3 (keine Messung) bleibt über jeder Grenze ungestylt.
    assert (3, col) not in styled._compute().ctx


@pytest.mark.parametrize('dd,gain,profit_text,retdd_text', [
    (20.0, 6.0, '6.00 %', '0.30'),
    (None, 6.0, '6.00 %', '—'),
    (0.0, 6.0, '6.00 %', '—'),
    (20.0, None, '—', '—'),
])
def test_detail_uses_same_fields_without_platform_or_trading_fallback(dd, gain, profit_text, retdd_text):
    at = AppTest.from_string(
        'import streamlit as st\n'
        'from mqlkiscanner.app_ui import render_detail\n'
        'render_detail(st.session_state.result)', default_timeout=30)
    at.session_state['result'] = _result(123, dd, gain=gain)
    at.run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics['Gewinn %/Monat'] == profit_text
    assert metrics['TrueRetDD'] == retdd_text
    assert metrics['Ertrag / Monat (Plattform)'] == '99.0 %'
    if dd is None:
        assert any('Equity-DD unbelegt' in m.value for m in at.markdown)


def test_detail_does_not_signal_safe_dd_when_platform_violates_overall_gate():
    at = AppTest.from_string(
        'import streamlit as st\n'
        'from mqlkiscanner.app_ui import render_detail\n'
        'render_detail(st.session_state.result)', default_timeout=30)
    at.session_state['result'] = _result(123, 10.0, schranke=True)
    at.run()
    assert not at.exception
    assert any('Drawdown-Grenze überschritten' in m.value for m in at.markdown)
    assert not any('Equity-DD mit Puffer' in m.value for m in at.markdown)


def test_styled_table_keeps_row_selection_on_exact_snapshot(monkeypatch):
    original = app_ui.st.dataframe

    def choose_second(*args, **kwargs):
        original(*args, **kwargs)
        return SimpleNamespace(selection=SimpleNamespace(rows=[1]))

    monkeypatch.setattr(app_ui.st, 'dataframe', choose_second)
    first, second = _result(123, 10.0, name='Erster'), _result(123, 35.0, name='Zweiter')
    at = AppTest.from_string(
        'import streamlit as st\n'
        'from mqlkiscanner.app_ui import render_results_table\n'
        'selected = render_results_table(st.session_state.rows)\n'
        'st.write(selected.name)', default_timeout=30)
    at.session_state['rows'] = [first, second]
    at.run()
    assert not at.exception
    assert any(m.value == 'Zweiter' for m in at.markdown)


def test_results_page_filters_profit_and_retdd_with_the_same_rows():
    rows = [_result(123, 20.0, name='Alpha'), _result(456, 10.0, name='Beta')]
    at = AppTest.from_file(str(ROOT / 'streamlit_app.py'), default_timeout=30).run()
    at.session_state['scan_results'] = rows
    at.switch_page('app_pages/ergebnisse.py').run()
    at.selectbox(key='results_run').set_value('Aktuelle Sitzung').run()
    at.text_input(key='results_search').set_value('Alpha').run()
    assert not at.exception
    frame = at.dataframe[0].value
    assert list(frame['Name']) == ['Alpha']
    assert list(frame['Gewinn %/Monat']) == [6.0]
    assert list(frame['TrueRetDD']) == pytest.approx([0.3])
    assert any('Ertrag ÷ ECHTER Max-Drawdown' in c.value for c in at.caption)


def test_kompaktansicht_faerbt_vorbehaltliches_trueretdd_orange():
    """Gegenbeweis zum Fremd-Review 05.10. (Befund 1): Die Markerspalte ist
    in der Kompaktansicht per column_order VERSTECKT, aber das Orange der
    TrueRetDD-Zelle kommt aus dem Styler — es bleibt sichtbar. Nur bei
    einer Stil-Regression (apply-Subset falsch) würde diese Prüfung kippen."""
    rows = [pipeline.ScanResult(
        id=1, name='Vorbehalt', forensik_vorhanden=True,
        ertrag_monat_geom_pct=1.4269, cagr_jahr_pct=18.2,
        equity_dd_rekonstruiert_pct=None, equity_dd_rekon_roh_pct=13.83,
        equity_rekon_grund='Wechselgrenze')]
    at = AppTest.from_string(
        'import streamlit as st\n'
        'from mqlkiscanner.app_ui import render_results_table\n'
        'render_results_table(st.session_state.rows)', default_timeout=30)
    at.session_state['rows'] = rows
    at.run()
    assert not at.exception
    frame = at.dataframe[0].value
    assert frame.loc[0, 'TrueRetDD'] == pytest.approx(1.4269 / 13.83)
    css = at.dataframe[0].proto.arrow_data.styler.styles
    assert 'rgba(249,115,22,0.12)' in css and '#fb923c' in css
