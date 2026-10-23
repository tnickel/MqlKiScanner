"""Research-only HTTP admission, cancellation and real concurrent budget SQL."""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import format_datetime

import pytest
import requests

from mqlkiscanner import abonnenten_analyse_ki as ki, config, db
from mqlkiscanner.abonnenten_analyse_parallel import AdaptiveHttpGate
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner.agenten import budget, journal
from mqlkiscanner.llm import client as llm


def response(status=200, *, code=None, retry_after=None, content="{}", tokens=100):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps({"error": {"code": code}} if status >= 400 else {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"total_tokens": tokens}}).encode()
    if retry_after is not None:
        result.headers["Retry-After"] = retry_after
    return result


class Clock:
    def __init__(self): self.value = 100.0; self.waits = []
    def __call__(self): return self.value
    def wait(self, condition, delay): self.waits.append(delay); self.value += delay
    def advance(self, delay): self.value += delay


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(llm.secrets_store, "get_secret", lambda _: "synthetic-key")


def test_adaptive_shared_cooldown_retry_after_and_slow_recovery():
    clock, notifications = Clock(), []
    gate = AdaptiveHttpGate(max_limit=10, monotonic=clock, wait=clock.wait,
                            recovery_successes=2, recovery_interval_s=60, on_change=notifications.append)
    with gate.slot():
        gate.observe(response(429, code="1302", retry_after="90"))
    assert gate.status()["limit"] == 5
    assert gate.status()["cooldown_remaining_s"] == 90
    assert gate.status()["active"] == 0
    with gate.slot():
        assert sum(clock.waits) == pytest.approx(90)
        gate.observe(response())
    gate.observe(response())
    assert gate.status()["limit"] == 6
    gate.observe(response())
    assert gate.status()["limit"] == 6, "One success cannot undo a throttle"
    clock.advance(60)
    gate.observe(response())
    assert gate.status()["limit"] == 7
    assert gate.status()["max_active"] == 1
    assert all(delay <= .5 for delay in clock.waits)
    assert notifications and notifications[-1]["throttles"] == 1


def test_repeated_throttling_halves_to_one_and_honors_http_date():
    clock = Clock()
    stamp = 1_700_000_000
    gate = AdaptiveHttpGate(max_limit=10, monotonic=clock, wait=clock.wait, wall_time=lambda: stamp)
    after = format_datetime(datetime.fromtimestamp(stamp+120, timezone.utc), usegmt=True)
    gate.observe(response(429, retry_after=after))
    assert gate.status()["cooldown_remaining_s"] == 120
    for expected in (2, 1, 1):
        gate.observe(response(400, code="1302"))
        assert gate.status()["limit"] == expected
    assert gate.status()["throttles"] == 4
    assert gate.status()["cooldown_remaining_s"] == 120


@pytest.mark.parametrize("value", [None, "nonsense", "nan", "inf", "-1"])
def test_bad_retry_after_cannot_disable_minimum_cooldown(value):
    clock = Clock()
    gate = AdaptiveHttpGate(monotonic=clock, wait=clock.wait)
    gate.observe(response(429, retry_after=value))
    assert gate.status()["cooldown_remaining_s"] == 15


@pytest.mark.parametrize("kwargs", [{"max_limit": 11}, {"max_limit": True}, {"initial_limit": 0},
                                   {"poll_s": .6}, {"cooldown_s": 0}, {"recovery_successes": False}])
def test_gate_rejects_invalid_limits(kwargs):
    with pytest.raises(ValueError): AdaptiveHttpGate(**kwargs)


def test_stop_interrupts_capacity_wait_and_backoff_without_slot_leak():
    stopped = threading.Event()
    def check():
        if stopped.is_set(): raise ki.Angehalten("synthetic stop")
    gate = AdaptiveHttpGate(max_limit=1, check_stop=check, poll_s=.01)
    with gate.slot(), ThreadPoolExecutor(max_workers=1) as pool:
        waiting = pool.submit(lambda: _take(gate))
        stopped.set()
        with pytest.raises(ki.Angehalten): waiting.result(timeout=1)
    assert gate.status()["active"] == 0
    with pytest.raises(ki.Angehalten): gate.backoff(100)


def _take(gate):
    with gate.slot(): return True


