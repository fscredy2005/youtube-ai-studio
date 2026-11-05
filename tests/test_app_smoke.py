import pytest


def test_streamlit_ui_loads_without_a_video_url():
    st = pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("app.py", default_timeout=30).run()
    assert not at.exception, str(at.exception)
    assert any("Analyze video" in b.label for b in at.button)
