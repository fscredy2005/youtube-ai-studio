"""Conservative transcript timing checks. No external calls or API credits required.

A transcript can look temporally complete and still omit words: this checker never
claims to verify the semantic completeness or accuracy of captions.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import re
from .models import Segment

GAP_THRESHOLD_SECONDS = 15.0


@dataclass(frozen=True)
class CaptionGap:
    start: float
    end: float

    @property
    def seconds(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class IntegrityReport:
    status: str
    summary: str
    first_start: float | None
    last_end: float | None
    reference_duration: float | None
    gaps: tuple[CaptionGap, ...]
    out_of_order: int
    overlaps: int
    invalid_timing: int
    empty_text: int
    zero_duration: int
    start_missing: float | None
    end_missing: float | None
    notes: tuple[str, ...]


def parse_video_duration(value: str) -> float | None:
    """Parse independently observed MM:SS or HH:MM:SS video length.

    Empty is unknown, not zero. Reject malformed timestamps rather than silently
    treating them as trustworthy evidence.
    """
    value = (value or "").strip()
    if not value:
        return None
    if not re.fullmatch(r"\d{1,3}:\d{2}(?::\d{2})?", value):
        raise ValueError("Enter a duration in MM:SS or HH:MM:SS format, e.g. 26:49.")
    parts = [int(item) for item in value.split(":")]
    if parts[-1] >= 60 or (len(parts) == 3 and parts[-2] >= 60):
        raise ValueError("Seconds (and minutes in HH:MM:SS) must be below 60.")
    duration = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
    if not 0 < duration <= 24 * 3600:
        raise ValueError("Enter a non-zero video duration of at most 24 hours.")
    return float(duration)


def check_integrity(segments: list[Segment], reference_duration: float | None = None) -> IntegrityReport:
    """Spot suspect time gaps and endpoints; never claim a transcript is complete.

    Use reference_duration ONLY when it comes independently from video metadata
    or an explicit duration entered by the user, never from caption end times.
    """
    duration = (float(reference_duration) if reference_duration is not None and
                math.isfinite(float(reference_duration)) and float(reference_duration) > 0 else None)
    valid: list[tuple[float, float]] = []
    invalid = empty = zero = out_of_order = 0
    previous_start: float | None = None
    for segment in segments:
        if not segment.text.strip():
            empty += 1
            continue
        start, length = segment.start, segment.duration
        if not (math.isfinite(start) and math.isfinite(length) and start >= 0 and length >= 0):
            invalid += 1
            continue
        if previous_start is not None and start < previous_start - .5:
            out_of_order += 1
        previous_start = start
        if length == 0:
            zero += 1
        valid.append((start, start + length))

    if not valid:
        return IntegrityReport("Cannot assess", "No valid timed caption segments were found.",
                               None, None, duration, (), out_of_order, 0, invalid, empty,
                               zero, None, None, ("A complete transcript cannot be verified.",))
    valid.sort()
    first = valid[0][0]
    end = max(row[1] for row in valid)
    # A plain-text paste uses synthetic (0,0) timestamps and has no meaningful timeline.
    if end == 0 and all(start == 0 for start, _ in valid):
        return IntegrityReport("Cannot assess", "This text has no usable caption timestamps.",
                               None, None, duration, (), out_of_order, 0, invalid, empty,
                               zero, None, None, ("Paste timed captions (or import an SRT) to check for gaps.",))

    gaps: list[CaptionGap] = []
    overlaps = 0
    cursor = valid[0][1]
    for start, stop in valid[1:]:
        if start - cursor >= GAP_THRESHOLD_SECONDS:
            gaps.append(CaptionGap(cursor, start))
        if cursor - start > 3:
            overlaps += 1
        cursor = max(cursor, stop)
    start_missing = first if duration is not None else None
    end_missing = max(0.0, duration - end) if duration is not None else None
    edge_threshold = max(12.0, duration * .02) if duration is not None else None

    warnings = []
    if invalid:
        warnings.append(f"{invalid} captions have invalid time values")
    if out_of_order:
        warnings.append(f"{out_of_order} caption timestamps are out of order")
    if gaps:
        warnings.append(f"{len(gaps)} gap(s) of at least {GAP_THRESHOLD_SECONDS:g} seconds")
    if start_missing is not None and start_missing >= edge_threshold:
        warnings.append("captions begin well after the video starts")
    if end_missing is not None and end_missing >= edge_threshold:
        warnings.append("captions end before the video finishes")

    notes = ["Timing checks cannot verify every spoken word or caption accuracy.",
             "A gap can represent silence, music, or missing captions; review the video to confirm."]
    if duration is None:
        notes.append("Video length is unknown: the end-of-video check was not performed.")
    if zero > len(valid) * .5:
        warnings.append("more than half of caption segments have zero duration")
    if overlaps:
        notes.append(f"{overlaps} significant caption overlap(s) found; overlapping captions may be normal.")
    if empty:
        notes.append(f"{empty} empty caption passages were ignored.")

    if warnings:
        status, summary = "Review recommended", "; ".join(warnings) + "."
    elif duration is None:
        status = "Partial check"
        summary = "No large internal timing gaps detected; video length is unknown, so final completeness cannot be assessed."
    else:
        status = "No obvious timing issues"
        summary = "No large timing gaps or missing start/end interval detected. This is not proof of a complete transcript."
    return IntegrityReport(status, summary, first, end, duration, tuple(gaps), out_of_order,
                           overlaps, invalid, empty, zero, start_missing, end_missing,
                           tuple(notes))