def test_admission_precedes_agent_ticket_and_throttle_is_typed_after_only_three_requests(key, monkeypatch):
    clock = Clock()
    gate = AdaptiveHttpGate(max_limit=10, monotonic=clock, wait=clock.wait)
    gate.observe(response(429))
    reserve_times, post_times = [], []
    real_reserve = budget.reserve
    def reserve(*args, **kwargs):
        reserve_times.append(clock())
        assert gate.status()["active"] == 1
        return real_reserve(*args, **kwargs)
    def post(*args, **kwargs):
        post_times.append(clock())
        return response(429, code="1302")
    monkeypatch.setattr(budget, "reserve", reserve)
    monkeypatch.setattr(llm.requests, "post", post)
    client = budget.attach(llm.GlmClient("synthetic", "synthetic", request_gate=gate), {
        "agenten_tagesbudget_tokens": 1_000_000, "agenten_monatsbudget_tokens": 1_000_000})
    client.budget_tickets = []
    with pytest.raises(llm.LlmRateLimitError): client.chat("synthetic", max_tokens=10)
    assert len(post_times) == len(reserve_times) == 3
    assert min(reserve_times) >= 115, "No SQL reservation while admission is cooling down"
    assert gate.status()["limit"] == 1 and gate.status()["active"] == 0
    assert len(client.budget_tickets) == 3
    assert budget.spent(datetime.now().strftime("%Y-%m-%d")) == 0


def test_gate_stop_before_first_ticket_settles_research_reservation_to_zero(key, monkeypatch):
    store = Store(); store.create({"id": "not-sent"})
    ai = ki.AnalyseKI(store, "not-sent", config.load_settings(), {})
    def stop(): raise ki.Angehalten("before first HTTP")
    ai.client.request_gate = AdaptiveHttpGate(check_stop=stop)
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: pytest.fail("No paid request"))
    entry = dict(signal_ref=7, id=7, quelle="mql5", name="Synthetic", forensik={}, equity={})
    with pytest.raises(ki.Angehalten): ai._ask("abonnenten_kurztest", entry, "vollanalyse", {}, [])
    assert store.spent("not-sent") == 0
    assert ai.client.budget_tickets == []
    with store.connection() as connection:
        row = connection.execute("SELECT status,tokens,meta FROM calls").fetchone()
        assert row["tokens"] == 0 and json.loads(row["meta"])["known_not_sent"] is True


def test_stop_after_uncertain_transport_never_refunds_its_ticket(key, monkeypatch):
    stopped = threading.Event()
    def check():
        if stopped.is_set(): raise ki.Angehalten("stop after timeout")
    store = Store(); store.create({"id": "uncertain"})
    settings = {**config.load_settings(), "agenten_tagesbudget_tokens": 10_000_000,
                "agenten_monatsbudget_tokens": 10_000_000}
    ai = ki.AnalyseKI(store, "uncertain", settings, {})
    ai.client.request_gate = AdaptiveHttpGate(check_stop=check)
    def post(*args, **kwargs):
        stopped.set()
        raise requests.Timeout("synthetic timeout after request")
    monkeypatch.setattr(llm.requests, "post", post)
    entry = dict(signal_ref=8, id=8, quelle="mql5", name="Synthetic", forensik={}, equity={})
    with pytest.raises(ki.Angehalten): ai._ask("abonnenten_kurztest", entry, "vollanalyse", {}, [])
    assert len(ai.client.budget_tickets) == 1
    with db._connect() as connection:
        row = connection.execute("SELECT tokens,status FROM agenten_budget_versuche").fetchone()
        assert row["tokens"] > 0 and row["status"] == "transport_kosten_unbekannt"
        assert store.spent("uncertain") == row["tokens"]
    with store.connection() as connection:
        assert json.loads(connection.execute("SELECT meta FROM calls").fetchone()[0])["known_not_sent"] is False


