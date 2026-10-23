"""Reasoning and JSON options survive retries without changing other callers."""
import json
from unittest.mock import Mock

import pytest
import requests

from mqlkiscanner.llm import client as llm


def response(finish="stop", tokens=30):
    r = requests.Response()
    r.status_code = 200
    r._content = json.dumps({"choices": [{"message": {"content": "{}"},
                                        "finish_reason": finish}],
                             "usage": {"total_tokens": tokens}}).encode()
    return r


def test_explicit_options_are_preserved_across_length_retry(monkeypatch):
    monkeypatch.setattr(llm.secrets_store, "get_secret", lambda _: "synthetic-key")
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    seen = []
    replies = iter([response("length", 20), response("stop", 30)])
    def post(*args, **kwargs):
        seen.append(json.loads(kwargs["data"]))
        return next(replies)
    monkeypatch.setattr(llm.requests, "post", post)
    c = llm.GlmClient("glm-5.3-flash", "glm-5.3", max_total_tokens=10000)
    meta = {}
    assert c.chat("synthetic", max_tokens=16, reasoning_effort="low",
                  response_format={"type": "json_object"}, meta_out=meta) == "{}"
    assert [b["max_tokens"] for b in seen] == [16, 32]
    assert all(b["reasoning_effort"] == "low" and
               b["response_format"] == {"type": "json_object"} for b in seen)
    assert meta["total_tokens"] == 50
    assert meta["reasoning_effort"] == "low"
    assert meta["response_format"] == {"type": "json_object"}


def test_unspecified_options_leave_other_callers_unchanged(monkeypatch):
    monkeypatch.setattr(llm.secrets_store, "get_secret", lambda _: "synthetic-key")
    post = Mock(return_value=response())
    monkeypatch.setattr(llm.requests, "post", post)
    c = llm.GlmClient("m1", "m2")
    c.chat("synthetic")
    body = json.loads(post.call_args.kwargs["data"])
    assert "reasoning_effort" not in body and "response_format" not in body


@pytest.mark.parametrize("options", [
    {"reasoning_effort": "disabled"}, {"reasoning_effort": True},
    {"response_format": {"type": "json_schema"}},
    {"response_format": {"type": "json_object", "extra": 1}},
    {"response_format": "json_object"},
])
def test_invalid_options_fail_before_spending_or_reservation(monkeypatch, options):
    post = Mock(side_effect=AssertionError("unexpected paid request"))
    monkeypatch.setattr(llm.requests, "post", post)
    c = llm.GlmClient("m1", "m2")
    with pytest.raises(ValueError):
        c.chat("synthetic", **options)
    assert not post.called and c._inflight_tokens == 0 and c.usage.total_tokens == 0
