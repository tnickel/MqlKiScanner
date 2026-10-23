"""Two evidence-bound prompts, complete trade coverage and durable paid replies."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from . import config, db, parser
from .abonnenten_analyse_store import Store, dumps
from .llm import client as llm_client, prompts, prompt_fill

MAX_PROMPT_BYTES = 240_000
MAX_TRADE_BLOCK_BYTES = 80_000
TRADE_OVERLAP = 8
MAX_EVIDENCE_CONTRACT_BYTES = 8_192
MAX_EVIDENCE_REGISTER_BYTES = 4_096
MAX_EVIDENCE_REGISTER_ENTRIES = 80
FACTS_PAYLOAD_VERSION = 2
MAX_FACT_LIST_ITEMS = 100


class Angehalten(RuntimeError):
    pass


def digest(value) -> str:
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


def compact(value):
    """Bound fact lists explicitly; raw trades travel through their own blocks."""
    if isinstance(value, dict):
        return {str(k): compact(v) for k, v in value.items()
                if k not in {"punkte", "equity_curve", "balance_curve", "bars", "rohkurse", "trades"}
                or not isinstance(v, (list, tuple))}
    if isinstance(value, (list, tuple)):
        items = [compact(v) for v in value[:MAX_FACT_LIST_ITEMS]]
        if len(value) <= MAX_FACT_LIST_ITEMS:
            return items
        return {"eintraege": items, "abdeckung": {
            "vollstaendig": False, "anzahl_gesamt": len(value),
            "enthaltene_indizes": [0, MAX_FACT_LIST_ITEMS - 1],
            "ausgelassene_indizes": [MAX_FACT_LIST_ITEMS, len(value) - 1],
            "indexbasis": 0}}
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def trade_rows(entry: dict) -> list[dict]:
    path, sha = entry.get("trades_path"), entry.get("trades_sha256")
    if not path or not sha:
        raise llm_client.LlmError("Kein belegter Trade-Snapshot für die KI")
    db.verify_trade_file(path, sha)
    parsed = parser.load_export(path, plattform_positions=entry.get("plattform_trades"))
    rows = []
    for index, trade in enumerate(parsed.trades, 1):
        rows.append({"trade_ref": f"{sha}:{index}", "trade_index": index,
                     "open": trade.open_time.isoformat(), "close": trade.close_time.isoformat(),
                     "symbol": trade.symbol, "direction": trade.direction,
                     "volume": trade.volume, "entry": trade.entry_price, "exit": trade.exit_price,
                     "profit": trade.profit, "commission": trade.commission, "swap": trade.swap,
                     "sl": trade.sl, "tp": trade.tp,
                     "comment": "".join(c for c in (trade.comment or "") if c.isprintable())[:160]})
    if len(rows) != entry.get("trades"):
        raise llm_client.LlmError("Tradezahl stimmt nicht mit der berechneten Grundlage überein")
    # Preserve occurrence identities before sorting; descending exports must
    # not reverse loss/lot sequences, identical true positions remain distinct.
    rows.sort(key=lambda row: (row["open"], row["close"], row["trade_index"]))
    return rows


def _trade_block(rows, start, end, segment_id, overlap=TRADE_OVERLAP):
    return {"segment_id": segment_id, "rows": rows[max(0, start-overlap):end],
            "primary_refs": [r["trade_ref"] for r in rows[start:end]],
            "overlap_refs": [r["trade_ref"] for r in rows[max(0, start-overlap):start]]}


def segments(rows: list[dict], *, max_bytes=MAX_TRADE_BLOCK_BYTES, overlap=TRADE_OVERLAP) -> list[dict]:
    """Partition every occurrence; count rows, manifests, overlap and framing.

    One indivisible row can exceed this soft block target. Its actual filled
    prompt still has to pass the unchanged hard limit before any model call.
    """
    if not rows:
        raise ValueError("Keine Trades für die KI")
    row_sizes, ref_sizes = [0], [0]
    for row in rows:
        row_sizes.append(row_sizes[-1] + len(dumps(row).encode("utf-8")) + 1)
        ref_sizes.append(ref_sizes[-1] + len(dumps(row["trade_ref"]).encode("utf-8")) + 1)
    blocks, start = [], 0
    while start < len(rows):
        end = start
        overlap_start = max(0, start-overlap)
        framing = len(dumps({"segment_id": len(blocks)+1, "rows": [],
                             "primary_refs": [], "overlap_refs": []}).encode("utf-8"))
        while end < len(rows):
            size = (framing + row_sizes[end+1] - row_sizes[overlap_start] - 1
                    + ref_sizes[end+1] - ref_sizes[start] - 1
                    + (ref_sizes[start] - ref_sizes[overlap_start] - 1 if start > overlap_start else 0))
            if end > start and size > max_bytes:
                break
            end += 1
        blocks.append(_trade_block(rows, start, end, len(blocks)+1, overlap))
        start = end
    expected = [r["trade_ref"] for r in rows]
    actual = [ref for b in blocks for ref in b["primary_refs"]]
    if actual != expected or len(set(actual)) != len(actual):
        raise ValueError("KI-Segmentierung deckt Trade-Referenzen nicht genau ab")
    return blocks


def json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = "\n".join(text.splitlines()[1:-1])
    try:
        def invalid_constant(value):
            raise ValueError(f"Ungültige JSON-Zahl: {value}")
        answer = json.loads(text, parse_constant=invalid_constant)
    except (TypeError, ValueError) as exc:
        raise llm_client.LlmError("KI-Antwort ist kein gültiges JSON; Rohantwort bleibt gespeichert") from exc
    if not isinstance(answer, dict):
        raise llm_client.LlmError("KI-Antwort muss ein JSON-Objekt sein")
    return answer


def _martingale_contract(entry):
    flag = entry.get("forensik", {}).get("forensics", {}).get("martingale", {}).get("flag")
    return {"geliefertes_code_flag": flag,
            "code_belegt_bedeutet": "Der Code hat Martingale positiv festgestellt; niemals nur die Existenz eines Tests oder eines negativen Ergebnisses.",
            "zulaessige_enumwerte": ["code_belegt"] if flag is True else
                ["kein_beleg", "verdacht", "nicht_beurteilbar"],
            "auswahlregel": "Bei flag=true zwingend code_belegt. Bei false oder fehlendem Flag ist code_belegt verboten; "
                "kein_beleg, verdacht oder nicht_beurteilbar passend zur gelieferten Evidenz wählen."}


def validate(answer: dict, entry: dict, *, deep=False, segment=False) -> dict:
    if isinstance(answer.get("signal_ref"), bool) or answer.get("signal_ref") != entry["signal_ref"]:
        raise llm_client.LlmError("KI-Antwort gehört nicht zur beauftragten Quellenidentität")
    if deep and segment:
        if (not isinstance(answer.get("handelsmuster"), str) or not answer["handelsmuster"].strip()
                or not isinstance(answer.get("segment_id"), (str, int))
                or isinstance(answer.get("segment_id"), bool)
                or any(not isinstance(answer.get(key), list) for key in
                       ("staerken", "risiken", "widersprueche", "datenluecken", "beleg_refs"))):
            raise llm_client.LlmError("Top-5-Segmentantwort ohne vollständige strukturierte Analyse")
        return answer
    required = ({"bericht_markdown": str, "neue_pruefhinweise": list, "datenluecken": list}
                if deep else {"strategietyp": str, "kurzurteil": str, "staerken": list,
                              "risiken": list, "pruefhinweise": list, "datenluecken": list})
    for key, cls in required.items():
        if not isinstance(answer.get(key), cls) or (cls is str and not answer[key].strip()):
            raise llm_client.LlmError(f"KI-Antwort ohne gültiges Pflichtfeld {key}")
    if not deep:
        if answer.get("strategie_sicherheit") not in {"belegt", "plausibel", "unklar"}:
            raise llm_client.LlmError("Ungültige Strategie-Sicherheit im KI-Kurztest")
        evidence = answer.get("martingale_einordnung")
        contract = _martingale_contract(entry)
        if evidence not in contract["zulaessige_enumwerte"]:
            raise llm_client.LlmError(
                "Martingale-Einordnung der KI widerspricht dem gelieferten Codebefund: "
                f"flag={dumps(contract['geliefertes_code_flag'])}, "
                f"martingale_einordnung={dumps(evidence)}; "
                f"zulässige Enumwerte={dumps(contract['zulaessige_enumwerte'])}. "
                "code_belegt bedeutet ausschließlich positiv festgestelltes Martingale, kein negatives Testergebnis")
    return answer


def _fact_refs(value, prefix=""):
    refs = set()
    if isinstance(value, dict):
        if prefix and value:
            refs.add(prefix)
        for key, child in value.items():
            refs.update(_fact_refs(child, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        if prefix and value:
            refs.add(prefix)
        for index, child in enumerate(value):
            refs.update(_fact_refs(child, f"{prefix}[{index}]"))
    elif prefix:
        # An explicitly delivered null is evidence of a missing measurement.
        refs.add(prefix)
    return refs


_COMPARISON_FIELDS = ("retdd_jahr", "equity_dd_pct", "auswahlwert", "rang", "dauer_monate",
                      "abo_perzentil", "signal_ref", "quelle", "name")


def _comparison_refs(comparison):
    """Only the coordinator's primitive code comparison, never model findings."""
    if not isinstance(comparison, list):
        return []
    refs = []
    # Field-first ordering covers the most useful metrics across all finalists
    # before spending the bounded register on less useful identity labels.
    for field in _COMPARISON_FIELDS:
        for index, row in enumerate(comparison):
            if not isinstance(row, dict) or field not in row:
                continue
            value = row[field]
            if value is not None and (isinstance(value, bool) or
                    not isinstance(value, str if field in {"quelle", "name"} else (int, float))):
                continue
            refs.append(f"vergleich[{index}].{field}")
    return refs


