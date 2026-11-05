"""Regression tests for conservative transcript completeness diagnostics."""
import pytest
from studio.integrity import check_integrity, parse_video_duration
from studio.models import Segment


def timed(*windows):
    return [Segment(float(a), float(b - a), f"Caption {i}") for i, (a, b) in enumerate(windows)]


def test_normal_timing_never_claims_verified_completeness():
    result = check_integrity(timed((0, 5), (6, 10), (11, 20)), 20)
    assert result.status == "No obvious timing issues"
    assert not result.gaps and result.end_missing == 0
    assert "not proof" in result.summary.lower()


def test_missing_middle_is_detected():
    result = check_integrity(timed((0, 5), (25, 31), (32, 40)), 40)
    assert result.status == "Review recommended"
    assert len(result.gaps) == 1
    assert result.gaps[0].seconds == 20


def test_missing_end_only_detectable_with_independent_duration():
    captions = timed((0, 10), (12, 30))
    assert check_integrity(captions).status == "Partial check"
    result = check_integrity(captions, 60)
    assert result.end_missing == 30
    assert result.status == "Review recommended"


def test_start_gap_and_out_of_order_are_distinct():
    result = check_integrity(timed((20, 25), (0, 5), (6, 10)), 30)
    assert result.out_of_order == 1
    assert result.status == "Review recommended"
    late_start = check_integrity(timed((20, 25)), 30)
    assert late_start.start_missing == 20
    assert late_start.status == "Review recommended"


def test_overlap_and_zero_length_handling():
    overlap = check_integrity(timed((0, 12), (3, 5), (12, 15)), 15)
    assert overlap.overlaps == 1
    assert overlap.status == "No obvious timing issues"
    zeros = check_integrity([Segment(0, 0, "hello"), Segment(30, 0, "world")])
    assert zeros.status == "Review recommended"


def test_invalid_timing_and_plain_text():
    assert check_integrity([Segment(0, 0, "Plain text")]).status == "Cannot assess"
    result = check_integrity([Segment(-1, 5, "bad"), Segment(0, 8, "good")], 8)
    assert result.invalid_timing == 1
    assert result.status == "Review recommended"
    assert check_integrity([]).status == "Cannot assess"


@pytest.mark.parametrize("value,expected", [
    ("", None), ("26:49", 1609), ("01:26:49", 5209), ("0:45", 45),
])
def test_duration_format(value, expected):
    assert parse_video_duration(value) == expected


@pytest.mark.parametrize("value", [
    "foo", "26:61", "01:60:00", "00:00", "-01:23", "99:99", "999:00:00",
])
def test_invalid_duration_rejected(value):
    with pytest.raises(ValueError):
        parse_video_duration(value)
