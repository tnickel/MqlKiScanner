"""XR-1/XR-2/ZU-R2: explicit list scope, non-destructive legacy, honest receipts."""
from types import SimpleNamespace

import pytest

from mqlkiscanner import (abonnenten_analyse as analyse, abonnenten_statistik as abo,
                         client_updates as cu, db, downloader_client as dc, ingest, katalog, quellen)
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner import abonnenten_analyse_ki as ki, pdf_reports


def provider(sid, version="pelican"):
    return dict(signalId=str(sid), signalName=f"Fresh {sid}", version=version,
                subscribers=50, weeks=20, url=f"https://example.invalid/{sid}")


class CatalogClient:
    def __init__(self, items, scope="full", *, page_size=500, later_scope=None):
        self.items, self.scope = items, scope
        self.page_size, self.later_scope = page_size, later_scope
        self.calls = []

    def katalog(self, *, limit, offset, min_subscribers, catalog_scope):
        self.calls.append(dict(limit=limit, offset=offset, min_subscribers=min_subscribers, catalog_scope=catalog_scope))
        block = self.items[offset:offset+min(limit, self.page_size)]
        result = dict(items=block, total=len(self.items), offset=offset)
        scope = self.later_scope if offset and self.later_scope is not None else self.scope
        if scope is not None:
            result["catalogScope"] = scope
        return result

    def history(self, *args):
        return []

    def health(self):
        return {"providerRefresh": True}


def wire(monkeypatch, client, name="pelik"):
    source = db.get_quelle(db.add_quelle(name, "Fixture", "http://scope.invalid"))
    monkeypatch.setattr(quellen, "_ensure", lambda: None)
    monkeypatch.setattr(quellen, "client_fuer_quelle", lambda *a, **kw: client)
    return source


@pytest.mark.parametrize("scope", ["subscribers", "unknown", None])
def test_top_selection_or_legacy_response_cannot_shrink_full_catalog(monkeypatch, scope):
    client = CatalogClient([provider(1), provider(500)], scope)
    source = wire(monkeypatch, client)
    db.katalog_upsert_many(source["kuerzel"], [{"signal_id": sid, "name": f"Old {sid}"} for sid in range(1, 301)])
    summary = katalog.sync()
    rows = {row["signal_id"]: row for row in db.katalog_list()}
    assert len(rows) == 301 and rows[1]["name"] == "Fresh 1"
    assert set(range(1, 301)) <= rows.keys()
    assert summary["quellen"]["pelik"]["geloescht"] == 0
    assert "Vollkatalog nicht bestätigt" in summary["quellen"]["pelik"]["hinweis"]
    assert db.katalog_sync_status()["pelik"]["fehler"]
    assert client.calls[0]["catalog_scope"] == "full"


@pytest.mark.parametrize("scope", ["subscribers", "unknown", None])
def test_statistics_merge_keeps_providers_outside_selection(monkeypatch, scope):
    client = CatalogClient([provider(1)], scope)
    source = wire(monkeypatch, client)
    db.katalog_upsert_many("pelik", [{"signal_id": sid} for sid in range(1, 301)])
    result = abo.sync_quelle(source)
    assert len(db.katalog_list()) == 300 and result["messpunkte"] == 0
    assert any("Vollkatalog nicht bestätigt" in message for message in result["fehler"])
    assert client.calls[0]["catalog_scope"] == "full"


def test_proven_full_empty_catalog_still_removes_old_rows(monkeypatch):
    wire(monkeypatch, CatalogClient([], "full"))
    db.katalog_upsert_many("pelik", [{"signal_id": 99}])
    assert katalog.sync()["quellen"]["pelik"]["geloescht"] == 1
    assert db.katalog_list() == []


@pytest.mark.parametrize("first,second", [("full", "subscribers"), ("full", None), (None, "full"),
                                         ("full", "unknown"), ("unknown", "full")])
def test_scope_must_match_on_every_page(first, second):
    client = CatalogClient([provider(1), provider(2)], first, page_size=1)
    original = client.katalog
    def pages(**kw):
        page = original(**kw)
        if kw["offset"]:
            if second is None:
                page.pop("catalogScope", None)
            else:
                page["catalogScope"] = second
        return page
    client.katalog = pages
    with pytest.raises(dc.DownloaderError, match="catalogScope wechselte"):
        ingest.hole_katalog({}, client=client)
    assert all(call["catalog_scope"] == "full" for call in client.calls)


@pytest.mark.parametrize("scope", [None, "subscribers", "unknown", "full"])
def test_workflow_requests_full_and_does_not_relabel_an_overlay(monkeypatch, scope):
    client = CatalogClient([provider(11)], scope)
    wire(monkeypatch, client)
    messages = []
    result = ingest.kandidaten_aus_quellen(log=messages.append)
    assert [row["id"] for row in result] == ([11] if scope == "full" else [])
    assert client.calls[0]["catalog_scope"] == "full"
    if scope != "full":
        assert any("Workflow übersprungen" in message for message in messages)


def test_client_transmits_explicit_scope_without_changing_default_contract(monkeypatch):
    calls = []
    def get(url, *, params, **kwargs):
        calls.append(params)
        return SimpleNamespace(status_code=200, json=lambda: {"items": [], "total": 0})
    monkeypatch.setattr(dc.requests, "get", get)
    client = dc.DownloaderClient("http://scope.invalid")
    client.katalog(catalog_scope="full")
    client.katalog(catalog_scope="subscribers")
    client.katalog()
    with pytest.raises(ValueError, match="catalog_scope"):
        client.katalog(catalog_scope="unknown")
    assert [call.get("catalogScope") for call in calls] == ["full", "subscribers", None]