def _evidence_register(facts, candidate, comparison=None):
    """Small, deterministic aliases to supplied data, not a second facts tree.

    The explicit $ target denotes the root of forensik_json. Deeper facts
    remain covered by their registered containers and may still be cited by
    their exact legacy paths. Lists are never enumerated into this register.
    """
    fact_paths = ["$"] if isinstance(facts, dict) and facts else []

    def containers(value, prefix="", depth=0):
        if not isinstance(value, dict) or depth >= 3:
            return
        for key in sorted(value):
            child = value[key]
            path = f"{prefix}.{key}" if prefix else str(key)
            is_container = isinstance(child, (dict, list))
            if (depth == 0 and (not is_container or child)) or (is_container and child):
                fact_paths.append(path)
            if isinstance(child, dict):
                containers(child, path, depth + 1)

    containers(facts)
    fact_paths = fact_paths[:1] + sorted(fact_paths[1:], key=lambda p: (p.count("."), p))
    candidate_refs = _fact_refs(candidate, "kandidat")
    candidate_paths = (["kandidat"] if "kandidat" in candidate_refs else []) + [
        f"kandidat.{key}" for key in sorted(candidate) if f"kandidat.{key}" in candidate_refs]
    register = {}
    for prefix, paths, maximum in (("F", fact_paths, 40), ("K", candidate_paths, 20),
                                    ("V", _comparison_refs(comparison), 40)):
        index = 0
        for path in paths:
            if index >= maximum or len(register) >= MAX_EVIDENCE_REGISTER_ENTRIES:
                break
            # Long unusual source keys remain in the original facts, under a
            # registered ancestor. They do not inflate this copying aid.
            if len(path.encode("utf-8")) > 160:
                continue
            key = f"{prefix}{index + 1:03}"
            if len(dumps({**register, key: path}).encode("utf-8")) > MAX_EVIDENCE_REGISTER_BYTES:
                continue
            register[key] = path
            index += 1
    return register


