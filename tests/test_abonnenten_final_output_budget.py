"""Final-review output room must reach HTTP and its conservative reservation."""
import json

import pytest

from mqlkiscanner import abonnenten_analyse_ki as ki, config
from mqlkiscanner.abonnenten_analyse_store import Store


@pytest.mark.parametrize("deep,automatic,expected", [(True, True, 32768),
                                                     (True, False, 16384),
                                                     (False, True, 16384)])
def test_output_room_is_scoped_to_automatic_final_review(deep, automatic, expected):
    class Client:
        has_key = True
        def __init__(self):
            self.requests = []
        def chat(self, prompt, **kwargs):
            self.requests.append(kwargs)
            kwargs["meta_out"].update(total_tokens=100)
            answer = ({"bericht_markdown": "# Vollständiger Endbericht", "neue_pruefhinweise": [],
                       "datenluecken": []} if deep else
                      {"strategietyp": "Trend", "strategie_sicherheit": "plausibel",
                       "martingale_einordnung": "kein_beleg", "kurzurteil": "Belegter Zusatz",
                       "staerken": [], "risiken": [], "pruefhinweise": [], "datenluecken": []})
            return json.dumps({"signal_ref": 1, **answer})

    store = Store()
    store.create({"id": "job"})
    client = Client()
    ai = ki.AnalyseKI(store, "job", config.load_settings(), {"endpruefung_auto": automatic}, client=client)
    answer = ai._ask("abonnenten_top5" if deep else "abonnenten_kurztest",
                     {"signal_ref": 1, "trades": 50, "forensik": {}, "equity": {}},
                     "vollanalyse", {}, [])
    assert answer["signal_ref"] == 1
    assert client.requests[0]["max_tokens"] == expected
    assert client.requests[0]["reasoning_effort"] == ("high" if deep else "low")
    with store.connection() as connection:
        reservation = connection.execute("SELECT reserved FROM calls WHERE run_id='job'").fetchone()[0]
    assert reservation >= 6 * (2 * expected + 2048)
    assert store.spent("job") == 100
