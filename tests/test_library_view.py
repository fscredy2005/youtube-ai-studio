from studio.library_view import (
    SORT_OPTIONS, formatted_saved_date, search_and_sort, thumbnail_url,
)


ROWS = [
    {"id": "A", "video_id": "WYsRZXlSmLA", "title": "Hack ANYTHING",
     "channel": "Paul Hibbert", "updated_at": "2026-11-15T08:37:35+00:00"},
    {"id": "B", "video_id": "abcdEF012_-", "title": "Treg: Open Source Higgsfield",
     "channel": "Julian Goldie", "updated_at": "2026-11-15T08:40:38+00:00"},
    {"id": "C", "video_id": "", "title": "French transcript",
     "channel": "My Upload", "updated_at": "2026-11-14T08:00:00+00:00"},
]


def test_search_by_title_or_channel_is_case_insensitive():
    assert [r["id"] for r in search_and_sort(ROWS, "hibbert")] == ["A"]
    assert [r["id"] for r in search_and_sort(ROWS, "HIGGSFIELD")] == ["B"]
    assert [r["id"] for r in search_and_sort(ROWS, "  my upload ")] == ["C"]
    assert search_and_sort(ROWS, "not found") == []


def test_saved_date_and_title_orderings():
    assert [r["id"] for r in search_and_sort(ROWS)] == ["B", "A", "C"]
    assert [r["id"] for r in search_and_sort(ROWS, sort_by="Oldest saved")] == ["C", "A", "B"]
    assert [r["id"] for r in search_and_sort(ROWS, sort_by="Title A–Z")] == ["C", "A", "B"]
    assert [r["id"] for r in search_and_sort(ROWS, sort_by="Title Z–A")] == ["B", "A", "C"]
    assert len(SORT_OPTIONS) == 4


def test_sorts_different_timezones_chronologically():
    data = [
        {"id": "early", "updated_at": "2026-11-15T12:00:00+02:00"},
        {"id": "later", "updated_at": "2026-11-15T11:00:00+00:00"},
    ]
    assert [r["id"] for r in search_and_sort(data)] == ["later", "early"]


def test_youtube_thumbnail_only_for_safe_video_ids():
    assert thumbnail_url("WYsRZXlSmLA") == "https://i.ytimg.com/vi/WYsRZXlSmLA/mqdefault.jpg"
    assert thumbnail_url("") is None
    assert thumbnail_url("uploaded:notes") is None
    assert thumbnail_url("../bad-path") is None
    assert thumbnail_url("https://example.com") is None


def test_saved_date_is_paris_local_and_missing_date_is_safe():
    assert formatted_saved_date(ROWS[0]) == "15 Nov 2026 · 09:37"
    assert formatted_saved_date({"updated_at": "wrong"}) == "Save date unavailable"


def test_no_mutation_of_index_or_network_dependencies():
    copied = [r.copy() for r in ROWS]
    assert search_and_sort(ROWS, "a")
    assert ROWS == copied