def _trade_evidence_refs(trade_data, parts, short, verified):
    """Only refs actually supplied in this request, or its full coverage manifest.

    Model-authored references in earlier findings must still belong to the
    verified snapshot. No second unbounded trade list is added to the prompt.
    """
    refs = set()

    def supplied(value):
        if isinstance(value, str):
            if value in verified:
                refs.add(value)
        elif isinstance(value, dict):
            for child in value.values():
                supplied(child)
        elif isinstance(value, list):
            for child in value:
                supplied(child)

    supplied(trade_data)
    supplied(parts)
    supplied(short)
    if isinstance(trade_data, dict) and trade_data.get("abdeckung_vollstaendig") is True:
        refs.update(verified)
    return refs


def validate_evidence(answer, allowed):
    """Reject invented references; quoted source text never authorizes actions."""
    for field in ("staerken", "risiken", "widersprueche", "pruefhinweise", "neue_pruefhinweise"):
        items = answer.get(field, [])
        if not isinstance(items, list):
            raise llm_client.LlmError(f"Ungültige Belegliste {field}")
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                raise llm_client.LlmError(f"Ungültiger Eintrag in {field}")
            refs = item.get("beleg_refs")
            if not isinstance(refs, list) or not refs:
                raise llm_client.LlmError(
                    f"Fehlender Fakten-/Tradebeleg in {field}[{index}].beleg_refs; eine nichtleere Liste exakter Referenzen ist erforderlich")
            invalid = [ref for ref in refs if not isinstance(ref, str) or ref not in allowed]
            if invalid:
                details = [ref[:180] if isinstance(ref, str) else f"Typ {type(ref).__name__}"
                           for ref in invalid[:8]]
                raise llm_client.LlmError(
                    f"Unbekannter Fakten-/Tradebeleg in {field}[{index}].beleg_refs: {dumps(details)}. "
                    "Nur exakt vorhandene Pfade oder unveränderte trade_ref-Werte ohne Zusatz verwenden")
    return answer


