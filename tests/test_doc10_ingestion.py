"""Regression for the request-attempt parameter, without network access."""
from unittest.mock import Mock

import pytest
import requests

from mqlkiscanner.mql5.ratelimit import Mql5ThrottleError
from mqlkiscanner.mql5.session import Mql5Session


@pytest.mark.parametrize("attempts", [0, -1, 0.5, "0", None, False, True])
def test_invalid_attempt_limit_is_rejected_before_request_or_wait(monkeypatch, attempts):
    session = Mql5Session()
    get = Mock()
    wait = Mock()
    monkeypatch.setattr(session.http, "get", get)
    monkeypatch.setattr(session.limiter, "wait", wait)
    with pytest.raises(ValueError, match="positive Ganzzahl"):
        session.get("/en", max_throttle_retries=attempts)
    get.assert_not_called()
    wait.assert_not_called()


@pytest.mark.parametrize("attempts", [1, 3])
def test_positive_attempt_limit_keeps_existing_request_count(monkeypatch, attempts):
    session = Mql5Session()
    response = requests.Response()
    response.status_code = 429
    get = Mock(return_value=response)
    monkeypatch.setattr(session.http, "get", get)
    monkeypatch.setattr(session.limiter, "wait", Mock())
    monkeypatch.setattr("mqlkiscanner.mql5.session.time.sleep", Mock())
    with pytest.raises(Mql5ThrottleError, match="HTTP 429"):
        session.get("/en", max_throttle_retries=attempts)
    assert get.call_count == attempts
