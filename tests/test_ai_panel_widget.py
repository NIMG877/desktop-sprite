"""v2 聊天气泡 UI 测试。"""
import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    CardWidget, DotInfoBadge, InfoLevel,
    SmoothScrollArea, TextEdit,
)

from desktop_sprite.ai.channel import AIText
from desktop_sprite.ai.orchestrator import AIOrchestrator
from desktop_sprite.ui.ai_panel import (
    AIPanelWidget, ChatBubble, _INPUT_EXPANDED_HEIGHT, _StatusDot,
)

from tests.ai_fakes import FakeProvider, make_orchestrator


# ---- 通用 fixture ----

class _StubOrchestrator:
    """轻量 stub：panel 用 trigger_test / ping_async，绕过真 orchestrator。"""
    def __init__(self, ping_latency_ms=12.0, ping_error=None):
        self._provider = FakeProvider(ping_latency_ms=ping_latency_ms, ping_error=ping_error)
        self.test_calls: list[dict] = []

    def trigger_test(self, user_hint: str = "") -> None:
        self.test_calls.append({"user_hint": user_hint})

    def ping_async(self, callback) -> None:
        try:
            ms = self._provider.ping()
            callback(ms, None)
        except Exception as e:
            callback(None, e)

    @property
    def provider(self):
        return self._provider


@pytest.fixture
def panel(qtbot):
    orch = _StubOrchestrator()
    p = AIPanelWidget(orchestrator=orch, history_max_lines=50)
    qtbot.addWidget(p)
    p.resize(900, 700)
    return p, orch


# ---- 基本结构 ----

def test_panel_has_title_and_status_dot(panel):
    p, _ = panel
    title_texts = [t for t in p.findChildren(__import__('qfluentwidgets').TitleLabel).__class__.__name__]
    # 标题为 "AI 互动"
    from qfluentwidgets import TitleLabel
    titles = [t for t in p.findChildren(TitleLabel) if t.text() == "AI 互动"]
    assert len(titles) == 1
    # 状态点存在
    dots = p.findChildren(_StatusDot)
    assert len(dots) == 1


def test_panel_uses_smoothscrollarea_and_history_card(panel):
    p, _ = panel
    scrolls = p.findChildren(SmoothScrollArea)
    assert len(scrolls) == 1
    history_cards = [c for c in p.findChildren(CardWidget) if c.objectName() == "aiHistoryCard"]
    assert len(history_cards) == 1


def test_panel_has_fab_button(panel):
    p, _ = panel
    from desktop_sprite.ui.ai_panel import _FabButton
    fabs = p.findChildren(_FabButton)
    assert len(fabs) == 1
    assert fabs[0].size().width() == 56
    assert fabs[0].size().height() == 56


def test_input_card_starts_collapsed(panel):
    p, _ = panel
    input_cards = [c for c in p.findChildren(CardWidget) if c.objectName() == "aiInputCard"]
    assert len(input_cards) == 1
    assert p.input_visible() is False
    assert input_cards[0].maximumHeight() == 0


# ---- 聊天气泡 ----

def test_append_history_creates_chat_bubble(panel):
    p, _ = panel
    p.append_history(AIText(text="hello", source="ai", use_case_id="x", timestamp=0.0))
    assert p.bubble_count() == 1
    msgs = p.messages()
    assert msgs == [{"role": "ai", "text": "hello"}]


def test_user_message_renders_as_user_bubble(panel):
    p, _ = panel
    p.append_history(AIText(text="hi", source="user", use_case_id="x", timestamp=0.0))
    msgs = p.messages()
    assert msgs[0]["role"] == "user"


def test_clear_history_removes_all_bubbles(panel):
    p, _ = panel
    p.append_history(AIText(text="a", source="ai", use_case_id="x", timestamp=0.0))
    p.append_history(AIText(text="b", source="ai", use_case_id="x", timestamp=0.0))
    assert p.bubble_count() == 2
    p.clear_history()
    assert p.bubble_count() == 0