class AnalyseKI:
    def __init__(self, store: Store, run_id: str, settings: dict, profile: dict,
                 *, should_stop=lambda: False, log=None, client=None):
        self.store, self.run_id, self.settings, self.profile = store, run_id, settings, profile
        self.should_stop, self.log = should_stop, log or (lambda text: None)
        self.client = client or llm_client.GlmClient(
            model_stufe1=settings.get("model_stufe1", config.MODEL_STUFE1),
            model_stufe2=settings.get("model_stufe2", config.MODEL_STUFE2),
            max_total_tokens=int(settings.get("llm_max_total_tokens", 10_000_000)),
            base_url=settings.get("glm_base_url"))
        if client is None:
            from .agenten import budget
            budget.attach(self.client, settings, rolle="abonnenten_analyse")
            self.client.budget_tickets = []

    def _charged_tokens(self, offset, meta):
        tickets = getattr(self.client, "budget_tickets", None)
        if isinstance(tickets, list) and tickets[offset:]:
            ids = tickets[offset:]
            with db._connect() as connection:
                values = connection.execute(
                    "SELECT CASE WHEN abgeschlossen=1 THEN tokens ELSE reserviert END "
                    "FROM agenten_budget_versuche WHERE id IN (" + ",".join("?" for _ in ids) + ")", ids).fetchall()
            if len(values) == len(ids):
                return sum(int(row[0]) for row in values)
            return None  # retain the reservation if any receipt is missing
        return meta.get("total_tokens")

    def _prompt(self, key, entry, processing, trade_data, parts, *, short=None, comparison=None):
        """The exact same filled prompt is used for sizing and for paid calls."""
        facts = compact({"forensik": entry.get("forensik", {}), "equity": entry.get("equity", {}),
                         "messhinweis": entry.get("messhinweis"),
                         **{k: entry.get(k) for k in ("retdd_jahr", "retdd_zeitraum", "equity_dd_pct",
                            "dauer_monate", "trades", "kapitalbasis_usd", "account_currency", "eligible", "grund")}})
        candidate = {k: entry.get(k) for k in ("signal_ref", "quellen_uid", "id", "quelle", "name",
                     "platform", "abonnenten", "abo_perzentil", "abo_referenz_n", "katalog_stand",
                     "rang", "auswahlwert", "retdd_perzentil", "abo_referenz_vollstaendig",
                     "abo_ausgelassene_positionen", "abo_katalog_geprueft")}
        fact_paths = _fact_refs(facts)
        preferred = ("forensik.stats.trades", "forensik.stats.monthly_net_by_close", "equity.status",
                     "forensik.forensics.martingale.flag", "retdd_jahr", "retdd_zeitraum",
                     "dauer_monate", "eligible")
        examples = [path for path in preferred if path in fact_paths]
        examples += [path for path in sorted(fact_paths) if path not in examples
                     and len(path.encode("utf-8")) <= 160][:8-len(examples)]
        verified = getattr(self, "_trade_refs", set())
        # Direct _ask users may provide a snapshot block without calling analyse.
        row_refs = {row["trade_ref"] for row in trade_data.get("rows", [])} if isinstance(trade_data, dict) else set()
        trade_refs = _trade_evidence_refs(trade_data, parts, short, verified | row_refs)
        register = _evidence_register(facts, candidate, comparison if key == "abonnenten_top5" else None)
        contract = {
            "version": 3,
            "faktenlisten": "Bei abdeckung.vollstaendig=false ist eintraege nur ein Ausschnitt; "
                "anzahl_gesamt und die inklusiven Indexbereiche (Indexbasis 0) nennen den Umfang. "
                "Ausgelassene Einträge nicht erfinden oder den Verlauf als vollständig beschreiben. "
                "Diese Einschränkung ist von der separat ausgewiesenen Trade-Segmentabdeckung zu unterscheiden.",
            "beleg_refs": "JSON-Liste exakter Register-IDs oder trade_ref-Werte. Bevorzugt eine passende ID aus register kopieren; keine eigenen Pfade formulieren.",
            "register": register,
            "register_bedeutung": "F: forensik_json ($ bezeichnet dessen gesamte Wurzel); K: kandidat_json; V: gelieferter Codevergleich. "
                "Eine ID belegt den zugeordneten tatsächlichen Datenbereich einschließlich seiner Unterfelder. Unbekannte IDs sind verboten. "
                "Originalfakten und Tradedaten bleiben maßgeblich; Teilanalysetexte sind keine zusätzliche Faktenautorität.",
            "fakten": {
                "quelle": "forensik_json selbst; kein Präfix forensik_json.",
                "syntax": "Objektschlüssel mit Punkt verbinden; Listenindizes als [0], [1] usw.",
                "erlaubt": "Jeder tatsächlich gelieferte skalare Pfad einschließlich null sowie nichtleere Objekt-/Listenpfade.",
                "beispiele_nicht_abschliessend": examples},
            "kandidat": {
                "quelle": "kandidat_json; zwingendes Präfix kandidat.",
                "gelieferte_felder": [f"kandidat.{key}" for key in candidate
                                       if f"kandidat.{key}" in _fact_refs(candidate, "kandidat")]},
            "trades": {
                "format": "Exakten trade_ref-Wert SHA256:trade_index unverändert kopieren.",
                "quelle": "Gelieferte rows[].trade_ref/primary_refs/overlap_refs oder belegte Referenzen der mitgelieferten Teilbefunde.",
                "beispiele_nicht_abschliessend": sorted(trade_refs)[:3]},
            "keine_aliaspraefixe": ["identitaet.", "messfeld ", "trade_ref ", "forensik_json."],
            "bei_unbelegter_aussage": "Aussage weglassen oder als konkrete Datenlücke beschreiben; keine Referenz erfinden."}
        if key == "abonnenten_top5" and comparison:
            contract["vergleich"] = {"quelle": "vergleich_json; V-IDs zeigen ausschließlich auf gelieferte Codewerte.",
                                      "codefelder": list(_COMPARISON_FIELDS)}
        if isinstance(trade_data, dict) and trade_data.get("abdeckung_vollstaendig") is True and verified:
            contract["trades"]["vollstaendiges_manifest"] = {
                "trades_sha256": entry["trades_sha256"], "trade_index_von": 1,
                "trade_index_bis": entry["trades"]}
        if len(dumps(contract).encode("utf-8")) > MAX_EVIDENCE_CONTRACT_BYTES:
            raise llm_client.LlmError("Belegvertrag überschreitet den sicheren Umfang; keine Fakten oder Trades wurden gekürzt")
        prompt = prompt_fill.build_abonnenten_prompt(
            key, laufprofil_json=dumps({**self.profile, "verarbeitung": processing,
                                       "belegvertrag": contract, "martingale_vertrag": _martingale_contract(entry)}),
            kandidat_json=dumps(candidate), forensik_json=dumps(facts), trades_json=dumps(trade_data),
            teilanalysen_json=dumps(parts), kurztest_json=dumps(short or {}), vergleich_json=dumps(comparison or []))
        return prompt, facts, candidate

    def _fit_blocks(self, key, entry, rows, *, short=None, comparison=None):
        """Enlarge ordinary blocks, then split only where the filled prompt needs it."""
        proposed = segments(rows)
        def fits(processing, block):
            prompt, _, _ = self._prompt(key, entry, processing, block, [],
                                        short=short, comparison=comparison)
            return len(prompt.encode("utf-8")) <= MAX_PROMPT_BYTES
        if len(proposed) == 1 and fits("vollanalyse", {
                "trades_sha256": entry["trades_sha256"], "trades_total": len(rows), "rows": rows}):
            return proposed
        blocks, start = [], 0
        for proposed_block in proposed:
            boundary = start + len(proposed_block["primary_refs"])
            while start < boundary:
                if self.should_stop():
                    raise Angehalten("Stop angefordert")
                entire = _trade_block(rows, start, boundary, len(blocks)+1)
                if fits("segment", entire):
                    blocks.append(entire)
                    start = boundary
                    continue
                # Binary search on the actual UTF-8 prompt, including user
                # template repetitions, facts, references and eight-row overlap.
                lower, upper, best = start+1, boundary, None
                while lower <= upper:
                    end = (lower+upper)//2
                    block = _trade_block(rows, start, end, len(blocks)+1)
                    if fits("segment", block):
                        best = block
                        lower = end+1
                    else:
                        upper = end-1
                if best is None:
                    raise llm_client.LlmError(
                        "Ein Trade mit Randüberlappung und vollständiger Faktenbasis überschreitet "
                        "den sicheren Promptumfang; keine Trades oder Belege wurden gekürzt")
                blocks.append(best)
                start += len(best["primary_refs"])
        if [ref for block in blocks for ref in block["primary_refs"]] != [row["trade_ref"] for row in rows]:
            raise llm_client.LlmError("Dynamische KI-Segmentierung deckt nicht alle Trades genau ab")
        return blocks

    def _ask(self, key, entry, processing, trade_data, parts, *, short=None, comparison=None):
        if self.should_stop():
            raise Angehalten("Stop angefordert")
        prompt, facts, candidate = self._prompt(key, entry, processing, trade_data, parts,
                                               short=short, comparison=comparison)
        allowed = _fact_refs(facts) | _fact_refs(candidate, "kandidat")
        code_comparison = comparison if key == "abonnenten_top5" else None
        register = _evidence_register(facts, candidate, code_comparison)
        self._last_evidence_register = register
        allowed.update(register)
        allowed.update(_comparison_refs(code_comparison))
        row_refs = {row["trade_ref"] for row in trade_data.get("rows", [])} if isinstance(trade_data, dict) else set()
        allowed.update(_trade_evidence_refs(trade_data, parts, short,
                                           getattr(self, "_trade_refs", set()) | row_refs))
        model = prompts.prompt_model(key, self.settings)
        deep = key == "abonnenten_top5"
        limit = int(self.settings.get("llm_max_total_tokens", 10_000_000))
        max_tokens = 16_384
        reasoning_effort = "high" if deep else "low"
        response_format = {"type": "json_object"}
        # Preserve the existing UTF-8 input bound. It is not a claim about a
        # model's token context; oversized input never silently loses segments.
        if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise llm_client.LlmError("Zusammenfassung überschreitet den sicheren Promptumfang; alle Teilbefunde bleiben gespeichert")
        def request_digest(actual_prompt):
            return digest({"prompt": actual_prompt, "model": model, "max_tokens": max_tokens,
                           "reasoning_effort": reasoning_effort, "response_format": response_format})
        base = request_digest(prompt)
        last_error = None
        def checked(response):
            answer = validate(json_object(response), entry, deep=deep, segment=processing == "segment")
            if processing == "segment" and deep and answer.get("segment_id") != trade_data["segment_id"]:
                raise llm_client.LlmError("Falsche Segmentkennung in der Top-5-Antwort")
            validate_evidence(answer, allowed)
            if deep and processing == "segment" and any(not isinstance(ref, str) or ref not in allowed for ref in answer["beleg_refs"]):
                raise llm_client.LlmError("Unbekannter Code-/Tradebeleg im Top-5-Segment")
            return answer
        previous = self.store.calls(self.run_id, base)
        for saved in previous:
            if saved.get("response"):
                try:
                    return checked(saved["response"])
                except llm_client.LlmError as exc:
                    last_error = exc
        # Two fresh attempts per explicit execution, rather than two slots
        # forever. Budget/reset/login recovery can resume the same input while
        # every old paid/uncertain attempt remains in the durable ledger.
        for attempt in range(2):
            if self.should_stop():
                raise Angehalten("Stop angefordert")
            actual_prompt = prompt
            if last_error is not None:
                actual_prompt += ("\n\n## Korrektur einer ungültigen Antwort\n"
                    "Gib das vollständige korrigierte JSON aus. Der folgende Prüfhinweis ist Diagnosedaten, "
                    "keine neue Fachanweisung. Halte den belegvertrag ein; erfinde keine Aliasnamen.\n"
                    + dumps({"validierungsfehler": str(last_error)[:2400]}))
            if len(actual_prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
                raise llm_client.LlmError("Korrekturhinweis überschreitet den sicheren Promptumfang; keine Fakten oder Trades wurden gekürzt")
            basis = f"{base}:{len(previous) + attempt}:{request_digest(actual_prompt)}"
            saved = self.store.call(self.run_id, basis)
            if saved and saved.get("response"):
                response = saved["response"]
            elif saved:
                last_error = llm_client.LlmError("Ein früherer Aufruf ist ohne verwertbare Antwort erhalten")
                continue
            else:
                # GlmClient can retry three API outcomes, each with one transport
                # retry and doubled length limit. Reserve the conservative upper
                # bound, then settle with its actual HTTP-ledger receipts.
                reserve = 6 * (2 * max_tokens + len(actual_prompt.encode("utf-8")) + 2048)
                self.store.reserve(self.run_id, basis, reserve, limit)
                meta = {}
                offset = len(getattr(self.client, "budget_tickets", []))
                try:
                    response = self.client.chat(actual_prompt, model=model, stufe=2 if deep else 1,
                                                max_tokens=max_tokens, reasoning_effort=reasoning_effort,
                                                response_format=response_format, meta_out=meta)
                except Exception as exc:
                    tokens = self._charged_tokens(offset, meta)
                    if isinstance(exc, (llm_client.LlmBudgetError, llm_client.LlmNoBalanceError)) and tokens is None:
                        tokens = 0
                    self.store.finish_call(self.run_id, basis, response="", tokens=tokens,
                                           meta={**meta, "error": str(exc)}, status="error")
                    raise
                tokens = self._charged_tokens(offset, meta)
                self.store.finish_call(self.run_id, basis, response=response,
                                       tokens=tokens if isinstance(tokens, int) and tokens >= 0 else None, meta=meta)
            try:
                return checked(response)
            except llm_client.LlmError as exc:
                last_error = exc
                self.log(f"Ungültige KI-Antwort {entry['quelle']}:{entry['id']} ({attempt+1}/2): {exc}")
        raise last_error or llm_client.LlmError("Keine gültige KI-Antwort")

    def analyse(self, entry: dict, *, deep=False, comparison=None) -> dict:
        rows = trade_rows(entry)
        self._trade_refs = {row["trade_ref"] for row in rows}
        key = "abonnenten_top5" if deep else "abonnenten_kurztest"
        short = entry.get("kurztest") if deep else None
        blocks = self._fit_blocks(key, entry, rows, short=short, comparison=comparison)
        full_data = {"trades_sha256": entry["trades_sha256"], "trades_total": len(rows), "rows": rows}
        if len(blocks) == 1 and len(self._prompt(key, entry, "vollanalyse", full_data, [],
                short=short, comparison=comparison)[0].encode("utf-8")) <= MAX_PROMPT_BYTES:
            answer = self._ask(key, entry, "vollanalyse", full_data, [], short=short, comparison=comparison)
        else:
            parts = []
            for block in blocks:
                self.log(f"{'Top 5' if deep else 'Kurztest'} {entry['name']}: Tradeblock {block['segment_id']}/{len(blocks)}")
                part = self._ask(key, entry, "segment", block, [], short=short, comparison=comparison)
                parts.append({"segment_id": block["segment_id"], "trades": len(block["primary_refs"]),
                              "first_ref": block["primary_refs"][0], "last_ref": block["primary_refs"][-1], "befund": part})
            # Hierarchical summaries keep every segment represented, even for
            # histories larger than one model context. These paid replies are
            # cached with the same prompt/input hash just like trade segments.
            level = 0
            while len(dumps(parts).encode("utf-8")) > 55_000:
                level += 1
                if level > 12:
                    raise llm_client.LlmError("Segmentzusammenfassung konnte nicht ausreichend verdichtet werden")
                groups, group, size = [], [], 0
                for part in parts:
                    length = len(dumps(part).encode("utf-8"))
                    if group and size + length > 25_000:
                        groups.append(group)
                        group, size = [], 0
                    group.append(part)
                    size += length
                if group:
                    groups.append(group)
                reduced = []
                for index, group in enumerate(groups):
                    segment_id = f"aggregation-{level}-{index}"
                    report = self._ask(key, entry, "segment", {"segment_id": segment_id,
                        "aggregation": True, "trades_total": sum(p["trades"] for p in group)}, group,
                        short=short, comparison=comparison)
                    reduced.append({"segment_id": segment_id, "trades": sum(p["trades"] for p in group),
                                    "befund": report})
                parts = reduced
            answer = self._ask(key, entry, "zusammenfassung", {"trades_total": len(rows),
                               "trades_sha256": entry["trades_sha256"], "segmente": len(blocks),
                               "abdeckung_vollstaendig": True}, parts, short=short, comparison=comparison)
        answer["analysegrundlage"] = {"trades_total": len(rows), "trades_ki_abgedeckt": len(rows),
                                      "facts_payload_version": FACTS_PAYLOAD_VERSION,
                                      "segmente": len(blocks), "trades_sha256": entry["trades_sha256"],
                                      "beleg_register": dict(self._last_evidence_register),
                                      "prompt_sha256": hashlib.sha256(prompts.load_prompt(key).encode()).hexdigest()}
        return answer


def report_pdf(entry: dict, run_id: str) -> str:
    from . import pdf_reports
    body = entry["bericht_markdown"]
    if entry.get("abo_referenz_vollstaendig") is False:
        body = ("**Auswahlhinweis:** Der Quellenkatalog enthält ausgelassene API-Positionen. "
                "Rang und Abonnentenrang beziehen sich auf die lesbaren Anbieter; "
                "eine globale Top-200-Auswahl ist nicht bestätigt.\n\n" + body)
    report = pdf_reports.PdfReport(kind="abonnenten_top5", body=body,
        signal_id=entry["id"], signal_name=entry["name"], quelle=entry["quelle"],
        quellen_uid=entry.get("quellen_uid", ""), signal_ref=entry["signal_ref"],
        created_at=entry.get("analyse_at"), model=entry.get("analyse_model"))
    path = config.DATA_DIR / "abonnenten_analyse" / "berichte" / run_id / f"{entry['signal_ref']}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(pdf_reports.render_report_pdf(report))
    temporary.replace(path)
    return str(path)
