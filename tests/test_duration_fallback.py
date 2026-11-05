"""No-network tests for the no-download duration fallback."""
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
import sys
from studio.models import Segment
from studio.youtube import youtube_duration_via_ytdlp, analyze_youtube

VIDEO_ID = "dQw4w9WgXcQ"

def test_ytdlp_reads_length_without_downloading():
    stub = MagicMock()
    stub.YoutubeDL.return_value.__enter__.return_value.extract_info.return_value = {
        "id": VIDEO_ID, "duration": 1609,
    }
    with patch.dict(sys.modules, {"yt_dlp": stub}):
        assert youtube_duration_via_ytdlp(VIDEO_ID) == 1609
    assert stub.YoutubeDL.return_value.__enter__.return_value.extract_info.call_args.kwargs["download"] is False

def test_ytdlp_rejects_wrong_id_and_invalid_duration():
    stub = MagicMock()
    extractor = stub.YoutubeDL.return_value.__enter__.return_value
    with patch.dict(sys.modules, {"yt_dlp": stub}):
        for metadata in ({"id": "different-id", "duration": 1609},
                         {"id": VIDEO_ID, "duration": 0},
                         {"id": VIDEO_ID, "duration": float("nan")}):
            extractor.extract_info.return_value = metadata
            assert youtube_duration_via_ytdlp(VIDEO_ID) is None

def test_fallback_sets_duration_from_independent_source():
    captions = [Segment(0, 4, "hello"), Segment(50, 4, "bye")]
    info = {"title": "T", "channel": "C", "duration": None, "thumbnail": ""}
    with patch("studio.youtube.retrieve_captions", return_value=(captions, "en")), \
         patch("studio.youtube.metadata", return_value=info), \
         patch("studio.youtube.supadata_video_metadata", return_value=None), \
         patch("studio.youtube.youtube_duration_via_ytdlp", return_value=90):
        result = analyze_youtube(VIDEO_ID, supadata_key="dummy")
    assert result.duration == 90
    assert result.duration_source == "YouTube metadata (no download)"
