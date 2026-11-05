from unittest.mock import patch
import io
import pytest
from studio.models import Segment, VideoResult
from studio.youtube import parse_video_id, VideoInputError, analyze_youtube, CaptionsUnavailable
from studio.summary import timestamp, extractive, generate_summary, chunk_segments, find_related
from studio.chapters import suggested_chapters
from studio.export import transcript_txt, transcript_srt, report_markdown, report_pdf

SAMPLE = [
    Segment(0, 2, "Welcome to our workshop. Today we are going to examine creative tools for designers."),
    Segment(10, 2, "The first tool is a simple spreadsheet for tracking production status and timing."),
    Segment(24, 3, "Later we explain how to automate the report and present the results to clients."),
    Segment(40, 2, "Our final recommendation is to verify every number before sharing the data."),
]

@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ?t=14",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ",
    "https://www.youtube.com/live/dQw4w9WgXcQ",
    "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
    "dQw4w9WgXcQ",
])
def test_youtube_urls(url):
    assert parse_video_id(url) == "dQw4w9WgXcQ"

@pytest.mark.parametrize("url", [
    "https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
    "file:///tmp/hi", "https://www.youtube.com/watch?v=bad",
    "https://youtu.be/dQw4w9WgXcQ:81", "https://www.youtube.com@evil.com/",
    "http://127.0.0.1/watch?v=dQw4w9WgXcQ",
])
def test_malicious_urls_rejected(url):
    with pytest.raises(VideoInputError):
        parse_video_id(url)


def test_timestamps():
    assert timestamp(65.4) == "01:05"
    assert timestamp(3661.8) == "01:01:01"


def test_summaries_formats():
    for kind in ["Quick summary", "Detailed summary", "Key takeaways", "Step-by-step tutorial", "Research notes"]:
        result = extractive(SAMPLE, kind, "dQw4w9WgXcQ")
        assert "workshop" in result
        assert "youtube.com" in result


def test_chunking():
    assert len(chunk_segments(SAMPLE, target_chars=110)) >= 2
    assert all("[" in c for c in chunk_segments(SAMPLE, target_chars=110))


def test_find_related():
    assert "spreadsheet" in find_related(SAMPLE, "spreadsheet production", "dQw4w9WgXcQ")


def test_export_formats():
    data = VideoResult(video_id="dQw4w9WgXcQ", title="Workshop", segments=SAMPLE, summary="Useful summary")
    assert b"Workshop" in transcript_txt(data)
    assert b"00:00:00,000 --> 00:00:02,000" in transcript_srt(data)
    assert b"## Full transcript" in report_markdown(data)
    assert report_pdf(data).startswith(b"%PDF")
    assert len(suggested_chapters(data.segments, data.video_id)) >= 1


def test_mocked_youtube_pipeline():
    with patch("studio.youtube.metadata", return_value={"title": "Example", "channel": "Channel", "duration": 100, "thumbnail": ""}), \
         patch("studio.youtube.retrieve_captions", return_value=(SAMPLE, "en")):
        data = analyze_youtube("https://youtu.be/dQw4w9WgXcQ")
    output, engine, note = generate_summary(data.segments, "Quick summary", data.video_id)
    assert data.title == "Example" and len(data.segments) == 4
    assert engine == "Free extractive" and "extractive" in note.lower()
    assert "spreadsheet" in output


def test_llm_failure_falls_back():
    with patch("studio.summary.gemini_summary", side_effect=RuntimeError("offline")):
        output, engine, note = generate_summary(SAMPLE, "Quick summary", "dQw4w9WgXcQ", api_key="fake")
    assert engine == "Free extractive" and "unavailable" in note
    assert "workshop" in output


def test_no_live_media_access_without_admin_opt_in():
    from studio.media import download_authorized, MediaDownloadError
    with patch.dict("os.environ", {"ENABLE_YOUTUBE_MEDIA_DOWNLOAD": "false"}):
        with pytest.raises(MediaDownloadError):
            download_authorized("https://youtu.be/dQw4w9WgXcQ", audio_only=False, confirmed=True)


def test_linkify_timestamps():
    from studio.summary import linkify_timestamp_marks
    result = linkify_timestamp_marks("At [03:12] there is a demo.", "dQw4w9WgXcQ")
    assert "t=192s" in result
    assert linkify_timestamp_marks(result, "dQw4w9WgXcQ") == result
    assert "t=" not in linkify_timestamp_marks("At [03:12] there is a demo.", "")


def test_caption_translation_from_available_track():
    import sys
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from studio.youtube import retrieve_translation
    translated_track = SimpleNamespace(fetch=lambda: [SimpleNamespace(start=0, duration=2, text="Bonjour !")])
    original_track = SimpleNamespace(language_code="en", is_translatable=True,
                                     translate=lambda lang: translated_track)
    fake_api = MagicMock()
    fake_api.YouTubeTranscriptApi.return_value.list.return_value = [original_track]
    with patch.dict(sys.modules, {"youtube_transcript_api": fake_api}):
        result = retrieve_translation("dQw4w9WgXcQ", "en", "fr")
    assert len(result) == 1 and result[0].text == "Bonjour !"
