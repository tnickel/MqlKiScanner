# -*- coding: utf-8 -*-
"""GLM-Client (Z.ai API, OpenAI-kompatibel) mit Token-Budget und Backoff.

Regeln (AGENTS.md Design-Regeln 1 + 5):
- Das LLM bekommt NUR fertige Forensik-/Kennzahlen-JSONs, nie Roh-Trades.
- Alle Zahlen stammen aus der Engine; das LLM formuliert und interpretiert.
- Kosten-Budget: `max_total_tokens` je Lauf; Budgetueberschreitung -> LlmBudgetError.
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
        with self._lock:
            if self.usage.total_tokens >= self.max_total_tokens:
                raise LlmBudgetError(
                    f"Token-Budget erschoepft ({self.max_total_tokens} je Lauf). "
                    "Budget im Admin-Bereich erhoehen oder weniger Kandidaten auswerten.")

        body = {
            "model": model,
            "messages": ([{"role": "system", "content": system}] if system else [])
            + [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        last_error: Exception | None = None
        for attempt in range(3):
            start = time.monotonic()
            r = requests.post(f"{self.base_url}/chat/completions",
                              headers=self._headers(), data=json.dumps(body),
                              timeout=self.timeout)
            if r.status_code == 429:
                try:
                    err = r.json().get("error", {})
                except ValueError:
                    err = {}
                code = str(err.get("code") or "")
                if code in ("1113", "1302"):
                    raise LlmNoBalanceError(
                        "GLM-Key gueltig, aber kein Kontingent auf diesem Endpunkt "
                        f"(Z.ai-Code {code}). Bei Abo-Keys (GLM Coding "
                        "Plan) muss der Coding-Endpunkt gesetzt sein "
                        "(api.z.ai/api/coding/paas/v4), bei Guthaben-Keys der "
                        "Standard-Endpunkt (api.z.ai/api/paas/v4) — im Admin-"
                        "bereich umstellbar, ggf. dort aufladen.")
                time.sleep(5 * (attempt + 1))
                last_error = LlmError(f"HTTP 429: {r.text[:200]}")
                continue
            if r.status_code >= 400:
                try:
                    err = r.json().get("error", {})
                except ValueError:
                    err = {}
                code = str(err.get("code") or "")
                if code in ("1113", "1302"):
                    raise LlmNoBalanceError(
                        "GLM-Key gueltig, aber kein Kontingent auf diesem Endpunkt "
                        f"(Z.ai-Code {code}). Bei Abo-Keys (GLM Coding "
                        "Plan) muss der Coding-Endpunkt gesetzt sein "
                        "(api.z.ai/api/coding/paas/v4), bei Guthaben-Keys der "
                        "Standard-Endpunkt (api.z.ai/api/paas/v4) — im Admin-"
                        "bereich umstellbar, ggf. dort aufladen.")
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
                self.usage.add(model, int(usage.get("total_tokens", 0)))
                self.last_call = call_meta
                if meta_out is not None:
                    meta_out.clear()
                    meta_out.update(call_meta)
            if not content:
                raise LlmError(
                    f"Leere Antwort von {model} (finish_reason={finish}, "
                    f"completion_tokens={call_meta['completion_tokens']}). "
                    "Moegliche Ursache: Reasoning hat das max_tokens-Budget "
                    "aufgebraucht — Limit erhoehen.")
            return content
        raise last_error or LlmError("GLM-Aufruf fehlgeschlagen.")

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
