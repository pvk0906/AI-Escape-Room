"""Headless UI smoke tests using Streamlit's AppTest (no browser, no API key)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
ROOT_TIMEOUT = 30


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")


def chat_texts(at):
    return [m.markdown[0].value for m in at.chat_message]


def test_v1_shows_setup_error_without_llm():
    at = AppTest.from_file(str(ROOT / "v1/app.py"), default_timeout=ROOT_TIMEOUT).run()
    assert not at.exception
    assert any("No LLM is configured" in e.value for e in at.error)


def test_v2_full_playthrough_through_the_ui():
    at = AppTest.from_file(str(ROOT / "v2/app.py"), default_timeout=ROOT_TIMEOUT).run()
    assert not at.exception
    assert "locked inside an old library" in chat_texts(at)[0]

    moves = [
        "examine the bookshelf", "examine the four books", "enter 3715 on the drawer", "take the silver key",
        "examine the painting", "use the silver key on the painting", "enter 4286 on the door",
    ]
    for move in moves:
        at.chat_input[0].set_value(move).run()
        assert not at.exception
    assert any("You escaped the library" in s.value for s in at.success)


def test_v2_restart_button_resets_game():
    at = AppTest.from_file(str(ROOT / "v2/app.py"), default_timeout=ROOT_TIMEOUT).run()
    at.chat_input[0].set_value("examine the bookshelf").run()
    assert len(at.chat_message) == 3  # intro, player, narration
    next(b for b in at.sidebar.button if "Restart" in b.label).click().run()
    assert len(at.chat_message) == 1
