"""Private, text-only GitHub archive for YouTube AI Studio.

One record per analysis and a compact manifest. No AI, Supadata, or YouTube calls.
Requires a *private* repository and a narrowly scoped GitHub token.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from studio.models import Segment, VideoResult

REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
KEY_PATTERN = re.compile(r"^(?:[A-Za-z0-9_-]{11}|input-[a-f0-9]{20})$")
MAX_DOC_BYTES = 900_000


class HistoryError(Exception):
    """History is unavailable or cannot be updated. No secrets in messages."""


def record_id(result: VideoResult) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", result.video_id or ""):
        return result.video_id
    content = result.title + "\n" + result.text
    return "input-" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:20]


def summary_slot(style: str, language: str) -> str:
    """Distinct saved summaries by both layout and output language."""
    return style + "::" + (language or "English")


def make_record(result: VideoResult, *, takeaways: str = "", variants: dict | None = None,
                questions: list | None = None, translation: dict | None = None,
                manual_duration: str = "", summary_language: str = "English") -> dict:
    summary = {"text": result.summary, "engine": result.summary_engine,
               "note": result.summary_note}
    saved = dict(variants or {})
    saved[summary_slot(result.summary_kind, summary_language)] = summary
    return {
        "schema_version": 1, "id": record_id(result),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "result": asdict(result), "takeaways": takeaways,
        "summary_language": summary_language,
        "variants": saved, "questions": list(questions or []),
        "translation": translation, "manual_duration": manual_duration,
    }


def restore_record(record: dict) -> tuple[VideoResult, dict]:
    if record.get("schema_version") != 1 or not isinstance(record.get("result"), dict):
        raise HistoryError("Unsupported or invalid saved analysis.")
    data = record["result"].copy()
    segments = data.pop("segments", [])
    if not isinstance(segments, list) or len(segments) > 15000:
        raise HistoryError("Saved transcript is invalid.")
    try:
        data["segments"] = [Segment(**s) for s in segments]
        video = VideoResult(**data)
    except (TypeError, ValueError) as exc:
        raise HistoryError("Saved analysis is incompatible with this version.") from exc
    if len(video.text) > 180000:
        raise HistoryError("Saved transcript exceeds the current safety limit.")
    return video, {
        "takeaways": record.get("takeaways", ""),
        "variants": record.get("variants", {}),
        "questions": record.get("questions", []),
        "translation": record.get("translation"),
        "manual_duration": record.get("manual_duration", ""),
        "summary_language": record.get("summary_language", "English"),
    }


class GitHubHistory:
    def __init__(self, repository: str, token: str, *, opener=urlopen):
        if not REPO_PATTERN.fullmatch(repository or "") or not token:
            raise HistoryError("Configure a valid private HISTORY_REPO and HISTORY_TOKEN.")
        self.repo = repository
        self.token = token
        self.opener = opener
        self._verified = False

    def _request(self, path: str, method: str = "GET", data: dict | None = None):
        url = f"https://api.github.com/repos/{self.repo}/{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "YouTube-AI-Studio-History",
        }
        body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
        req = Request(url, headers=headers, data=body, method=method)
        try:
            with self.opener(req, timeout=12) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code in (409, 422):
                raise HistoryError("Archive changed concurrently; please retry saving.") from exc
            if exc.code in (401, 403):
                raise HistoryError("GitHub access denied. Check your history token and repository permissions.") from exc
            raise HistoryError(f"GitHub archive request failed (HTTP {exc.code}).") from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise HistoryError("Cannot reach or decode the GitHub archive right now.") from exc

    def verify_private(self) -> None:
        if self._verified:
            return
        repo = self._request("")
        if not isinstance(repo, dict) or repo.get("private") is not True:
            raise HistoryError("History storage must be an accessible PRIVATE GitHub repository.")
        self._verified = True

    def _read(self, name: str) -> tuple[dict | None, str | None]:
        self.verify_private()
        file = self._request("contents/" + quote(name, safe="/"))
        if file is None:
            return None, None
        try:
            data = base64.b64decode(file["content"], validate=False)
            return json.loads(data), file["sha"]
        except (KeyError, ValueError, TypeError) as exc:
            raise HistoryError("Saved archive contains invalid JSON data.") from exc

    def _write(self, name: str, record: dict, sha: str | None) -> None:
        self.verify_private()
        encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_DOC_BYTES:
            raise HistoryError("Analysis is too large for the configured text archive.")
        data = {"message": f"Save video analysis: {name}",
                "content": base64.b64encode(encoded).decode("ascii")}
        if sha:
            data["sha"] = sha
        result = self._request("contents/" + quote(name, safe="/"), "PUT", data)
        if result is None:
            raise HistoryError("GitHub archive did not confirm the save.")

    def list_index(self) -> list[dict]:
        index, _ = self._read("index.json")
        if not index:
            return []
        if index.get("schema_version") != 1 or not isinstance(index.get("items"), list):
            raise HistoryError("The history index format is invalid.")
        return sorted(index["items"], key=lambda x: x.get("updated_at", ""), reverse=True)

    def load(self, key: str) -> dict | None:
        if not KEY_PATTERN.fullmatch(key or ""):
            raise HistoryError("Invalid analysis identifier.")
        record, _ = self._read(f"analyses/{key}.json")
        if record and (record.get("id") != key or record.get("schema_version") != 1):
            raise HistoryError("Saved analysis identifier does not match its filename.")
        return record

    def save(self, record: dict) -> None:
        key = record.get("id", "")
        if not KEY_PATTERN.fullmatch(key):
            raise HistoryError("Invalid analysis identifier.")
        old, sha = self._read(f"analyses/{key}.json")
        # Retain previous summary formats and Q&A when a video is analyzed again.
        if old:
            variants = dict(old.get("variants") or {})
            variants.update(record.get("variants") or {})
            record["variants"] = variants
            old_questions = list(old.get("questions") or [])
            for item in record.get("questions") or []:
                if item not in old_questions:
                    old_questions.append(item)
            record["questions"] = old_questions
            if not record.get("translation"):
                record["translation"] = old.get("translation")
            if not record.get("manual_duration"):
                record["manual_duration"] = old.get("manual_duration", "")
        self._write(f"analyses/{key}.json", record, sha)
        self._update_index(record)

    def _update_index(self, record: dict) -> None:
        # A failed index update leaves the analysis intact; next Save can retry.
        for attempt in range(2):
            index, sha = self._read("index.json")
            items = list(index.get("items", [])) if index else []
            items = [x for x in items if x.get("id") != record["id"]]
            video = record["result"]
            items.append({"id": record["id"], "video_id": video.get("video_id", ""),
                          "title": video.get("title", ""), "channel": video.get("channel", ""),
                          "source": video.get("source", ""), "updated_at": record["updated_at"]})
            try:
                self._write("index.json", {"schema_version": 1, "items": items}, sha)
                return
            except HistoryError as exc:
                if attempt == 1 or "concurrently" not in str(exc):
                    raise


def verify_password(provided: str, expected: str) -> bool:
    """Use constant-time compare and refuse blank archive passwords."""
    return bool(expected) and hmac.compare_digest(provided.encode(), expected.encode())
