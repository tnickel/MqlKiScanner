"""Native GET-only trends remain reproducible and identity-bound."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from mqlkiscanner import abonnenten_analyse_trend as trend, db
from mqlkiscanner.abonnenten_analyse_ki import Angehalten
from mqlkiscanner.abonnenten_analyse_store import Store


AS_OF = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def point(days, count, **extra):
    return {"timestamp": (AS_OF-timedelta(days=days)).isoformat(),
            "subscribers": count, **extra}


def test_measured_absolute_and_percentage_growth_share_fixed_baselines():
    result = trend.trend_from_points([point(0, 200), point(7, 140), point(30, 100)], AS_OF)
    assert result["verified"] and result["status"] == "ok"
    assert result["delta_7"] == 60 and result["delta_7_pct"] == pytest.approx(60/140*100)
    assert result["delta_30"] == result["delta_30_pct"] == 100
    assert result["aktuell"] == 200 and result["basis_7"] == 140
    assert result["messabstand_7_tage"] == 7 and result["messalter_tage"] == 0


def test_zero_baseline_keeps_absolute_change_and_unknown_percentage():
    result = trend.trend_from_points([point(0, 10), point(7, 0), point(30, 0)], AS_OF)
    assert result["verified"] and result["delta_7"] == result["delta_30"] == 10
    assert result["delta_7_pct"] is result["delta_30_pct"] is None
    assert result["status"] == "teilweise" and "null" in result["grund"]


def test_no_comparison_is_unknown_instead_of_zero_growth():
    result = trend.trend_from_points([point(0, 50), point(1, 40)], AS_OF)
    assert result["aktuell"] == 50 and result["status"] == "unbekannt"
    assert not result["verified"]
    assert result["delta_7"] is result["delta_30"] is None


def test_future_measurements_are_excluded_from_latest_and_comparison():
    result = trend.trend_from_points([point(-1, 999), point(0, 10), point(7, 5)], AS_OF)
    assert result["verified"] and result["delta_7"] == 5 and result["aktuell"] == 10
    assert result["coverage"]["zukuenftige_punkte"] == 1
    assert all(p["subscribers"] != 999 for p in result["punkte"])


def test_stale_latest_never_relabels_two_days_as_seven_day_growth():
    result = trend.trend_from_points([point(5, 20), point(7, 10), point(30, 2)], AS_OF)
    assert result["messalter_tage"] == 5
    assert not result["verified"] and result["delta_7"] is None
    assert result["delta_30"] is None


def test_tolerance_checks_both_cutoff_target_and_real_elapsed_time():
    allowed = trend.trend_from_points([point(0, 20), point(4, 10)], AS_OF)
    assert allowed["verified"] and allowed["messabstand_7_tage"] == 4
    rejected = trend.trend_from_points([point(2, 20), point(4, 10)], AS_OF)
    assert not rejected["verified"] and rejected["delta_7"] is None
    assert not trend.trend_from_points([point(0, 20), point(10.001, 10)], AS_OF)["verified"]


def test_equal_distance_baselines_choose_earlier_measurement_deterministically():
    points = [point(0, 50), point(6, 40), point(8, 30)]
    left = trend.trend_from_points(points, AS_OF)
    right = trend.trend_from_points(list(reversed(points)), AS_OF)
    assert left == right and left["basis_7"] == 30 and left["delta_7"] == 20


@pytest.mark.parametrize("claim", ["version", "quelle_version", "quellen_uid", "providerId", "signalId", "quelle"])
def test_explicit_mixed_provider_source_or_version_is_not_combined(claim):
    result = trend.trend_from_points([point(0, 20, **{claim: "A"}),
                                      point(7, 10, **{claim: "B"})], AS_OF)
    assert not result["verified"] and result["aktuell"] is None
    assert "vermischt" in result["grund"]


def test_identical_duplicates_are_deduplicated_and_counter_conflicts_rejected():
    points = [point(0, 20), point(7, 10)]
    okay = trend.trend_from_points([*points, deepcopy(points[1])], AS_OF)
    assert okay["verified"] and okay["coverage"]["doppelte_punkte"] == 1
    bad = trend.trend_from_points([*points, point(7, 11)], AS_OF)
    assert not bad["verified"] and bad["delta_7"] is None
    assert "Widersprüchliche" in bad["grund"]


@pytest.mark.parametrize("bad", [point(3, True), point(3, -1), point(3, "10"),
                                 {"timestamp": "not-a-date", "subscribers": 5}, None])
def test_malformed_history_never_receives_verified_score_input(bad):
    result = trend.trend_from_points([point(0, 20), point(7, 10), bad], AS_OF)
    assert result["delta_7"] == 10 and not result["verified"]
    assert result["coverage"]["ungueltige_punkte"] == 1


def test_native_unix_millisecond_timestamps_and_explicit_offset_are_supported():
    ms = [{"ts": int((AS_OF-timedelta(days=days)).timestamp()*1000), "subscribers": count}
          for days, count in ((0, 20), (7, 10))]
    assert trend.trend_from_points(ms, AS_OF)["delta_7"] == 10
    offset = timezone(timedelta(hours=2))
    local_cutoff = AS_OF.astimezone(offset)
    naive_points = [{"timestamp": (local_cutoff-timedelta(days=days)).replace(tzinfo=None).isoformat(),
                     "subscribers": count} for days, count in ((0, 20), (7, 10))]
    result = trend.trend_from_points(naive_points, local_cutoff)
    assert result["verified"] and result["delta_7"] == 10
    assert result["coverage"]["naive_zeitpunkte"] == 2 and "Offset" in result["zeitannahme"]


def test_cutoff_must_supply_timezone_and_invalid_container_stays_unknown():
    with pytest.raises(ValueError, match="Zeitzone"):
        trend.trend_from_points([], AS_OF.replace(tzinfo=None))
    assert trend.trend_from_points({}, AS_OF)["status"] == "unbekannt"
    assert trend.trend_from_points([point(-1, 1)], AS_OF)["aktuell"] is None


def candidate(ref=1, **changes):
    return {"signal_ref": ref, "quellen_uid": "uid-mql", "id": 123, "quelle": "mql5",
            "quelle_version": "mql5", "platform": "MT5", "eligible": True,
            "data_done": True, "abonnenten": 99, **changes}


@pytest.fixture
def snapshot_env(monkeypatch):
    store = Store()
    store.create({"id": "trend", "abo_trend_snapshot": {
        "version": trend.SNAPSHOT_VERSION, "as_of": AS_OF.isoformat(), "entries": {}, "status": "laeuft"}})
    calls = []
    sources = [{"id": 1, "kuerzel": "mql5", "quellen_uid": "uid-mql", "base_url": "http://native-mql"},
               {"id": 2, "kuerzel": "zulu", "quellen_uid": "uid-zulu", "base_url": "http://native-zulu"}]
    monkeypatch.setattr(db, "list_quellen", lambda **kwargs: sources)

    def client(source):
        def history(provider, version):
            calls.append((source["quellen_uid"], provider, version))
            return [point(-1, 999), point(0, 20), point(7, 10), point(30, 5)]
        return SimpleNamespace(history=history)
    monkeypatch.setattr(trend.quellen, "client_fuer_quelle", client)
    return store, calls


def freeze(store, entries, stopped=lambda: False):
    return trend.freeze_trends(store, "trend", entries, {}, lambda text: None, stopped)


def test_freeze_fetches_only_eligible_complete_and_preserves_original_counters(snapshot_env):
    store, calls = snapshot_env
    entries = [candidate(), candidate(2, eligible=False), candidate(3, data_done=False)]
    result = freeze(store, entries)
    assert calls == [("uid-mql", 123, "mql5")]
    assert result["status"] == "fertig" and set(result["entries"]) == {"1"}
    saved = store.tasks("trend")[0]
    assert saved["abonnenten"] == 99 and saved["abo_trend"]["aktuell"] == 20
    assert saved["abo_trend"]["verified"] and saved["abo_trend"]["quelle"] == "native_history_get"
    assert saved["abo_trend"]["coverage"]["zukuenftige_punkte"] == 1
    assert not db.DB_PATH.exists(), "The frozen enrichment must not write main scanner storage"


def test_equal_numeric_ids_of_different_sources_get_separate_native_snapshots(snapshot_env):
    store, calls = snapshot_env
    entries = [candidate(), candidate(2, quelle="zulu", quellen_uid="uid-zulu", quelle_version="mql4", platform="MT4")]
    freeze(store, entries)
    assert calls == [("uid-mql", 123, "mql5"), ("uid-zulu", 123, "mql4")]
    assert entries[0]["abo_trend"]["identitaet"] != entries[1]["abo_trend"]["identitaet"]


def test_repeated_resume_reuses_exact_cutoff_history_and_finished_attempt(snapshot_env, monkeypatch):
    store, calls = snapshot_env
    entries = [candidate()]
    first = freeze(store, entries)
    saved = deepcopy(entries[0]["abo_trend"])
    monkeypatch.setattr(trend.quellen, "client_fuer_quelle", lambda *args: pytest.fail("No repeat native GET"))
    second = freeze(store, entries)
    assert first == second and entries[0]["abo_trend"] == saved and len(calls) == 1


def test_native_error_is_unknown_and_not_replaced_by_catalog_or_scanner_history(snapshot_env, monkeypatch):
    store, calls = snapshot_env
    def unavailable(*args):
        raise RuntimeError("native service unavailable")
    monkeypatch.setattr(trend.quellen, "client_fuer_quelle", lambda *args: SimpleNamespace(history=unavailable))
    entries = [candidate(abonnenten=500)]
    freeze(store, entries)
    result = entries[0]["abo_trend"]
    assert result["aktuell"] is result["delta_7"] is None and not result["verified"]
    assert "native service unavailable" in result["grund"]
    monkeypatch.setattr(trend.quellen, "client_fuer_quelle", lambda *args: pytest.fail("Unknown attempt is frozen too"))
    freeze(store, entries)


@pytest.mark.parametrize("field,value", [("providerId", 456), ("version", "mql4"), ("quellen_uid", "other")])
def test_get_response_explicit_claim_must_match_requested_identity(snapshot_env, monkeypatch, field, value):
    store, calls = snapshot_env
    monkeypatch.setattr(trend.quellen, "client_fuer_quelle", lambda *args: SimpleNamespace(
        history=lambda *args: [point(0, 20, **{field: value}), point(7, 10)]))
    entries = [candidate()]
    freeze(store, entries)
    assert not entries[0]["abo_trend"]["verified"]
    assert entries[0]["abo_trend"]["aktuell"] is None
    assert "anderer Identität" in entries[0]["abo_trend"]["grund"]


def test_wrong_registry_uid_is_never_used_for_native_get(snapshot_env, monkeypatch):
    store, calls = snapshot_env
    monkeypatch.setattr(trend.quellen, "client_fuer_quelle", lambda *args: pytest.fail("Wrong native source"))
    entries = [candidate(quellen_uid="foreign-uid")]
    freeze(store, entries)
    assert not calls and not entries[0]["abo_trend"]["verified"]
    assert "Quellen-UID" in entries[0]["abo_trend"]["grund"]


@pytest.mark.parametrize("tamper", ["counter", "identity", "cutoff"])
def test_changed_snapshot_or_owner_is_rejected_before_any_new_get(snapshot_env, tamper):
    store, calls = snapshot_env
    entries = [candidate()]
    freeze(store, entries)
    if tamper == "counter":
        entries[0]["abo_trend"]["aktuell"] += 1
    elif tamper == "identity":
        entries[0]["quelle_version"] = "mql4"
    else:
        entries[0]["abo_trend"]["as_of"] = "2026-10-25T12:00:00+00:00"
    with pytest.raises(ValueError, match="verändert oder fremd"):
        freeze(store, entries)
    assert len(calls) == 1


def test_cooperative_stop_does_not_fetch_or_publish_synthetic_points(snapshot_env):
    store, calls = snapshot_env
    with pytest.raises(Angehalten):
        freeze(store, [candidate()], stopped=lambda: True)
    assert not calls and not store.tasks("trend")


def test_explicit_all_scope_includes_non_candidates_missing_trades_and_robo_values(snapshot_env, monkeypatch):
    store, calls = snapshot_env
    sources = [{"id": 1, "kuerzel": "mql5", "quellen_uid": "uid-mql", "base_url": "http://native-mql"},
               {"id": 2, "kuerzel": "robo", "quellen_uid": "uid-robo", "base_url": "http://native-robo"}]
    monkeypatch.setattr(db, "list_quellen", lambda **kwargs: sources)
    entries = [candidate(), candidate(2, id=124, eligible=False),
               candidate(3, id=125, data_done=False),
               candidate(4, id=126, quelle="robo", quellen_uid="uid-robo", quelle_version="rst",
                         platform="", eligible=False, auswertung_typ="quellenprofitabilitaet"),
               candidate(5, id=127, abonnenten=0), candidate(6, id=128, abonnenten=None),
               candidate(7, id=129, abonnenten=-1), candidate(8, id=130, abonnenten=True)]
    # Begin with the existing finalist default, then explicitly expand scope
    # while preserving every already frozen historical observation.
    freeze(store, entries[:4])
    initial = deepcopy(entries[0]["abo_trend"])
    first_cutoff = store.read("trend")["abo_trend_snapshot"]["as_of"]
    trend.freeze_trends(store, "trend", entries, {}, lambda text: None, lambda: False, include_all=True)
    assert calls == [("uid-mql", 123, "mql5"), ("uid-mql", 124, "mql5"),
                     ("uid-mql", 125, "mql5"), ("uid-robo", 126, "rst")]
    assert entries[0]["abo_trend"] == initial
    assert all(entry["abo_trend"]["verified"] for entry in entries[:4])
    assert all("abo_trend" not in entry for entry in entries[4:])
    assert store.read("trend")["abo_trend_snapshot"]["as_of"] == first_cutoff
    assert len(store.tasks("trend")) == 4
    monkeypatch.setattr(trend.quellen, "client_fuer_quelle", lambda *args: pytest.fail("No repeated GET"))
    trend.freeze_trends(store, "trend", entries, {}, lambda text: None, lambda: False, include_all=True)


@pytest.mark.parametrize("invalid", [1, "True", None])
def test_all_scope_requires_explicit_boolean_before_any_fetch_or_mutation(snapshot_env, invalid):
    store, calls = snapshot_env
    original = store.read("trend")
    with pytest.raises(ValueError, match="boolesch"):
        trend.freeze_trends(store, "trend", [candidate()], {}, lambda text: None, lambda: False,
                            include_all=invalid)
    assert not calls and store.read("trend") == original
