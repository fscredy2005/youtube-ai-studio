"""Optional CPU-only transcription for user-supplied, authorized media."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
from .models import Segment, VideoResult

ALLOWED_EXTS = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".mp4", ".webm"}
MAX_UPLOAD_MB = 50
MAX_DURATION_SECONDS = 30 * 60


class AudioError(RuntimeError):
    pass


def transcribe_upload(uploaded, title: str | None = None) -> VideoResult:
    if not uploaded:
        raise AudioError("Choose an audio or video file to transcribe.")
    name = getattr(uploaded, "name", "uploaded_audio")
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise AudioError("Unsupported file type. Use MP3, M4A, WAV, OGG, FLAC, MP4, or WebM.")
    content = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
    if not content or len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise AudioError(f"File must be between 1 byte and {MAX_UPLOAD_MB} MB.")
    try:
        from faster_whisper import WhisperModel
        import av
    except ImportError as exc:
        raise AudioError("Audio support is not installed on this server. See README 'Audio transcription'.") from exc
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as handle:
            path = handle.name
            handle.write(content)
        try:
            with av.open(path) as container:
                if container.duration and container.duration / av.time_base > MAX_DURATION_SECONDS:
                    raise AudioError("Audio is longer than 30 minutes. Split it into shorter files first.")
        except AudioError:
            raise
        except Exception as exc:
            raise AudioError("Unable to read this audio/video file.") from exc
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        fragments, info = model.transcribe(path, beam_size=1, vad_filter=True)
        segments = [Segment(float(s.start), max(0.1, float(s.end - s.start)), str(s.text).strip())
                    for s in fragments if str(s.text).strip()]
        if not segments:
            raise AudioError("No spoken words detected in the uploaded file.")
        return VideoResult(video_id="", title=title or Path(name).stem[:140], channel="Uploaded media",
                           duration=segments[-1].start + segments[-1].duration,
                           source="Uploaded authorized media", language=str(info.language), segments=segments)
    finally:
        if path and os.path.exists(path):
            os.remove(path)