@pytest.mark.parametrize("scope", [True, [], {}, "invalid"])
def test_malformed_scope_is_a_typed_catalog_error(scope):
    with pytest.raises(dc.DownloaderError, match="catalogScope"):
        ingest.hole_katalog({}, client=CatalogClient([], scope))


def test_research_requests_selection_and_keeps_unconfirmed_receipt_visible(monkeypatch):
    client = CatalogClient([provider(11)], "subscribers")
    wire(monkeypatch, client)
    store = Store()
    store.create(dict(id="scope", quellen=["pelik"], snapshot_quellen={}, logs=[]))
    monkeypatch.setattr(cu, "starte_alle_updates", lambda *a, **kw: {"pelik": {
        "status": cu.TEILWEISE, "abonnenten_auswahl_unbestaetigt": True, "job_id": "fresh"}})
    analyse._snapshot(store, store.read("scope"), {}, lambda message: None, lambda: False)
    assert client.calls[0]["catalog_scope"] == "subscribers"
    snapshot = store.read("scope")["snapshot_quellen"]["pelik"]
    assert snapshot["status"] == "fertig" and snapshot["abonnenten_auswahl_unbestaetigt"] is True
    row = store.tasks("scope")[0]
    assert row["abo_referenz_vollstaendig"] is False
    assert "unbestätigt" in row["abo_auswahl_hinweis"]
    assert row["abo_ausgelassene_positionen"] == [], "Unknown coverage does not prove any skipped API positions"


def test_selection_warning_reaches_prompt_and_pdf_without_inventing_skipped_positions(monkeypatch):
    warning = "Abonnentenauswahl/Abdeckung unbestätigt: Auswahlbeleg fehlt."
    row = dict(signal_ref=8, id=8, quelle="pelik", name="Fixture", bericht_markdown="Fixture report",
               abo_referenz_vollstaendig=False, abo_ausgelassene_positionen=[], abo_auswahl_hinweis=warning)
    ai = object.__new__(ki.AnalyseKI)
    ai.profile = {}
    prompt, _, candidate = ai._prompt("abonnenten_kurztest", row, "vollanalyse", {}, [])
    assert warning in prompt and candidate["abo_auswahl_hinweis"] == warning
    captured = []
    monkeypatch.setattr(pdf_reports, "render_report_pdf", lambda report: captured.append(report.body) or b"fixture pdf")
    ki.report_pdf(row, "scope")
    assert warning in captured[0] and "ausgelassene API-Positionen" not in captured[0]
    old = dict(row)
    old.pop("abo_auswahl_hinweis")
    _, _, old_candidate = ai._prompt("abonnenten_kurztest", old, "vollanalyse", {}, [])
    assert "abo_auswahl_hinweis" not in old_candidate, "Existing prompt/cache inputs must not gain a new null field"


def test_update_without_coverage_is_usable_warning_and_persisted(monkeypatch):
    source = wire(monkeypatch, CatalogClient([]))
    client = SimpleNamespace(
        health=lambda: {"status": "ok", "abonnentenRefresh": True},
        update_starten=lambda **kw: {"jobId": "own"},
        update_status=lambda: {"state": "done", "jobId": "own", "ergebnis": {
            "nurAbonnenten": True, "signaleGeliefert": 20, "datenstand": "fixture"}})
    monkeypatch.setattr(quellen, "client_fuer_quelle", lambda *a, **kw: client)
    result = cu._update_eine_quelle(source, settings={}, modus="abonnenten", log=None,
        on_fortschritt=None, gestopft=lambda: False, bereit_warten_s=0,
        poll_s=.001, backoff_s=0, timeout_s=1, login_timeout_s=0)
    assert result["status"] == cu.TEILWEISE and result["abonnenten_auswahl_unbestaetigt"] is True
    assert "Abdeckung unbestätigt" in result["detail"]
    assert any("Abdeckung unbestätigt" in str(row["hinweise"]) for row in db.list_client_updates())


@pytest.mark.parametrize("mode", ["scan", "abonnenten"])
def test_cancelled_own_job_is_terminal_without_timeout_polling(monkeypatch, mode):
    source = wire(monkeypatch, CatalogClient([]), "zulu")
    polls = []
    def status():
        polls.append(1)
        return dict(state="cancelled", jobId="own", phase="downloads", message="Belegter Abbruch", done=3, total=10)
    client = SimpleNamespace(health=lambda: {"status": "ok", "abonnentenRefresh": True},
                             update_starten=lambda **kw: {"jobId": "own"}, update_status=status)
    monkeypatch.setattr(quellen, "client_fuer_quelle", lambda *a, **kw: client)
    monkeypatch.setattr(cu.time, "sleep", lambda *a: pytest.fail("Cancelled job must not be polled again"))
    result = cu._update_eine_quelle(source, settings={}, modus=mode, log=None,
        on_fortschritt=None, gestopft=lambda: False, bereit_warten_s=0,
        poll_s=.001, backoff_s=0, timeout_s=7200, login_timeout_s=0)
    assert result["status"] == cu.ABGEBROCHEN
    assert "Belegter Abbruch" in result["detail"] and result["done"] == 3
    assert len(polls) == 1 and db.list_client_updates()[0]["status"] == cu.ABGEBROCHEN