def test_ten_private_clients_reconcile_real_run_and_day_month_reservations(key, monkeypatch):
    db.init_db(); journal.init_journal()
    store = Store(); store.create({"id": "ten-workers"})
    settings = {**config.load_settings(), "llm_max_total_tokens": 20_000_000,
                "agenten_tagesbudget_tokens": 1_000_000, "agenten_monatsbudget_tokens": 1_000_000}
    barrier = threading.Barrier(10)
    lock = threading.Lock()
    active = peak = 0
    gate = AdaptiveHttpGate(max_limit=10)
    clients = []
    def post(*args, **kwargs):
        nonlocal active, peak
        body = json.loads(kwargs["data"])
        index = int(body["messages"][-1]["content"].split()[-1])
        with lock: active += 1; peak = max(peak, active)
        try:
            barrier.wait(timeout=15)
            answer = {"signal_ref": index, "strategietyp": "Synthetic", "strategie_sicherheit": "plausibel",
                      "martingale_einordnung": "kein_beleg", "kurzurteil": "Synthetic profile",
                      "staerken": [], "risiken": [], "pruefhinweise": [], "datenluecken": []}
            return response(content=json.dumps(answer), tokens=100+index)
        finally:
            with lock: active -= 1
    monkeypatch.setattr(llm.requests, "post", post)
    def work(index):
        ai = ki.AnalyseKI(store, "ten-workers", dict(settings), {})
        ai.client.request_gate = gate
        with lock: clients.append(ai.client)
        entry = dict(signal_ref=index, id=index, quelle="mql5", name=f"Synthetic {index}")
        ai._prompt = lambda *a, **k: (f"Synthetic profile {index}", {}, {"signal_ref": index})
        return ai._ask("abonnenten_kurztest", entry, "vollanalyse", {}, [])
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(work, range(1, 11)))
    assert [r["signal_ref"] for r in results] == list(range(1, 11))
    expected = sum(100+i for i in range(1, 11))
    assert peak == gate.status()["max_active"] == 10
    assert gate.status()["active"] == 0
    assert len(clients) == 10 and all(len(c.budget_tickets) == 1 for c in clients)
    assert store.spent("ten-workers") == expected
    with db._connect() as connection:
        assert connection.execute("SELECT SUM(tokens),COUNT(*),MIN(abgeschlossen) FROM agenten_budget_versuche").fetchone()[:] == (expected, 10, 1)
    with store.connection() as connection:
        costs = [row[0] for row in connection.execute("SELECT tokens FROM calls ORDER BY tokens")]
        assert costs == list(range(101, 111))


def test_ten_competing_reservations_never_cross_either_sql_cap():
    db.init_db(); journal.init_journal()
    store = Store(); store.create({"id": "run-cap"})
    def reserve_run(index):
        try:
            store.reserve("run-cap", f"private-{index}", 100, 250)
            return index
        except llm.LlmBudgetError:
            return None
    def reserve_daily(index):
        try:
            return budget.reserve({"agenten_tagesbudget_tokens": 2500,
                                   "agenten_monatsbudget_tokens": 2500}, 1500, "synthetic", f"private-{index}")
        except llm.LlmBudgetError:
            return None
    with ThreadPoolExecutor(max_workers=10) as pool:
        admitted_run = [index for index in pool.map(reserve_run, range(10)) if index is not None]
        admitted_daily = [ticket for ticket in pool.map(reserve_daily, range(10)) if ticket is not None]
    assert len(admitted_run) == 2 and store.spent("run-cap") == 200
    assert len(admitted_daily) == 1
    with db._connect() as connection:
        assert connection.execute("SELECT SUM(reserviert) FROM agenten_budget_versuche").fetchone()[0] == 1500


def test_notification_callbacks_cannot_publish_regressing_peaks_or_hold_admission_lock():
    observed = []
    barrier = threading.Barrier(10)
    def changed(snapshot):
        # Older notifications would finish later without the separate lock.
        time.sleep(.001*(11-snapshot["max_active"]))
        observed.append(snapshot["max_active"])
        if len(observed) % 3 == 0:
            raise ValueError("Synthetic display failure")
    gate = AdaptiveHttpGate(max_limit=10, on_change=changed)
    def work(index):
        with gate.slot():
            barrier.wait(timeout=5)
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(work, range(10)))
    assert observed == sorted(observed)
    assert gate.status()["max_active"] == 10 and gate.status()["active"] == 0


def test_missing_optional_gate_leaves_existing_retry_sleep_and_type_behavior(key, monkeypatch):
    sleeps, calls = [], []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: calls.append(1) or response(503))
    with pytest.raises(llm.LlmError) as error: llm.GlmClient("s", "s").chat("synthetic")
    assert not isinstance(error.value, llm.LlmRateLimitError)
    assert sleeps == [5, 10] and len(calls) == 3
