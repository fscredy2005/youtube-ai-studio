from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Segment:
    start: float
    duration: float
    text: str


@dataclass
class VideoResult:
    video_id: str
    title: str
    channel: str = "Unknown channel"
    duration: float | None = None
    thumbnail: str = ""
    source: str = "YouTube captions"
    language: str = "unknown"
    segments: list[Segment] = field(default_factory=list)
    summary: str = ""
    summary_kind: str = "Quick summary"
    summary_engine: str = "Free extractive"
    summary_note: str = ""
    error: str = ""
    duration_source: str = ""

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.text.strip())

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}" if self.video_id else ""
