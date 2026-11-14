"""Notion-friendly exports of an already-generated summary; no API calls."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
import re

from .models import VideoResult


# Read existing summary timestamps. Do not infer times from an un-timed source.
_TIME_LINK = re.compile(
    r"\[(?P<time>(?:\d{1,2}:)?\d{1,2}:\d{2})\]"
    r"(?:\((?P<url>https://(?:www\.)?youtube\.com/watch\?[^)\s]+)\))?"
)


def _export_date(exported_at: datetime | None) -> str:
    value = exported_at or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("exported_at must include a timezone")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _inline(value: str) -> str:
    """Keep untrusted metadata on one Markdown line."""
    return re.sub(r"\s+", " ", value or "").strip().replace("\\", "\\\\").replace("*", "\\*")


def summary_markdown(result: VideoResult, exported_at: datetime | None = None) -> bytes:
    """Single Notion page with only the current summary and available metadata."""
    rows = [
        f"# {_inline(result.title)}",
        "",
        f"**Channel:** {_inline(result.channel)}",
    ]
    if result.url:
        rows.append(f"**Video:** [Watch on YouTube]({result.url})")
    rows.extend([
        f"**Exported (UTC):** {_export_date(exported_at)}",
        f"**Summary format:** {_inline(result.summary_kind)}",
        f"**Summary method:** {_inline(result.summary_engine)}",
        "",
        "## Summary",
        "",
        result.summary,
        "",
    ])
    return "\n".join(rows).encode("utf-8")


def _summary_timestamps(summary: str) -> str:
    values = []
    for match in _TIME_LINK.finditer(summary):
        time, url = match.group("time"), match.group("url")
        item = f"{time} — {url}" if url else time
        if item not in values:
            values.append(item)
    return "\n".join(values)


def summary_csv(result: VideoResult, exported_at: datetime | None = None) -> bytes:
    """One-row UTF-8 CSV suitable for manual import into a Notion database."""
    record = {
        "Name": result.title,
        "Channel": result.channel,
        "URL": result.url,
        "Export date (UTC)": _export_date(exported_at),
        "Summary format": result.summary_kind,
        "Summary method": result.summary_engine,
        "Timestamps": _summary_timestamps(result.summary),
        "Summary": result.summary,
    }
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(record), lineterminator="\n")
    writer.writeheader()
    writer.writerow(record)
    return output.getvalue().encode("utf-8-sig")
