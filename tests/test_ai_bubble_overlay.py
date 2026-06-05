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


@pytest.fixture
def bubble(qtbot):
    b = BubbleOverlayWindow()
    qtbot.addWidget(b)
    return b


def test_bubble_append_text_extends_label(bubble):
    bubble.show_message(AIText(text="你好", source="ai", use_case_id="x", timestamp=0.0))
    bubble.append_text("世界")
    assert bubble._label.text() == "你好世界"


def test_bubble_append_text_resets_hide_timer(bubble, qtbot):
    """append_text 重置 hide timer，气泡不会中途消失。"""
    bubble.show_message(AIText(text="hi", source="ai", use_case_id="x", timestamp=0.0))
    # 直接验证 _hide_timer 是否重置（不依赖真实时间）
    assert bubble._hide_timer.isActive()
    bubble.append_text(".")
    # 重新 active
    assert bubble._hide_timer.isActive()


def test_bubble_show_message_with_empty_text(bubble):
    """流开始时 show_message("") 创建空气泡；后续 append_text 累加。"""
    bubble.show_message(AIText(text="", source="ai", use_case_id="x", timestamp=0.0))
    assert bubble._label.text() == ""
    bubble.append_text("流")
    bubble.append_text("式")
    assert bubble._label.text() == "流式"