def test_bubble_role_object_name(panel):
    p, _ = panel
    p.append_history(AIText(text="ai", source="ai", use_case_id="x", timestamp=0.0))
    p.append_history(AIText(text="user", source="user", use_case_id="x", timestamp=0.0))
    bubbles = p.findChildren(ChatBubble)
    roles = sorted(b.objectName() for b in bubbles)
    assert "chatBubble_ai" in roles
    assert "chatBubble_user" in roles


# ---- FAB 切换输入区 ----

def test_fab_click_expands_input(panel, qtbot):
    p, _ = panel
    assert p.input_visible() is False
    p._fab.click()
    # 等动画结束：maximumHeight 升到目标值
    qtbot.waitUntil(lambda: p._input_card.maximumHeight() == _INPUT_EXPANDED_HEIGHT, timeout=2000)


def test_fab_click_again_collapses_input(panel, qtbot):
    p, _ = panel
    p._fab.click()
    qtbot.waitUntil(lambda: p.input_visible() is True, timeout=2000)
    p._fab.click()
    qtbot.waitUntil(lambda: p.input_visible() is False, timeout=2000)


# ---- 发送消息 ----

def test_send_button_dispatches_orchestrator_with_user_hint(panel, qtbot):
    p, orch = panel
    # 展开输入区
    p._fab.click()
    qtbot.waitUntil(lambda: p.input_visible() is True, timeout=2000)
    # 输入文字
    p._input_edit.setPlainText("hello world")
    p._send_btn.click()
    assert orch.test_calls == [{"user_hint": "hello world"}]
    # 用户气泡出现
    assert p.bubble_count() == 1
    assert p.messages()[0] == {"role": "user", "text": "hello world"}


def test_send_with_empty_text_is_noop(panel, qtbot):
    p, orch = panel
    p._send_btn.click()
    assert orch.test_calls == []
    assert p.bubble_count() == 0


# ---- 状态点 ----

def test_status_dot_initial_state_idle(panel):
    p, _ = panel
    assert p.status_text() == "—"


def test_status_dot_green_after_successful_ping(panel):
    p, _ = panel
    p.trigger_ping_for_test()
    # 12 ms 是 stub 默认值，远低于 800ms 阈值 → SUCCESS
    assert p.status_available() is True
    assert "ms" in p.status_text()


def test_status_dot_red_after_failed_ping():
    from PySide6.QtWidgets import QApplication
    from desktop_sprite.ai.provider import AuthError
    app = QApplication.instance() or QApplication([])
    orch = _StubOrchestrator(ping_error=AuthError("bad"))
    p = AIPanelWidget(orchestrator=orch)
    try:
        p.trigger_ping_for_test()
        assert p.status_available() is False
        assert "不可用" in p.status_text()
    finally:
        p.deleteLater()


def test_status_dot_yellow_for_warn_latency(panel):
    p, orch = panel
    # 改 stub 延迟到 warn 区间
    orch._provider._ping_latency = 1500.0
    p.trigger_ping_for_test()
    assert p.status_available() is True
    # level 应是 WARNING（黄）
    assert p._status.level() == InfoLevel.WARNING


# ---- API 不可用时禁用 FAB ----

def test_fab_disabled_when_ping_fails():
    from PySide6.QtWidgets import QApplication
    from desktop_sprite.ai.provider import AuthError
    app = QApplication.instance() or QApplication([])
    orch = _StubOrchestrator(ping_error=AuthError("bad"))
    p = AIPanelWidget(orchestrator=orch)
    try:
        p.trigger_ping_for_test()
        assert p._fab.isEnabled() is False
    finally:
        p.deleteLater()


def test_fab_enabled_when_ping_succeeds(panel):
    p, _ = panel
    p.trigger_ping_for_test()
    assert p._fab.isEnabled() is True


# ---- v3：去掉 CardWidget 容器 ----

def test_no_card_widget_for_history_or_input(panel):
    p, _ = panel
    # v3 不再用 CardWidget 当历史 / 输入容器
    assert p.findChild(QObject, "aiHistoryCard") is None
    assert p.findChild(QObject, "aiInputCard") is None
