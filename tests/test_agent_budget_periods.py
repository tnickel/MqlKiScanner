"""Request-start accounting across period changes; synthetic DBs and HTTP only."""
from datetime import datetime
import json
from unittest.mock import Mock

import pytest
import requests

from mqlkiscanner import db, secrets_store
from mqlkiscanner.agenten import budget, dirigent, journal
from mqlkiscanner.llm import client as llm_client


SETTINGS={"agenten_tagesbudget_tokens":10000,"agenten_monatsbudget_tokens":10000,
          "agenten_dirigent_max_tokens":10}


def response(tokens=30,finish="stop"):
    r=requests.Response()
    r.status_code=200
    r._content=json.dumps({"choices":[{"message":{"content":json.dumps({"aktionen":[],"begruendung":"synthetic"})},
                                        "finish_reason":finish}],
                            "usage":{"total_tokens":tokens}}).encode()
    return r


@pytest.fixture
def clock(monkeypatch):
    tick=[datetime(2026,10,16,12)]
    class Clock:
        @staticmethod
        def now(): return tick[0]
    monkeypatch.setattr(budget,"datetime",Clock)
    monkeypatch.setattr(journal,"_now",lambda:tick[0].isoformat(" "))
    monkeypatch.setattr(journal,"_heute",lambda:tick[0].strftime("%Y-%m-%d"))
    monkeypatch.setattr(journal,"_monat",lambda:tick[0].strftime("%Y-%m"))
    monkeypatch.setattr(secrets_store,"get_secret",lambda _:"synthetic-key")
    monkeypatch.setattr(llm_client.time,"sleep",lambda _:None)
    return tick


def run_dirigent():
    run=journal.lauf_starten("dirigent")
    lage={"start_zeit":"synthetic","tagesbudget_tokens":10000,"tokens_heute":0,
          "monatsbudget_tokens":10000,"tokens_monat":0}
    result=dirigent._llm_entscheidung(lage,SETTINGS,run,lambda _:None)
    return run,result


@pytest.mark.parametrize("start,end", [
    (datetime(2026,10,16,23,59),datetime(2026,10,17,0,1)),
    (datetime(2026,10,31,23,59),datetime(2026,11,1,0,1)),
])
def test_real_role_completion_in_new_period_does_not_rebook_request(clock,monkeypatch,start,end):
    clock[0]=start
    def post(*a,**kw):
        # SQLite reserved in the previous period; role completion occurs later.
        clock[0]=end
        return response(30)
    monkeypatch.setattr(llm_client.requests,"post",post)
    run,result=run_dirigent()
    assert result is not None
    with db._connect() as conn:
        row=conn.execute("SELECT tokens,budget_ledger FROM agenten_schritte "
                         "WHERE lauf_id=? AND schritt='llm_entscheidung'",(run,)).fetchone()
    assert row["tokens"] == 30 and row["budget_ledger"] == 1
    assert journal.tokens_heute() == 0
    same_month=start.month==end.month
    assert journal.tokens_monat() == (30 if same_month else 0)
    assert budget.spent(start.strftime("%Y-%m-%d")) == 30
    ticket=budget.reserve(SETTINGS,500,"synthetic","new-period request")
    budget.settle(ticket,20,"synthetic","ok")
    assert journal.tokens_heute() == 20
    assert journal.tokens_monat() == (50 if same_month else 20)
    # A genuine legacy cost, even after the ledger exists, must remain additive.
    journal.schritt_protokollieren(run,"legacy","old-client",prompt="synthetic",tokens=7)
    assert journal.tokens_heute() == 27
    assert journal.tokens_monat() == (57 if same_month else 27)
    with pytest.raises(llm_client.LlmBudgetError):
        budget.reserve({"agenten_tagesbudget_tokens":60},34,"synthetic","would exceed by one")


def test_unmarked_legacy_before_and_after_first_ledger_call_counts(clock):
    run=journal.lauf_starten("legacy")
    journal.schritt_protokollieren(run,"legacy","before",prompt="synthetic",tokens=11)
    ticket=budget.reserve(SETTINGS,500,"synthetic","request")
    budget.settle(ticket,20,"synthetic","ok")
    journal.schritt_protokollieren(run,"legacy","after",prompt="synthetic",tokens=17)
    assert journal.tokens_heute() == journal.tokens_monat() == 48
    with pytest.raises(llm_client.LlmBudgetError):
        budget.reserve({"agenten_tagesbudget_tokens":50},3,"synthetic","would exceed by one")


@pytest.mark.parametrize("success", [False,True])
def test_transport_costs_and_real_role_error_mirrors_count_once(clock,monkeypatch,success):
    second=response(20) if success else requests.Timeout("synthetic second timeout")
    post=Mock(side_effect=[requests.Timeout("synthetic first timeout"),second])
    monkeypatch.setattr(llm_client.requests,"post",post)
    run,result=run_dirigent()
    assert (result is not None) == success
    assert post.call_count == 2
    with db._connect() as conn:
        attempts=conn.execute("SELECT reserviert,tokens,status FROM agenten_budget_versuche ORDER BY rowid").fetchall()
        outer=conn.execute("SELECT budget_ledger FROM agenten_schritte WHERE lauf_id=? "
                           "AND schritt='llm_entscheidung'",(run,)).fetchone()
    assert outer["budget_ledger"] == 1
    assert attempts[0]["tokens"] == attempts[0]["reserviert"]
    assert attempts[0]["status"] == "transport_kosten_unbekannt"
    assert attempts[1]["tokens"] == (20 if success else attempts[1]["reserviert"])
    expected=sum(a["tokens"] for a in attempts)
    assert journal.tokens_heute() == journal.tokens_monat() == expected


def test_length_retry_costs_and_outer_aggregate_count_once(clock,monkeypatch):
    post=Mock(side_effect=[response(50,"length"),response(100)])
    monkeypatch.setattr(llm_client.requests,"post",post)
    run,result=run_dirigent()
    assert result is not None and post.call_count == 2
    assert journal.tokens_heute() == journal.tokens_monat() == 150
    with db._connect() as conn:
        outer=conn.execute("SELECT tokens,budget_ledger FROM agenten_schritte WHERE lauf_id=? "
                           "AND schritt='llm_entscheidung'",(run,)).fetchone()
    assert outer["tokens"] == 150 and outer["budget_ledger"] == 1


def test_old_journal_migration_preserves_real_legacy_costs(clock):
    old_schema=journal._SCHEMA.replace("    budget_ledger INTEGER NOT NULL DEFAULT 0,\n","")
    assert "budget_ledger" not in old_schema
    with db._connect() as conn:
        conn.executescript(old_schema)
        run=conn.execute("INSERT INTO agenten_laeufe(rolle,quelle,start,status) "
                         "VALUES('legacy','synthetic',?,'ok')",(journal._now(),)).lastrowid
        conn.execute("INSERT INTO agenten_schritte(lauf_id,ts,rolle,schritt,status,prompt,tokens) "
                     "VALUES(?,?,'legacy','historical','ok','synthetic',13)",(run,journal._now()))
    journal.init_journal()
    with db._connect() as conn:
        row=conn.execute("SELECT tokens,budget_ledger FROM agenten_schritte").fetchone()
    assert row["tokens"] == 13 and row["budget_ledger"] == 0
    assert journal.tokens_heute() == 13
    ticket=budget.reserve(SETTINGS,500,"synthetic","new request")
    budget.settle(ticket,7,"synthetic","ok")
    assert journal.tokens_heute() == 20
