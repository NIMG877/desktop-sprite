import pytest

from desktop_sprite.ui.bubble_overlay import BubbleOverlayWindow
from desktop_sprite.ai.channel import AIText


@pytest.fixture
def overlay(qtbot):
    win = BubbleOverlayWindow(visible_seconds=0.2)
    qtbot.addWidget(win)
    return win


def test_initial_state_invisible(overlay):
    assert not overlay.isVisible()
    assert overlay.current_text() == ""


def test_show_makes_window_visible(overlay, qtbot):
    msg = AIText(text="hi", source="ai", use_case_id="x", timestamp=0.0)
    overlay.show_message(msg)
    qtbot.wait(50)
    assert overlay.isVisible()
    assert overlay.current_text() == "hi"


def test_hide_after_visible_seconds(overlay, qtbot):
    msg = AIText(text="hi", source="ai", use_case_id="x", timestamp=0.0)
    overlay.show_message(msg)
    qtbot.wait(50)
    assert overlay.isVisible()
    qtbot.wait(300)  # visible_seconds=0.2 + 缓冲
    assert not overlay.isVisible()
    assert overlay.current_text() == ""


def test_new_message_replaces_old(overlay, qtbot):
    overlay.show_message(AIText(text="first", source="ai", use_case_id="x", timestamp=0.0))
    qtbot.wait(20)
    overlay.show_message(AIText(text="second", source="ai", use_case_id="x", timestamp=0.1))
    qtbot.wait(20)
    assert overlay.current_text() == "second"
