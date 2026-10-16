"""The finisher must not stop when existing study rows improve."""
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('finisher_test_module',Path(__file__).parents[1]/'scripts'/'finisher_studien.py')
finisher=importlib.util.module_from_spec(spec)
spec.loader.exec_module(finisher)


def study(dd=None,coverage=0,valid=False,sha='same',**extra):
    return {'trades_sha':sha,'report':{'equity_dd_pct_raw':dd,'abdeckung_pct_raw':coverage,'verlaesslich':valid,**extra}}


def test_existing_rows_improved_is_progress_without_row_count_change():
    before={1:study(),2:study(10,80)}
    after={1:study(10,100,True),2:study(11,90)}
    assert len(before)==len(after)
    assert finisher.studien_verbessert(before,after)==2


def test_rewritten_failure_is_not_progress():
    assert finisher.studien_verbessert({1:study()},{1:study(grund='gleicher Fehler')})==0


def test_missing_measurement_or_history_changes_are_progress():
    assert finisher.studien_verbessert({1:study()},{1:study(0,100),2:study()})==2
    assert finisher.studien_verbessert({1:study(10,95,True)},{1:study(10,95,True,sha='new')})==1


def test_rounding_does_not_hide_coverage_improvement():
    assert finisher.studien_verbessert({1:study(10,94.96)},{1:study(10,95.03,True)})==1
