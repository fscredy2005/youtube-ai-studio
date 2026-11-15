"""Presentation-only helpers for the saved-video library.

All operations are local; they do not fetch captions, thumbnails, or AI output.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
SORT_OPTIONS = ("Newest saved", "Oldest saved", "Title A–Z", "Title Z–A")


def thumbnail_url(video_id: str) -> str | None:
    """Build a YouTube thumbnail URL only for valid video identifiers."""
    if not isinstance(video_id, str) or not _VIDEO_ID.fullmatch(video_id):
        return None
    return f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"


def _saved_utc(item: dict) -> datetime:
    try:
        dt = datetime.fromisoformat(item.get("updated_at", ""))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return datetime.min.replace(tzinfo=timezone.utc)


def formatted_saved_date(item: dict) -> str:
    """Show last SAVED time, not the YouTube video's publication date."""
    saved = _saved_utc(item)
    if saved.year == 1:
        return "Save date unavailable"
    return saved.astimezone(ZoneInfo("Europe/Paris")).strftime("%d %b %Y · %H:%M")


def search_and_sort(items: list[dict], query: str = "", sort_by: str = "Newest saved") -> list[dict]:
    """Filter by title or channel and order using saved metadata only."""
    q = (query or "").strip().casefold()
    matched = [
        item for item in items if isinstance(item, dict) and (
            q in str(item.get("title") or "").casefold()
            or q in str(item.get("channel") or "").casefold()
        )
    ]
    if sort_by == "Oldest saved":
        return sorted(matched, key=lambda x: (_saved_utc(x), str(x.get("id") or "")))
    if sort_by in ("Title A–Z", "Title Z–A"):
        return sorted(
            matched, key=lambda x: (str(x.get("title") or "").casefold(), str(x.get("id") or "")),
            reverse=sort_by == "Title Z–A",
        )
    return sorted(matched, key=lambda x: (_saved_utc(x), str(x.get("id") or "")), reverse=True)
