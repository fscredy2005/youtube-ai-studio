import base64
import json
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import unquote

import pytest
from studio.history import (GitHubHistory, HistoryError, make_record,
                            record_id, restore_record, verify_password, summary_slot)
from studio.models import Segment, VideoResult


class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeGitHub:
    def __init__(self, is_private=True):
        self.files = {}
        self.private = is_private
        self.operations = []

    def __call__(self, request, timeout=None):
        method, url = request.get_method(), request.full_url
        self.operations.append((method, url))
        if url.endswith("/repos/test/private/"):
            return FakeResponse(json.dumps({"private": self.private}).encode())
        path = unquote(url.split("/contents/", 1)[1])
        if method == "GET":
            if path not in self.files:
                raise HTTPError(url, 404, "Not Found", {}, None)
            value = self.files[path]
            return FakeResponse(json.dumps({"sha": "sha-"+str(len(value)),
                                            "content": base64.b64encode(value).decode()}).encode())
        if method == "PUT":
            data = json.loads(request.data)
            old = self.files.get(path)
            if old is not None and data.get("sha") != "sha-" + str(len(old)):
                raise HTTPError(url, 409, "Conflict", {}, None)
            if old is None and "sha" in data:
                raise HTTPError(url, 409, "Conflict", {}, None)
            self.files[path] = base64.b64decode(data["content"])
            return FakeResponse(b'{"content": {}}')
        raise AssertionError(method)


def example():
    return VideoResult(video_id="abcdEF012_-", title="A video", channel="Example",
                       segments=[Segment(0.0, 4.5, "Hello, hello.")], summary="Initial summary")


def test_roundtrip_utf8_and_all_analysis_fields():
    result = example()
    result.summary = "Résumé avec caractères éè"
    saved = make_record(result, takeaways="Key ideas", questions=[{"question": "Why?", "answer": "Because"}],
                        variants={"Detailed summary": {"text": "Long", "engine": "Gemini", "note": ""}},
                        manual_duration="18:45")
    restored, extra = restore_record(saved)
    assert restored == result
    assert extra["variants"]["Detailed summary"]["text"] == "Long"
    assert extra["questions"][0]["answer"] == "Because"
    assert extra["manual_duration"] == "18:45"


def test_private_archive_save_load_search_index_and_update_without_ai():
    api = FakeGitHub()
    store = GitHubHistory("test/private", "fine-grained-token", opener=api)
    item = make_record(example(), takeaways="Important")
    store.save(item)
    assert store.load(record_id(example()))["takeaways"] == "Important"
    assert store.list_index()[0]["title"] == "A video"
    later = make_record(example(), variants={"Research notes": {"text": "Saved notes", "engine": "Gemini", "note": ""}})
    store.save(later)
    assert store.load(item["id"])["variants"]["Research notes"]["text"] == "Saved notes"
    assert len(store.list_index()) == 1
    assert all("api.github.com" in url for _, url in api.operations)


def test_private_required_and_invalid_keys_rejected():
    api = FakeGitHub(is_private=False)
    store = GitHubHistory("test/private", "token", opener=api)
    with pytest.raises(HistoryError, match="PRIVATE"):
        store.list_index()
    with pytest.raises(HistoryError, match="Invalid analysis"):
        store.load("../../secrets")
    with pytest.raises(HistoryError):
        GitHubHistory("https://malicious.example", "token")


def test_pasted_source_hash_prevents_same_title_collisions():
    a = VideoResult(video_id="", title="My notes", segments=[Segment(0, 0, "aaa")])
    b = VideoResult(video_id="", title="My notes", segments=[Segment(0, 0, "bbb")])
    assert record_id(a).startswith("input-")
    assert record_id(a) != record_id(b)


def test_password_is_required_and_exact():
    assert verify_password("MySecret99", "MySecret99")
    assert not verify_password("MySecret99 ", "MySecret99")
    assert not verify_password("", "")

def test_preserves_both_english_and_french_versions():
    api = FakeGitHub()
    store = GitHubHistory("test/private", "token", opener=api)
    english = example()
    store.save(make_record(english, summary_language="English"))
    french = example()
    french.summary = "Un résumé français"
    store.save(make_record(french, summary_language="Français"))
    archived = store.load(record_id(french))
    assert archived["variants"][summary_slot("Quick summary", "English")]["text"] == "Initial summary"
    assert archived["variants"][summary_slot("Quick summary", "Français")]["text"] == "Un résumé français"
    _, extra = restore_record(archived)
    assert extra["summary_language"] == "Français"
