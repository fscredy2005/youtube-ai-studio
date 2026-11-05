"""Strict YouTube URL parsing and caption retrieval. No URL is fetched directly from user input."""
from __future__ import annotations
import re
import time
from urllib.parse import parse_qs, urlsplit
import requests
from .models import Segment, VideoResult

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
                 "youtube-nocookie.com", "www.youtube-nocookie.com", "youtu.be", "www.youtu.be"}


class VideoInputError(ValueError):
    pass


class CaptionsUnavailable(RuntimeError):
    pass


def parse_video_id(value: str) -> str:
    value = (value or "").strip()
    if len(value) > 2048:
        raise VideoInputError("URL is too long.")
    if VIDEO_ID.fullmatch(value):
        return value
    parts = urlsplit(value)
    if parts.scheme not in {"https", "http"} or not parts.hostname:
        raise VideoInputError("Paste a valid YouTube link (or an 11-character video ID).")
    try:
        if parts.username or parts.password or parts.port:
            raise VideoInputError("The YouTube link contains unexpected credentials or a port.")
    except ValueError as exc:
        raise VideoInputError("The YouTube link has an invalid port.") from exc
    host = parts.hostname.lower()
    if host not in ALLOWED_HOSTS:
        raise VideoInputError("Only links from youtube.com or youtu.be are accepted.")
    pieces = [p for p in parts.path.split("/") if p]
    if host.endswith("youtu.be"):
        candidate = pieces[0] if pieces else ""
    elif pieces and pieces[0] in {"shorts", "embed", "live", "v"}:
        candidate = pieces[1] if len(pieces) > 1 else ""
    elif parts.path in {"/watch", "/watch/"}:
        candidate = parse_qs(parts.query).get("v", [""])[0]
    else:
        candidate = ""
    if not VIDEO_ID.fullmatch(candidate):
        raise VideoInputError("Could not find a valid 11-character YouTube video ID.")
    return candidate


