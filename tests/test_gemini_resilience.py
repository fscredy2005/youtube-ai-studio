"""Tests for Gemini failure guidance and request chunking."""
from studio.models import Segment
from studio.summary import chunk_segments, friendly_gemini_error, generate_summary
from unittest.mock import patch


class FakeGeminiError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__("Private provider message should not be shown")


def test_short_transcript_stays_in_one_request():
    segments = [Segment(i * 3, 3, "A caption about Claude tools and AI " * 3) for i in range(140)]
    assert len(chunk_segments(segments)) == 1


def test_long_transcript_still_chunks():
    segments = [Segment(i * 2, 2, "Much longer caption " * 10) for i in range(600)]
    assert len(chunk_segments(segments)) > 1


def test_transient_server_error_is_actionable_and_safe():
    message = friendly_gemini_error(FakeGeminiError(503))
    assert "temporarily unavailable" in message
    assert "Generate selected format" in message
    assert "Private provider message" not in message


def test_quota_error_is_not_mislabelled_as_server_outage():
    message = friendly_gemini_error(FakeGeminiError(429))
    assert "quota" in message.lower()


def test_summary_falls_back_without_leaking_error_text():
    segments = [Segment(0, 3, "This is a transcript with helpful details.")]
    with patch("studio.summary.gemini_summary", side_effect=FakeGeminiError(500)):
        output, engine, note = generate_summary(
            segments, "Quick summary", "dQw4w9WgXcQ", api_key="private"
        )
    assert engine == "Free extractive"
    assert "Generate selected format" in note
    assert "Private provider message" not in note
    assert "transcript" in output
