"""Test independent video-duration lookup; no live API calls or credentials."""
from unittest.mock import Mock, patch
import requests
from studio.youtube import supadata_video_metadata, analyze_youtube
from studio.models import Segment
from studio.integrity import check_integrity

VIDEO_ID = "dQw4w9WgXcQ"

def fake_response(payload):
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response

def test_duration_from_supadata_media():
    data = {"platform": "youtube", "id": VIDEO_ID, "title": "Video title",
            "author": {"displayName": "Creator"}, "media": {"duration": 1609}}
    with patch("studio.youtube.requests.get", return_value=fake_response(data)) as get:
        result = supadata_video_metadata(VIDEO_ID, "dummy-key")
    assert result == {"duration": 1609.0, "title": "Video title", "channel": "Creator"}
    assert get.call_args.kwargs["headers"] == {"x-api-key": "dummy-key"}
    assert "dummy-key" not in str(get.call_args.kwargs["params"])

def test_legacy_duration_shape():
    with patch("studio.youtube.requests.get", return_value=fake_response(
        {"id": VIDEO_ID, "duration": 84, "channel": {"name": "Old channel"}})):
        assert supadata_video_metadata(VIDEO_ID, "dummy")["duration"] == 84

def test_invalid_durations_not_trusted():
    for value in (None, True, 0, -5, "nan", 8e20, "invalid"):
        with patch("studio.youtube.requests.get", return_value=fake_response({"media": {"duration": value}})):
            assert supadata_video_metadata(VIDEO_ID, "dummy") is None

def test_metadata_failure_keeps_transcript():
    captions = [Segment(0, 3, "start"), Segment(12, 3, "end")]
    base = {"title": "Title", "channel": "Channel", "duration": None, "thumbnail": ""}
    with patch("studio.youtube.retrieve_captions", return_value=(captions, "en")), \
         patch("studio.youtube.metadata", return_value=base), \
         patch("studio.youtube.supadata_video_metadata", return_value=None), \
         patch("studio.youtube.youtube_duration_via_ytdlp", return_value=None):
        result = analyze_youtube(VIDEO_ID, supadata_key="dummy")
    assert len(result.segments) == 2
    assert result.duration is None
    assert result.duration_source == ""

def test_metadata_duration_is_independent_of_caption_end():
    captions = [Segment(0, 3, "start"), Segment(20, 3, "middle"), Segment(55, 3, "end")]
    base = {"title": "Title", "channel": "Channel", "duration": None, "thumbnail": ""}
    meta = {"duration": 90, "title": "New title", "channel": "Creator"}
    with patch("studio.youtube.retrieve_captions", return_value=(captions, "en")), \
         patch("studio.youtube.metadata", return_value=base), \
         patch("studio.youtube.supadata_video_metadata", return_value=meta):
        result = analyze_youtube(VIDEO_ID, supadata_key="dummy")
    assert result.duration == 90
    assert result.duration_source == "Supadata metadata"
    assert check_integrity(result.segments, result.duration).end_missing == 32

def test_timeout_is_safe():
    with patch("studio.youtube.requests.get", side_effect=requests.Timeout):
        assert supadata_video_metadata(VIDEO_ID, "dummy") is None