def metadata(video_id: str) -> dict:
    """Lightweight public oEmbed; optional yt-dlp duration lookup is opt-in."""
    data = {"title": f"YouTube video {video_id}", "channel": "Unknown channel",
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg", "duration": None}
    try:
        response = requests.get("https://www.youtube.com/oembed", params={
            "url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}, timeout=7)
        response.raise_for_status()
        remote = response.json()
        data["title"] = str(remote.get("title", data["title"]))[:300]
        data["channel"] = str(remote.get("author_name", data["channel"]))[:120]
        # YouTube thumbnail CDN URL derived from validated video ID to avoid arbitrary network links.
    except (requests.RequestException, ValueError, TypeError):
        pass
    return data


def retrieve_captions(video_id: str, preferred: str = "Auto") -> tuple[list[Segment], str]:
    """Manual captions preferred over auto captions; not guaranteed on cloud IP addresses."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcripts = list(YouTubeTranscriptApi().list(video_id))
    except Exception as exc:
        kind = type(exc).__name__
        if kind in {"RequestBlocked", "IpBlocked", "TooManyRequests"}:
            message = ("YouTube is blocking requests from this cloud hosting IP. "
                       "Add an optional SUPADATA_API_KEY to Streamlit secrets, "
                       "or use More options to paste a YouTube transcript.")
        elif kind in {"TranscriptsDisabled", "NoTranscriptFound"}:
            message = "No accessible YouTube captions were reported for this video. Use More options to paste a transcript."
        else:
            message = ("Captions could not be retrieved. The video may lack captions "
                       "or YouTube may block this cloud server. Use More options to paste a transcript.")
        raise CaptionsUnavailable(message) from exc
    if not transcripts:
        raise CaptionsUnavailable("No public captions were found. Upload an authorized audio file or paste a transcript.")
    if preferred != "Auto":
        candidates = sorted(transcripts, key=lambda t: (
            not t.language_code.lower().startswith(preferred.lower()), t.is_generated))
    else:
        candidates = sorted(transcripts, key=lambda t: (t.is_generated,
            0 if t.language_code.startswith("en") else 1 if t.language_code.startswith("fr") else 2))
    last_error = None
    for transcript in candidates:
        try:
            fetched = transcript.fetch()
            output = [Segment(float(item.start), float(item.duration), str(item.text).replace("\n", " ").strip())
                      for item in fetched if str(item.text).strip()]
            if output:
                return output, str(transcript.language_code)
        except Exception as exc:
            last_error = exc
    raise CaptionsUnavailable("Captions exist but could not be fetched from this server. Try pasting a transcript or uploading an audio file.") from last_error


def retrieve_supadata_captions(video_id: str, api_key: str, preferred: str = "Auto") -> tuple[list[Segment], str]:
    """Optional third-party fallback for existing captions only; does not trigger AI transcription."""
    if not api_key or not VIDEO_ID.fullmatch(video_id):
        raise CaptionsUnavailable("Hosted caption fallback is not configured.")
    endpoint = "https://api.supadata.ai/v1/transcript"
    headers = {"x-api-key": api_key}
    params = {"url": f"https://www.youtube.com/watch?v={video_id}", "mode": "native"}
    if preferred != "Auto":
        params["lang"] = preferred
    try:
        r = requests.get(endpoint, params=params, headers=headers, timeout=35)
        r.raise_for_status()
        payload = r.json()
        if not isinstance(payload, dict):
            raise CaptionsUnavailable("The hosted service returned invalid caption data.")
        if payload.get("jobId"):
            job_id = payload["jobId"]
            if not isinstance(job_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", job_id):
                raise CaptionsUnavailable("The hosted service returned an invalid job ID.")
            for _ in range(12):
                time.sleep(2)
                poll = requests.get(f"{endpoint}/{job_id}", headers=headers, timeout=20)
                poll.raise_for_status()
                payload = poll.json()
                if payload.get("status") == "completed":
                    break
                if payload.get("status") == "failed":
                    raise CaptionsUnavailable("The hosted caption job failed.")
            else:
                raise CaptionsUnavailable("The hosted caption job is still processing. Try again shortly.")
        if not isinstance(payload, dict) or not isinstance(payload.get("content"), list):
            raise CaptionsUnavailable("The hosted service returned no usable caption segments.")
        rows = [Segment(float(x["offset"]) / 1000, float(x.get("duration", 0)) / 1000,
                        str(x.get("text", "")).replace("\n", " ").strip())
                for x in payload["content"] if isinstance(x, dict) and str(x.get("text", "")).strip()]
        if not rows:
            raise CaptionsUnavailable("No existing captions were returned for this video.")
        return rows, str(payload.get("lang", "unknown"))
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        if code in {401, 403}:
            why = "Check SUPADATA_API_KEY in your private Streamlit secrets."
        elif code in {402, 429}:
            why = "The hosted caption credit limit may have been reached."
        elif code == 404:
            why = "No captions were found by the hosted service."
        else:
            why = "The hosted caption service is unavailable."
        raise CaptionsUnavailable(why + " You can still paste a transcript.") from exc
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        raise CaptionsUnavailable("The hosted caption service could not return a usable transcript. "
                                  "Try again or paste a transcript.") from exc


def analyze_youtube(url: str, preferred: str = "Auto", supadata_key: str = "") -> VideoResult:
    video_id = parse_video_id(url)
    info = metadata(video_id)
    source = "YouTube captions"
    try:
        segments, language = retrieve_captions(video_id, preferred)
    except CaptionsUnavailable as primary_error:
        if not supadata_key:
            raise
        try:
            segments, language = retrieve_supadata_captions(video_id, supadata_key, preferred)
            source = "Supadata captions"
        except CaptionsUnavailable as fallback_error:
            raise CaptionsUnavailable(str(primary_error) + " Hosted fallback: " + str(fallback_error)) from fallback_error
    return VideoResult(video_id=video_id, title=info["title"], channel=info["channel"],
                       duration=info["duration"] or (segments[-1].start + segments[-1].duration),
                       thumbnail=info["thumbnail"], language=language, segments=segments, source=source)


def retrieve_translation(video_id: str, original_language: str, target_language: str) -> list[Segment]:
    """Use a YouTube-provided translated caption track when the creator/video permits it."""
    if target_language == original_language or target_language.split("-")[0] == original_language.split("-")[0]:
        raise CaptionsUnavailable("The captions are already in the selected language.")
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        tracks = list(YouTubeTranscriptApi().list(video_id))
        preferred = [t for t in tracks if t.language_code == original_language]
        originals = preferred or tracks
        source = next((t for t in originals if t.is_translatable), None)
        if source is None:
            raise CaptionsUnavailable("YouTube does not provide a translatable subtitle track for this video.")
        translated = source.translate(target_language).fetch()
        rows = [Segment(float(s.start), float(s.duration), str(s.text).strip())
                for s in translated if str(s.text).strip()]
        if not rows:
            raise CaptionsUnavailable("The translated subtitle track was empty.")
        return rows
    except CaptionsUnavailable:
        raise
    except Exception as exc:
        raise CaptionsUnavailable("Translated captions aren't available on this server or for this video.") from exc
