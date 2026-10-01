# -*- coding: utf-8 -*-
"""GLM-Client (Z.ai API, OpenAI-kompatibel) mit Token-Budget und Backoff.

Regeln (AGENTS.md Design-Regeln 1 + 5):
- Das LLM bekommt Forensik-/Kennzahlen-JSONs und kuratierte Beispiel-Trades
  aus `trade_data`, um die Strategie anhand des Handelsverhaltens zu beschreiben.
- Die Engine berechnet die Kennzahlen; das LLM zitiert und interpretiert sie,
  ohne eigene Berechnungen durchzufuehren.
- Token-Budget: `max_total_tokens` je Lauf; vor jedem Aufruf wird der bisher
  gemeldete Verbrauch geprueft. Auch unvollstaendige Antworten zaehlen dazu.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field

import requests

from .. import config as _config
from .. import secrets_store


class LlmError(RuntimeError):
    """Basisfehler des LLM-Layers."""


class LlmNoBalanceError(LlmError):
    """Key gueltig, aber kein Guthaben/Resource-Package (Z.ai-Code 1113)."""


class LlmBudgetError(LlmError):
    """Token-Budget des Laufs erschoepft."""


class LlmIncompleteResponseError(LlmError):
    """Antwort wurde abgebrochen und darf nicht als fertiger Bericht gelten."""


@dataclass
class LlmUsage:
    total_tokens: int = 0
    requests: int = 0
    pro_modell: dict = field(default_factory=dict)

    def add(self, model: str, tokens: int) -> None:
        self.total_tokens += tokens
        self.requests += 1
        self.pro_modell[model] = self.pro_modell.get(model, 0) + tokens


class GlmClient:
    def __init__(self, model_stufe1: str, model_stufe2: str,
                 max_total_tokens: int = 5_000_000, timeout: int = 300,
                 base_url: str | None = None):
        # base_url: Coding-Plan-Endpunkt (Abo-Keys) vs. Standard-API-Endpunkt
        # (Pay-as-you-go-Keys) — falscher Endpunkt => Fehler 1113 "Insufficient
        # balance". Default kommt aus den Settings (config.glm_base_url).
        self.base_url = (base_url or _config.GLM_BASE_URL).rstrip("/")
        self.model_stufe1 = model_stufe1
        self.model_stufe2 = model_stufe2
        self.max_total_tokens = max_total_tokens
        self.timeout = timeout
        self.usage = LlmUsage()
        # Details des letzten Aufrufs — fuer die GUI-Anzeige "was macht das LLM"
        self.last_call: dict = {}
        # Trade- und Risiko-Analyse laufen parallel; Usage/last_call absichern.
        self._lock = threading.Lock()
        # Reservierung laufender Calls (Review T1/2 29.09., M5): Der Budget-
        # Check lief vor dem HTTP-Call, die Abrechnung erst nach der Antwort —
        # zwei parallele Threads konnten beide passieren. Die konservative
        # Obergrenze jedes Calls (max_tokens + Prompt-Schätzung) wird vor dem
        # Call reserviert und nach der Abrechnung freigegeben; die Summe aus
        # verbrauchten + reservierten Tokens haelt das Budget hart ein.
        self._inflight_tokens = 0

    @property
    def has_key(self) -> bool:
        return bool(secrets_store.get_secret("glm_api_key"))

    def _headers(self) -> dict:
        key = secrets_store.get_secret("glm_api_key")
        if not key:
            raise LlmError("Kein GLM-API-Key gesetzt (Admin-Bereich oder GLM_API_KEY).")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def chat(self, prompt: str, system: str = "", model: str | None = None,
             stufe: int = 1, temperature: float = 0.4,
             max_tokens: int = 1600, meta_out: dict | None = None) -> str:
        """Ein Chat-Completion. Wirft klar benannte Fehler (Key/Guthaben/Budget).

        meta_out: optionaler Dict, der unter Lock mit den Call-Metadaten
        gefuellt wird — noetig bei parallelen Aufrufen (last_call allein rasant).
        """
        model = model or (self.model_stufe1 if stufe == 1 else self.model_stufe2)
        # Konservative Reservierung: Antwort-Limit plus Prompt-Obergrenze
        # (Bytes/3 deckt bytebasierte Tokenizer nach oben ab). Muss VOR dem
        # Budget-Check stehen, sonst buchen parallele Calls gemeinsam über.
        reservierung = max_tokens + len(prompt.encode("utf-8")) // 3 + 1024
        with self._lock:
            if self.usage.total_tokens + self._inflight_tokens + reservierung \
                    > self.max_total_tokens:
                raise LlmBudgetError(
                    f"Token-Budget erschoepft ({self.max_total_tokens} je Lauf; "
                    f"{self.usage.total_tokens} verbraucht, "
                    f"{self._inflight_tokens} fuer laufende Aufrufe reserviert). "
                    "Budget im Admin-Bereich erhoehen oder weniger Kandidaten auswerten.")
            self._inflight_tokens += reservierung

        verrechnet = False
        try:
            body = {
                "model": model,
                "messages": ([{"role": "system", "content": system}] if system else [])
                + [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            last_error: Exception | None = None
            length_retry_offen = True
            verworfene_tokens = 0   # F8 (Fremd-Review 01.10.)
            for attempt in range(3):
                start = time.monotonic()
                # Ein Transportfehler darf nicht den gesamten Signal-Lauf abbrechen.
                # Pro HTTP-Aufruf genau eine Wiederholung, dann ein LlmError.
                for transport_attempt in range(2):
                    try:
                        r = requests.post(f"{self.base_url}/chat/completions",
                                          headers=self._headers(), data=json.dumps(body),
                                          timeout=self.timeout)
                        break
                    except requests.RequestException as exc:
                        if transport_attempt:
                            raise LlmError(
                                f"GLM-Verbindungsfehler nach 2 Versuchen: "
                                f"{type(exc).__name__}: {exc}") from exc
                        time.sleep(5)
                if r.status_code >= 400:
                    try:
                        err = r.json().get("error", {})
                    except ValueError:
                        err = {}
                    code = str(err.get("code") or "")
                    if code == "1113":
                        raise LlmNoBalanceError(
                            "GLM-Key gueltig, aber kein Kontingent auf diesem Endpunkt "
                            f"(Z.ai-Code {code}). Bei Abo-Keys (GLM Coding "
                            "Plan) muss der Coding-Endpunkt gesetzt sein "
                            "(api.z.ai/api/coding/paas/v4), bei Guthaben-Keys der "
                            "Standard-Endpunkt (api.z.ai/api/paas/v4) — im Admin-"
                            "bereich umstellbar, ggf. dort aufladen.")
                    # 1302 bezeichnet das Parallelitätslimit, nicht fehlendes Guthaben.
                    # https://docs.z.ai/api-reference/api-code
                    if r.status_code == 429 or code == "1302":
                        last_error = LlmError(
                            f"GLM-Drosselung (HTTP {r.status_code}, Code {code or 'unbekannt'}): "
                            f"{r.text[:200]}")
                        if attempt < 2:
                            time.sleep(5 * (attempt + 1))
                        continue
                    raise LlmError(f"GLM-API HTTP {r.status_code}: {r.text[:300]}")
                try:
                    data = r.json()
                except ValueError as exc:
                    raise LlmError(
                        f"GLM-API lieferte kein JSON (HTTP {r.status_code}): "
                        f"{r.text[:200]!r}") from exc
                try:
                    choice0 = data["choices"][0]
                    content = (choice0.get("message") or {}).get("content") or ""
                    finish = choice0.get("finish_reason")
                except (KeyError, IndexError, TypeError) as exc:
                    raise LlmError(
                        f"GLM-API-Antwort ohne gueltige choices: {str(data)[:200]}") from exc
                usage = data.get("usage", {})
                call_meta = {
                    "model": model,
                    # total_tokens = Kosten DIESES Calls (M3, Review T1/2 29.09.):
                    #usage.total_tokens ist der kumulierte Lauf-Zahler und darf
                    # fuer store_analysis/Journal nicht verwendet werden.
                    "total_tokens": int(usage.get("total_tokens", 0)),
                    "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                    "completion_tokens": int(usage.get("completion_tokens", 0)),
                    "reasoning_tokens": int((usage.get("completion_tokens_details") or {})
                                            .get("reasoning_tokens", 0) or 0),
                    "dauer_s": round(time.monotonic() - start, 1),
                    "finish_reason": finish,
                    "zeichen": len(content),
                    "prompt_zeichen": len(prompt),
                }
                with self._lock:
                    # Reservierung gegen die echte (kleinere) Nutzung aufloesen
                    self._inflight_tokens -= reservierung
                    verrechnet = True
                    self.usage.add(model, int(usage.get("total_tokens", 0)))
                    self.last_call = call_meta
                    if meta_out is not None:
                        # F8: jeder bezahlte Versuch zaehlt — die Tokens
                        # verworfener length-Retries aufsummieren, statt den
                        # letzten Versuch allein zu speichern.
                        meta_out.clear()
                        meta_out.update(call_meta)
                        if verworfene_tokens:
                            meta_out["total_tokens"] = (
                                int(call_meta.get("total_tokens", 0))
                                + verworfene_tokens)
                            meta_out["verworfene_retry_tokens"] = verworfene_tokens
                if finish not in (None, "stop"):
                    # F-11 (Review 29.09.): finish_reason=length ist BEZAHLT
                    # und wurde bisher verworfen — ein einmaliger Retry mit
                    # doppeltem Ausgabelimit (neue Reservierung, Budget
                    # geprueft) rettet den Bericht, statt ihn jeden Lauf
                    # erneut zu bezahlen und zu verlieren.
                    if finish == "length" and length_retry_offen:
                        length_retry_offen = False
                        verworfene_tokens += int(usage.get("total_tokens", 0))
                        max_tokens = min(max_tokens * 2, 262_144)
                        neue_reservierung = (max_tokens
                                             + len(prompt.encode("utf-8")) // 3
                                             + 1024)
                        with self._lock:
                            if (self.usage.total_tokens
                                    + self._inflight_tokens
                                    + neue_reservierung > self.max_total_tokens):
                                raise LlmIncompleteResponseError(
                                    f"Unvollständige Antwort von {model} "
                                    "(finish_reason=length); Retry-Budget "
                                    "reicht nicht — Limit im Admin-Bereich "
                                    "erhöhen.")
                            self._inflight_tokens += neue_reservierung
                        reservierung = neue_reservierung
                        verrechnet = False
                        body["max_tokens"] = max_tokens
                        continue
                    raise LlmIncompleteResponseError(
                        f"Unvollständige Antwort von {model} (finish_reason={finish}). "
                        "Nicht als fertiger Bericht gespeichert; bei length das "
                        "Ausgabelimit erhöhen oder den Bericht kürzer anfordern.")
                if not content:
                    raise LlmError(
                        f"Leere Antwort von {model} (finish_reason={finish}, "
                        f"completion_tokens={call_meta['completion_tokens']}). "
                        "Moegliche Ursache: Reasoning hat das max_tokens-Budget "
                        "aufgebraucht — Limit erhoehen.")
                return content
            raise last_error or LlmError("GLM-Aufruf fehlgeschlagen.")
        finally:
            # Fehler VOR der Abrechnung: Reservierung zurueckgeben, sonst
            # vergiftet jeder fehlgeschlagene Call das Budget.
            if not verrechnet:
                with self._lock:
                    self._inflight_tokens -= reservierung

    def test_connection(self) -> dict:
        """Mini-Test fuer den Admin-Bereich.

        max_tokens=256: die glm-5.x-Modelle verbrauchen Reasoning-Tokens,
        bevor sichtbarer Content entsteht — zu kleine Werte liefern leere
        Antworten, obwohl der Aufruf klappt.
        """
        content = self.chat("Antworte mit genau einem Wort: Test",
                            model=self.model_stufe1, stufe=1, max_tokens=2048)
        return {"ok": True, "antwort": content.strip(), "usage": {
            "total_tokens": self.usage.total_tokens,
            "pro_modell": self.usage.pro_modell}}
