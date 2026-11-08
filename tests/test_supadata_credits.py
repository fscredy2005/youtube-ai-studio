"""Offline tests for the optional Supadata account credit display."""
from unittest.mock import Mock, patch

import pytest
import requests

from studio.credits import fetch_supadata_balance, SUPADATA_ACCOUNT_URL


def test_account_balance_and_read_only_request():
    response = Mock()
    response.json.return_value = {"plan": "Free", "maxCredits": 100, "usedCredits": 27}
    with patch("studio.credits.requests.get", return_value=response) as get:
        balance = fetch_supadata_balance("private-test-key")
    assert balance.remaining == 73
    assert (balance.max_credits, balance.used_credits, balance.plan) == (100, 27, "Free")
    get.assert_called_once_with(SUPADATA_ACCOUNT_URL,
                                headers={"x-api-key": "private-test-key"}, timeout=8)


def test_no_key_makes_no_request():
    with patch("studio.credits.requests.get") as get:
        assert fetch_supadata_balance("") is None
    get.assert_not_called()


@pytest.mark.parametrize("payload", [
    {}, [], {"maxCredits": True, "usedCredits": 0},
    {"maxCredits": 100, "usedCredits": -2},
    {"maxCredits": "100", "usedCredits": 27},
])
def test_unknown_or_invalid_quota_not_displayed(payload):
    response = Mock()
    response.json.return_value = payload
    with patch("studio.credits.requests.get", return_value=response):
        assert fetch_supadata_balance("key") is None


def test_account_quota_exhausted_never_negative():
    response = Mock()
    response.json.return_value = {"plan": "Free", "maxCredits": 100, "usedCredits": 101}
    with patch("studio.credits.requests.get", return_value=response):
        assert fetch_supadata_balance("key").remaining == 0


def test_network_error_is_nonfatal():
    with patch("studio.credits.requests.get", side_effect=requests.Timeout("secret-debug-value")):
        assert fetch_supadata_balance("key") is None
