"""Opt-in YouTube media downloads for content the user is authorized to download.
Disabled by default for public deployments.
"""
from __future__ import annotations
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from .youtube import parse_video_id

MAX_DOWNLOAD_MB = 50


class MediaDownloadError(RuntimeError):
    pass


def download_authorized(url: str, audio_only: bool, confirmed: bool) -> tuple[str, bytes]:
    if os.getenv("ENABLE_YOUTUBE_MEDIA_DOWNLOAD", "false").lower() != "true":
        raise MediaDownloadError("Media downloads are disabled by the administrator.")
    if not confirmed:
        raise MediaDownloadError("Confirm that you own or are authorized to download this media.")
    video_id = parse_video_id(url)
    try:
        import yt_dlp
    except ImportError as exc:
        raise MediaDownloadError("yt-dlp is not installed on the server.") from exc
    with TemporaryDirectory() as tmp:
        format_selector = "bestaudio[ext=m4a]/bestaudio" if audio_only else "best[ext=mp4][height<=720]/best[height<=720]"
        opts = {"format": format_selector, "outtmpl": str(Path(tmp) / "%(id)s.%(ext)s"),
                "noplaylist": True, "quiet": True, "no_warnings": True,
                "ignoreerrors": False, "retries": 1, "socket_timeout": 12,
                "max_filesize": MAX_DOWNLOAD_MB * 1024 * 1024,
                "playlistend": 1}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                if not info or info.get("is_live"):
                    raise MediaDownloadError("Live or unavailable videos cannot be downloaded.")
                if (info.get("duration") or 0) > 1800:
                    raise MediaDownloadError("Videos longer than 30 minutes aren't supported for server downloads.")
                size = info.get("filesize") or info.get("filesize_approx")
                if size and size > MAX_DOWNLOAD_MB * 1024 * 1024:
                    raise MediaDownloadError("This file exceeds the 50 MB limit.")
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
            files = [p for p in Path(tmp).iterdir() if p.is_file()]
            if len(files) != 1 or files[0].stat().st_size > MAX_DOWNLOAD_MB * 1024 * 1024:
                raise MediaDownloadError("Download output is missing or exceeds the 50 MB limit.")
            return files[0].name, files[0].read_bytes()
        except MediaDownloadError:
            raise
        except Exception as exc:
            raise MediaDownloadError("Video download was blocked or failed. Try authorized upload instead.") from exc
