"""Stop-mode ties, calendar boundaries and lossless lot labels through CSVs."""
from datetime import date, datetime, timedelta
from itertools import permutations

import pytest

from mqlkiscanner import engine, parser, pipeline, stats, trade_data
from mqlkiscanner.lot_format import format_lots


START = datetime(2023, 1, 1)


def trade(index, profit=1, volume=.1, symbol="XAUUSD", distance=None):
    opened = START + timedelta(days=index * 30)
    change = profit / (volume * 100) if distance is None else -distance
    return [opened.strftime(parser.TIME_FMT), "Buy", str(volume), symbol, "2000", str(volume),
            (opened + timedelta(hours=1)).strftime(parser.TIME_FMT), str(2000 + change),
            "0", "0", str(profit)]


def write_csv(tmp_path, rows):
    path = tmp_path / "9000099_history.csv"
    header = ";".join(parser.POSITION_HEADER)
    balance = "2022.12.31 00:00:00;Balance;;;;;;;;;10000"
    path.write_text("\n".join([header, balance, *(";".join(row) for row in rows)]) + "\n",
                    encoding="utf-8")
    return str(path)


def test_zero_mode_tie_never_grants_stop_proof_when_csv_rows_are_reordered(tmp_path):
    gains = [trade(i, profit=1000) for i in range(26)]
    distances = [.01, .02, .03, .04, .06, .07, .08, .09]
    losses = [trade(26 + i, profit=-distance * 10, distance=distance)
              for i, distance in enumerate(distances)]
    orders = [losses[i:] + losses[:i] for i in range(len(losses))]
    orders.append(list(reversed(losses)))
    evidence = []
    for ordered in orders:
        path = write_csv(tmp_path, gains + ordered)
        stops = engine.analyze(path)["forensics"]["stops"]
        assert stops["top_distance_level"] == 0
        assert stops["top_distance_share_pct"] == 50
        assert stops["stop_evidence"] == "none"
        result = pipeline.ScanPipeline.analyze_local_files([path])[0]
        assert result.forensik_vorhanden and result.score < 5
        assert result.ampel == "🟡" and result.stop_evidence == "none"
        evidence.append(stops)
    assert all(item == evidence[0] for item in evidence)


@pytest.mark.parametrize("distances,expected_level,expected_evidence", [
    ([1] * 4 + [2] * 4, 1, "cluster"),  # positive mode ties keep the existing threshold
    ([.01] * 3 + [.1] * 5, .1, "cluster"),  # zero is not tied for the maximum
    ([20] * 3 + [1, 2, 3, 4, 5], 20, "cluster"),  # original minimum support
])
def test_positive_modes_and_existing_cluster_thresholds_remain_unchanged(
        tmp_path, distances, expected_level, expected_evidence):
    rows = [trade(i, profit=-d * 10, distance=d) for i, d in enumerate(distances)]
    for ordered in (rows, list(reversed(rows))):
        stops = engine.analyze(write_csv(tmp_path, ordered))["forensics"]["stops"]
        assert stops["top_distance_level"] == expected_level
        assert stops["stop_evidence"] == expected_evidence


def test_equal_symbol_modes_choose_same_representative_after_reordering(tmp_path):
    rows = [trade(i, profit=-10, distance=1, symbol=symbol)
            for symbol in ("XAUUSD", "US30") for i in range(8)]
    first = engine.analyze(write_csv(tmp_path, rows))["forensics"]["stops"]
    second = engine.analyze(write_csv(tmp_path, list(reversed(rows))))["forensics"]["stops"]
    # The representative and reported distance statistics must not depend on
    # which symbol happened to occur first. Ribbon ordering is separate.
    assert first["cluster_symbol"] == second["cluster_symbol"] == "US30"
    assert first["stop_evidence"] == second["stop_evidence"] == "cluster"
    assert first["per_symbol"] == second["per_symbol"]


@pytest.mark.parametrize("first,last,expected", [
    ("2024-01-01 12:00", "2024-02-29 08:00", {"2024-01", "2024-02"}),
    ("2024-01-01 08:00", "2024-02-29 12:00", {"2024-01", "2024-02"}),
    ("2024-01-01 23:59", "2024-01-31 00:01", {"2024-01"}),
    ("2023-12-01 23:59", "2024-01-31 00:01", {"2023-12", "2024-01"}),
    ("2024-01-02 12:00", "2024-02-28 08:00", set()),  # partial leap-year February
    ("2023-01-02 12:00", "2023-02-28 08:00", {"2023-02"}),
    ("2024-01-02 12:00", "2024-03-30 08:00", {"2024-02"}),
])
def test_full_calendar_months_ignore_intraday_times_but_keep_partial_month_rules(first, last, expected):
    assert stats.full_month_keys(datetime.fromisoformat(first), datetime.fromisoformat(last)) == expected


def test_negative_final_full_month_is_counted_from_real_csv(tmp_path):
    rows = [trade(0, profit=10), trade(1, profit=-10)]
    rows[0][0], rows[0][6] = "2024.01.01 12:00:00", "2024.01.01 13:00:00"
    rows[1][0], rows[1][6] = "2024.02.01 12:00:00", "2024.02.29 08:00:00"
    parsed = parser.load_export(write_csv(tmp_path, rows))
    assert stats.negative_months_full(parsed) == ["2024-02"]


def test_calendar_date_inputs_remain_supported():
    assert stats.full_month_keys(date(2024, 1, 1), date(2024, 2, 29)) == {"2024-01", "2024-02"}


@pytest.mark.parametrize("volumes,expected,expected_range", [
    ([.001, .001, .002], {"0.001": 2, "0.002": 1}, "0.001-0.002"),
    ([.01, .01, .02, 1], {"0.01": 2, "0.02": 1, "1.00": 1}, "0.01-1.00"),
    ([.011, .012, .012], {"0.011": 1, "0.012": 2}, "0.011-0.012"),
    ([1e-7, 2e-7], {"0.0000001": 1, "0.0000002": 1}, "0.0000001-0.0000002"),
])
def test_histograms_and_ranges_preserve_all_parsed_volumes(tmp_path, volumes, expected, expected_range):
    for ordered in set(permutations(volumes)):
        rows = [trade(i, profit=volume * 1000, volume=volume) for i, volume in enumerate(ordered)]
        parsed = parser.load_export(write_csv(tmp_path, rows))
        metrics = stats.compute(parsed)
        payload = trade_data.build_trade_payload(parsed)
        assert metrics["lots"] == payload["lots_verteilung"] == expected
        assert sum(payload["lots_verteilung"].values()) == payload["meta"]["trades"] == len(volumes)
        assert payload["pro_symbol"][0]["lots"] == expected_range


def test_distinct_roundtrippable_float_volumes_cannot_collide():
    values = [.01, .010000000000000002, .001, 1e-15, 10.0]
    labels = [format_lots(value) for value in values]
    assert len(set(labels)) == len(values)
    assert [float(label) for label in labels] == values
    assert format_lots(.1) == "0.10"
