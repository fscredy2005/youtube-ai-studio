from __future__ import annotations
from .models import Segment
from .summary import _terms, timestamp, youtube_at
from collections import Counter


def suggested_chapters(segments: list[Segment], video_id: str, minutes: int = 4) -> list[dict]:
    """Deterministic timeline navigation, NOT the creator's official chapter markers."""
    if not segments:
        return []
    window = max(120, minutes * 60)
    origin = max(0.0, segments[0].start)
    groups: dict[int, list[Segment]] = {}
    for s in segments:
        groups.setdefault(int((s.start - origin) // window), []).append(s)
    chapters = []
    for i, items in groups.items():
        freq = Counter(word for s in items for word in _terms(s.text))
        common = [w for w, n in freq.most_common(10) if n >= 2][:3]
        label = " / ".join(common).capitalize() if common else "Transcript section"
        sec = items[0].start
        chapters.append({"start": sec, "time": timestamp(sec), "title": label,
                         "url": youtube_at(video_id, sec), "text": " ".join(s.text for s in items)[:320]})
    return chapters[:100]
