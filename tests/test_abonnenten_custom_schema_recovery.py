"""Paid generic JSON must pass each workflow's custom schema before reuse."""
from copy import deepcopy
import hashlib
import json

import pytest

from mqlkiscanner import abonnenten_analyse_ki as ki, abonnenten_analyse_klaerung as kl
from mqlkiscanner import abonnenten_analyse_redaktion as edit, config
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner.llm.client import LlmError


@pytest.fixture
def entry(tmp_path):
    path = tmp_path / "trade.csv"
    path.write_text("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
                    "2026.01.01 12:00:00;Buy;0.01;EURUSD;1.1;0.01;2026.01.01 13:00:00;1.2;0;0;10\n",
                    encoding="utf-8")
    body = "# Bericht\n\nEin belegter historischer Befund."
    return {"signal_ref": 1, "id": 1, "quelle": "mql5", "name": "Synthetic",
            "trades_path": str(path), "trades_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "trades": 1, "data_basis": "frozen", "top5_basis": "original-deep",
            "forensik": {"forensics": {"martingale": {"flag": False}}}, "equity": {},
            "ki_pruefhinweise": [{"text": "Konkrete Datenfrage", "beleg_refs": ["trades"]}],
            "top5_comparison": [{"signal_ref": 1, "retdd_jahr": 3}],
            "top5_befund": {"bericht_markdown": body}, "bericht_markdown": body}


class Client:
    has_key = True
    def __init__(self, field, answer):
        self.field, self.answer, self.requests = field, answer, []
    def chat(self, prompt, **kwargs):
        self.requests.append(prompt)
        kwargs["meta_out"].update(total_tokens=100)
        return json.dumps({"signal_ref": 1, "strategietyp": "Prüfung", "strategie_sicherheit": "belegt",
                           "martingale_einordnung": "kein_beleg", "kurzurteil": "Gezielte Prüfung",
                           "staerken": [], "risiken": [], "pruefhinweise": [], "datenluecken": [],
                           self.field: deepcopy(self.answer)})


def workflow(kind, entry):
    if kind == "resolver":
        cls, method, field = kl.KlaerungKI, "klaeren", "hinweisklaerung"
        answer = kl.blocked_resolution(entry, "Eine erforderliche Datengrundlage ist nicht entscheidbar.")
    else:
        cls, method, field = edit.BerichtRedaktionKI, "pruefen", "berichtpruefung"
        answer = {"schema_version": edit.REVIEW_VERSION, "signal_ref": 1,
                  "pruefbasis": edit.review_basis(entry),
                  "original_bericht_sha256": ki.digest(entry["top5_befund"]["bericht_markdown"]),
                  "korrekturen": [], "offene_pflichtfragen": []}
    def execute(store, client):
        instance = cls(store, "recovery", config.load_settings(), {}, client=client)
        return getattr(instance, method)(entry)
    return execute, field, answer


@pytest.mark.parametrize("kind", ["resolver", "redaktion"])
def test_explicit_resume_skips_paid_custom_invalid_cache_and_can_request_again(entry, kind):
    execute, field, valid = workflow(kind, entry)
    store = Store()
    store.create({"id": "recovery"})
    invalid = deepcopy(valid)
    invalid["schema_version"] = True  # valid generic envelope, invalid custom schema
    first = Client(field, invalid)
    with pytest.raises(LlmError):
        execute(store, first)
    assert len(first.requests) == 2
    assert store.spent("recovery") == 200
    with store.connection() as connection:
        paid_before = [dict(row) for row in connection.execute("SELECT * FROM calls ORDER BY rowid")]
    success = Client(field, valid)
    result = execute(store, success)
    assert result["schema_version"] == valid["schema_version"]
    assert len(success.requests) == 1
    assert store.spent("recovery") == 300
    with store.connection() as connection:
        paid_after = [dict(row) for row in connection.execute("SELECT * FROM calls ORDER BY rowid")]
    assert paid_after[:2] == paid_before, "Rejected paid responses and their charges must remain untouched"
    replay = Client(field, invalid)
    assert execute(store, replay) == result
    assert not replay.requests and store.spent("recovery") == 300
