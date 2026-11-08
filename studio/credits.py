"""Read-only Supadata account credit balance. No credentials are logged or returned."""
from __future__ import annotations

from dataclasses import dataclass

import requests

SUPADATA_ACCOUNT_URL = "https://api.supadata.ai/v1/me"


@dataclass(frozen=True)
class CreditBalance:
    plan: str
    max_credits: int
    used_credits: int

    @property
    def remaining(self) -> int:
        return max(0, self.max_credits - self.used_credits)


def fetch_supadata_balance(api_key: str) -> CreditBalance | None:
    """Return provider-reported credits, or None if unavailable.

    GET /me is a read-only account-status call. Do not guess a plan's quota
    or expose the API key or raw error responses in the UI.
    """
    if not api_key:
        return None
    try:
        response = requests.get(
            SUPADATA_ACCOUNT_URL,
            headers={"x-api-key": api_key},
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return None
        maximum = data.get("maxCredits")
        used = data.get("usedCredits")
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0
               for v in (maximum, used)):
            return None
        plan = data.get("plan")
        if not isinstance(plan, str) or not plan.strip():
            plan = "Unknown"
        return CreditBalance(plan=plan[:50], max_credits=maximum, used_credits=used)
    except (requests.RequestException, ValueError, TypeError):
        return None
