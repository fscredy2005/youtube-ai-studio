"""In-memory exports; no persistent transcript storage."""
from __future__ import annotations
from io import BytesIO
from xml.sax.saxutils import escape
from .models import VideoResult
from .summary import timestamp
from .chapters import suggested_chapters


def transcript_txt(result: VideoResult) -> bytes:
    heading = f"{result.title}\n{result.url}\nLanguage: {result.language}\n\n"
    return (heading + "\n".join(f"[{timestamp(s.start)}] {s.text}" for s in result.segments)).encode("utf-8")


def _srt_time(value: float) -> str:
    ms = max(0, int(round(value * 1000)))
    hours, rem = divmod(ms, 3600000)
    mins, rem = divmod(rem, 60000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def transcript_srt(result: VideoResult) -> bytes:
    rows = []
    for i, s in enumerate(result.segments, start=1):
        start = max(0.0, s.start)
        end = max(start + 0.1, start + max(0.0, s.duration))
        rows.append(f"{i}\n{_srt_time(start)} --> {_srt_time(end)}\n{s.text.strip()}\n")
    return "\n".join(rows).encode("utf-8")


def report_markdown(result: VideoResult, takeaways: str = "") -> bytes:
    ch = suggested_chapters(result.segments, result.video_id)
    rows = [f"# {result.title}", "", f"Source: {result.url or result.source}",
            f"Channel: {result.channel}", f"Language: {result.language}",
            f"Summary method: {result.summary_engine}", "", "## Summary", "", result.summary,
            "", "## Key takeaways", "", takeaways or "Not generated yet.",
            "", "## Suggested timeline (not official chapters)", ""]
    rows.extend(f"- [{c['time']}]({c['url']}) — {c['title']}" if c["url"] else f"- {c['time']} — {c['title']}" for c in ch)
    rows.extend(["", "## Full transcript", ""])
    rows.extend(f"[{timestamp(s.start)}] {s.text}" for s in result.segments)
    return "\n".join(rows).encode("utf-8")


def report_pdf(result: VideoResult, takeaways: str = "") -> bytes:
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from pathlib import Path

    family = "Helvetica"
    for font in (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                 Path("/usr/local/share/fonts/DejaVuSans.ttf")):
        if font.exists():
            try:
                if "StudioUnicode" not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont("StudioUnicode", str(font)))
                family = "StudioUnicode"
                break
            except Exception:
                pass
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="StudioTitle", fontName=family, fontSize=18, leading=23,
                              textColor=colors.HexColor("#103C5A"), spaceAfter=12))
    styles.add(ParagraphStyle(name="StudioSection", fontName=family, fontSize=12, leading=16,
                              textColor=colors.HexColor("#146AC5"), spaceBefore=12, spaceAfter=8))
    styles.add(ParagraphStyle(name="StudioText", fontName=family, fontSize=9, leading=14,
                              spaceAfter=7, alignment=TA_LEFT))
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=43, rightMargin=43,
                            topMargin=43, bottomMargin=40)
    story = [Paragraph(escape(result.title), styles["StudioTitle"])]
    story.append(Paragraph(escape(f"Channel: {result.channel}  |  Language: {result.language}"), styles["StudioText"]))
    if result.url:
        story.append(Paragraph(escape(result.url), styles["StudioText"]))
    story.append(Paragraph("Summary", styles["StudioSection"]))
    for line in result.summary.splitlines():
        line = line.strip().lstrip("#->* ")
        if line:
            story.append(Paragraph(escape(line), styles["StudioText"]))
    if takeaways:
        story.append(Paragraph("Key takeaways", styles["StudioSection"]))
        for line in takeaways.splitlines():
            line = line.strip().lstrip("#->* ")
            if line:
                story.append(Paragraph(escape(line), styles["StudioText"]))
    story.append(Paragraph("Full transcript", styles["StudioSection"]))
    for seg in result.segments[:12000]:
        content = f"[{timestamp(seg.start)}] {seg.text}"
        story.append(Paragraph(escape(content), styles["StudioText"]))
    doc.build(story)
    return buffer.getvalue()
