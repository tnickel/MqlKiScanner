"""Feed mechanics preserve the distinct account and no-flow-model policies."""
import pytest

from mqlkiscanner.forensics import feed_auswahl as feeds


class Provider:
    def __init__(self, sources):
        self.sources = sources
        self.terminal_idx = 0
        self.calls = []
        self.resets = 0
        self.terminal_herkunft = {}

    @property
    def terminal_pfad(self):
        return f"source-{self.terminal_idx}"

    def hat_weiteren_terminal(self):
        return self.terminal_idx < len(self.sources) - 1

    def wechsle_terminal(self):
        self.terminal_idx += 1
        return True, "connected"

    def zurueck_zum_ersten_terminal(self):
        self.terminal_idx = 0
        self.resets += 1
        return True, "reset"

    def hole_h1(self, symbol):
        self.calls.append((self.terminal_idx, symbol))
        value = self.sources[self.terminal_idx].get(symbol)
        if isinstance(value, Exception):
            raise value
        if value:
            self.terminal_herkunft[symbol] = self.terminal_pfad
        return value


def test_symbol_supplement_keeps_existing_series_and_uses_later_sources_in_order():
    original = [{"time": 1, "close": 10}]
    added = [{"time": 3, "close": 30}]
    provider = Provider([{}, {"A": [{"time": 2, "close": 20}]}, {"B": added}, {"B": ["unused"]}])
    bars = {"A": original}
    missing = feeds.ergaenze_fehlende_symbole(provider, bars, ["B"], provider.hole_h1)
    assert missing == [] and bars == {"A": original, "B": added}
    assert bars["A"] is original and bars["B"] is added
    assert provider.calls == [(1, "B"), (2, "B")]
    assert provider.terminal_idx == 0 and provider.resets == 1
    assert provider.terminal_herkunft == {"B": "source-2"}


@pytest.mark.parametrize("reset_fails", [False, True])
def test_read_exception_resets_selected_terminal_without_masking_original(reset_fails):
    original = ValueError("bad bars")
    provider = Provider([{}, {"B": original}])
    if reset_fails:
        def reset():
            provider.resets += 1
            raise RuntimeError("reset broke")
        provider.zurueck_zum_ersten_terminal = reset
    with pytest.raises(ValueError) as caught:
        feeds.ergaenze_fehlende_symbole(provider, {}, ["B"], provider.hole_h1)
    assert caught.value is original and provider.resets == 1
    if not reset_fails:
        assert provider.terminal_idx == 0


def test_symbol_fallback_stops_after_failed_connection_without_reading_third_source():
    provider = Provider([{}, {}, {"B": [1]}])
    def failed_switch():
        provider.terminal_idx += 1
        return False, "connection failed"
    provider.wechsle_terminal = failed_switch
    assert feeds.ergaenze_fehlende_symbole(provider, {}, ["B"], provider.hole_h1) == ["B"]
    assert provider.calls == [] and provider.resets == 1


def test_whole_feed_iteration_can_continue_past_failed_connection_and_detect_cycles():
    provider = Provider([{}, {}, {}])
    provider.hat_weiteren_terminal = lambda: True
    switches = iter([(1, False), (2, True), (0, True)])
    def switch():
        provider.terminal_idx, ok = next(switches)
        return ok, "connected" if ok else "failed"
    provider.wechsle_terminal = switch
    events = []
    indices = [p.terminal_idx for p in feeds.iteriere_weitere_feeds(
        provider, weiter_nach_verbindungsfehler=True, meldung=events.append)]
    assert indices == [2]
    assert [item["status"] for item in events] == ["verbindung_fehlgeschlagen", "kein_feed_fortschritt"]


def test_single_feed_adapter_does_not_expose_lifecycle_or_switching():
    provider = Provider([{"A": [1]}])
    one = feeds.Einzelfeed(provider)
    assert one.hole_h1("A") == [1]
    assert one.terminal_pfad == "source-0" and one.terminal_herkunft == {"A": "source-0"}
    for name in ("hat_weiteren_terminal", "wechsle_terminal", "zurueck_zum_ersten_terminal", "starten", "beenden"):
        assert not hasattr(one, name)
    assert feeds.ergaenze_fehlende_symbole(one, {}, ["B"], one.hole_h1) == ["B"]
    assert provider.resets == 0


def test_account_acceptance_does_not_weaken_stricter_model_completeness():
    report = dict(status="ok", verlaesslich=True, equity_dd_pct_raw=12,
                  abdeckung_pct_raw=99.0, trades_mit_kurs_und_kontrakt=2)
    assert feeds.ausreichend(report)
    assert not feeds.ausreichend(report, modus="modell", trades_n=2)
    report["abdeckung_pct_raw"] = 100
    assert feeds.ausreichend(report, modus="modell", trades_n=2)
    report["teilmessung"] = True
    assert feeds.ausreichend(report)  # Existing study policy, independent of model acceptance.
    assert not feeds.ausreichend(report, modus="modell", trades_n=2)


@pytest.mark.parametrize("dd", [None, True, -1, float("nan"), float("inf"), 10 ** 999])
def test_account_reliability_flag_cannot_hide_unmeasurable_dd(dd):
    assert not feeds.ausreichend(dict(verlaesslich=True, equity_dd_pct_raw=dd, abdeckung_pct_raw=100))


def test_identical_quality_keeps_first_provider_and_policies_keep_original_tiebreaks():
    first = dict(verlaesslich=False, equity_dd_pct_raw=20, abdeckung_pct_raw=90,
                 trades_mit_kurs_und_kontrakt=3)
    second = dict(first, equity_dd_pct_raw=10, trades_mit_kurs_und_kontrakt=4)
    assert feeds.qualitaet(first) > feeds.qualitaet(second)
    assert feeds.qualitaet(first, modus="modell", trades_n=5) < feeds.qualitaet(second, modus="modell", trades_n=5)
    assert not feeds.qualitaet(first) > feeds.qualitaet(first)
