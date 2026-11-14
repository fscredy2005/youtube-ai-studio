"""No network, AI model, Streamlit or external services required."""
import csv
from datetime import datetime, timezone
from io import StringIO

import pytest

from studio.models import VideoResult
from studio.notion_export import summary_csv, summary_markdown

NOW = datetime(2026, 11, 15, 0, 24, tzinfo=timezone.utc)


def test_notions_exports_preserve_current_summary_and_timestamp_links():
    summary = "### Research\n- [01:05](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=65s) First insight\n- [02:31] Second\nConclusion, with a comma."
    result = VideoResult(video_id="dQw4w9WgXcQ", title="Café, AI & Ideas", channel="Test Channel",
                         summary=summary, summary_kind="Detailed summary", summary_engine="Gemini")
    md = summary_markdown(result, NOW).decode("utf-8")
    assert "# Café, AI & Ideas" in md
    assert "**Exported (UTC):** 2026-11-15 00:24 UTC" in md
    assert "**Summary format:** Detailed summary" in md
    assert summary in md
    assert "Full transcript" not in md
    rows = list(csv.DictReader(StringIO(summary_csv(result, NOW).decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["Name"] == "Café, AI & Ideas"
    assert rows[0]["Summary"] == summary
    assert rows[0]["Summary format"] == "Detailed summary"
    assert rows[0]["Export date (UTC)"] == "2026-11-15 00:24 UTC"
    assert "01:05 — https://www.youtube.com/watch" in rows[0]["Timestamps"]
    assert "02:31" in rows[0]["Timestamps"]


def test_unlinked_pasted_text_keeps_no_fake_url_or_timestamps():
    result = VideoResult(video_id="", title="User note", source="Pasted text", summary="Useful note.")
    md = summary_markdown(result, NOW).decode("utf-8")
    row = next(csv.DictReader(StringIO(summary_csv(result, NOW).decode("utf-8-sig"))))
    assert "**Video:**" not in md
    assert row["URL"] == ""
    assert row["Timestamps"] == ""
    assert row["Summary"] == "Useful note."


def test_multiline_csv_is_single_record_and_metadata_is_sanitized():
    result = VideoResult(video_id="", title="A\nB*", channel="One\nTwo", summary="line1\nline2, comma\n\"quote\"")
    md = summary_markdown(result, NOW).decode("utf-8")
    assert "# A B\\*" in md
    row = next(csv.DictReader(StringIO(summary_csv(result, NOW).decode("utf-8-sig"))))
    assert row["Summary"] == result.summary


def test_naive_export_timestamp_is_rejected():
    with pytest.raises(ValueError):
        summary_csv(VideoResult(video_id="", title="Example"), datetime(2026, 1, 1))
