"""Read-only Supadata account credit balance. No credentials are logged or returned."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from calendar import monthrange
import re

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


def parse_reset_date(value: str) -> date | None:
    """Parse a manually supplied provider-dashboard reset date, never guess one."""
    value = (value or "").strip()
    if not value:
        return None
    if not re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", value):
        raise ValueError("Use YYYY-MM-DD, for example 2026-11-21.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Enter a valid calendar date in YYYY-MM-DD format.") from exc


def next_expected_monthly_reset(confirmed_date: date, today: date) -> date:
    """Project the next monthly anniversary of a manually provided reset date.

    A 31st-day anchor becomes the last day of shorter months. This is an
    estimate, not a provider-verified billing schedule or fixed 30-day period.
    """
    if confirmed_date >= today:
        return confirmed_date
    anchor_day = confirmed_date.day
    year, month = today.year, today.month
    candidate = date(year, month, min(anchor_day, monthrange(year, month)[1]))
    if candidate < today:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        candidate = date(year, month, min(anchor_day, monthrange(year, month)[1]))
    return candidate
