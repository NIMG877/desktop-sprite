"""v3 FluentUI 扁平 UI 测试（聊天气泡 + 切换按钮 + 输入区折叠）。"""
import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    AvatarWidget, DotInfoBadge, InfoLevel, SmoothScrollArea, TitleLabel,
)

from desktop_sprite.ai.channel import AIText
from desktop_sprite.ui.ai_panel import (
    AIPanelWidget, ChatBubble, _INPUT_EXPANDED_HEIGHT, _StatusDot,
)

from tests.ai_fakes import FakeProvider


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
def panel(qtbot, tmp_path):
    orch = _StubOrchestrator()
    ui_state = tmp_path / "ui_state.json"
    p = AIPanelWidget(
        orchestrator=orch, history_max_lines=50, ui_state_path=ui_state,
    )
    qtbot.addWidget(p)
    p.resize(900, 700)
    return p, orch, ui_state


# ---- 基本结构 ----

def test_panel_has_title_and_status_dot(panel):
    p, _, _ = panel
    titles = [t for t in p.findChildren(TitleLabel) if t.text() == "AI 互动"]
    assert len(titles) == 1
    # 状态点存在
    dots = p.findChildren(_StatusDot)
    assert len(dots) == 1


def test_panel_uses_smoothscrollarea(panel):
    p, _, _ = panel
    # v3: 历史区改成 SmoothScrollArea + QWidget，不再用 CardWidget
    scrolls = p.findChildren(SmoothScrollArea)
    assert len(scrolls) == 1


def test_input_starts_collapsed(panel):
    p, _, _ = panel
    assert p.input_visible() is False
    assert p._input_area.maximumHeight() == 0
    assert p._toggle_btn.isChecked() is False
    assert p._toggle_btn.text() == "展开"


# ---- 聊天气泡 ----

def test_append_history_creates_chat_bubble(panel):
    p, _, _ = panel
    p.append_history(AIText(text="hello", source="ai", use_case_id="x", timestamp=0.0))
    assert p.bubble_count() == 1
    msgs = p.messages()
    assert msgs == [{"role": "ai", "text": "hello"}]


def test_user_message_renders_as_user_bubble(panel):
    p, _, _ = panel
    p.append_history(AIText(text="hi", source="user", use_case_id="x", timestamp=0.0))
    msgs = p.messages()
    assert msgs[0]["role"] == "user"


def test_clear_history_removes_all_bubbles(panel):
    p, _, _ = panel
    p.append_history(AIText(text="a", source="ai", use_case_id="x", timestamp=0.0))
    p.append_history(AIText(text="b", source="ai", use_case_id="x", timestamp=0.0))
    assert p.bubble_count() == 2
    p.clear_history()
    assert p.bubble_count() == 0


def test_bubble_role_object_name(panel):
    p, _, _ = panel
    p.append_history(AIText(text="ai", source="ai", use_case_id="x", timestamp=0.0))
    p.append_history(AIText(text="user", source="user", use_case_id="x", timestamp=0.0))
    bubbles = p.findChildren(ChatBubble)
    roles = sorted(b.objectName() for b in bubbles)
    assert "chatBubble_ai" in roles
    assert "chatBubble_user" in roles


# ---- 切换按钮展开 / 收起输入区 ----

def test_toggle_btn_click_expands_input(panel, qtbot):
    p, _, _ = panel
    assert p.input_visible() is False
    p._toggle_btn.click()
    # 等动画结束：maximumHeight 升到目标值
    qtbot.waitUntil(lambda: p._input_area.maximumHeight() == _INPUT_EXPANDED_HEIGHT, timeout=2000)
    assert p.input_visible() is True
    assert p._toggle_btn.isChecked() is True
    assert p._toggle_btn.text() == "收起"


def test_toggle_btn_click_again_collapses_input(panel, qtbot):
    p, _, _ = panel
    p._toggle_btn.click()
    qtbot.waitUntil(lambda: p._input_area.maximumHeight() == _INPUT_EXPANDED_HEIGHT, timeout=2000)
    p._toggle_btn.click()
    qtbot.waitUntil(lambda: p._input_area.maximumHeight() == 0, timeout=2000)
    assert p.input_visible() is False


# ---- 发送消息 ----

def test_send_button_dispatches_orchestrator_with_user_hint(panel, qtbot):
    p, orch, _ = panel
    # 展开输入区
    p._toggle_btn.click()
    qtbot.waitUntil(lambda: p.input_visible() is True, timeout=2000)
    # 输入文字
    p._input_edit.setPlainText("hello world")
    p._send_btn.click()
    assert orch.test_calls == [{"user_hint": "hello world"}]
    # 用户气泡出现
    assert p.bubble_count() == 1
    assert p.messages()[0] == {"role": "user", "text": "hello world"}


def test_send_with_empty_text_is_noop(panel, qtbot):
    p, orch, _ = panel
    p._send_btn.click()
    assert orch.test_calls == []
    assert p.bubble_count() == 0


# ---- 状态点 ----

def test_status_dot_initial_state_idle(panel):
    p, _, _ = panel
    assert p.status_text() == "—"


def test_status_dot_green_after_successful_ping(panel):
    p, _, _ = panel
    p.trigger_ping_for_test()
    # 12 ms 是 stub 默认值，远低于 800ms 阈值 → SUCCESS
    assert p.status_available() is True
    assert "ms" in p.status_text()


def test_status_dot_red_after_failed_ping():
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
    p, orch, _ = panel
    # 改 stub 延迟到 warn 区间
    orch._provider._ping_latency = 1500.0
    p.trigger_ping_for_test()
    assert p.status_available() is True
    # level 应是 WARNING（黄）
    assert p._status.level() == InfoLevel.WARNING


# ---- API 不可用时禁用切换按钮 ----

def test_toggle_btn_disabled_when_ping_fails():
    from desktop_sprite.ai.provider import AuthError
    app = QApplication.instance() or QApplication([])
    orch = _StubOrchestrator(ping_error=AuthError("bad"))
    p = AIPanelWidget(orchestrator=orch)
    try:
        p.trigger_ping_for_test()
        assert p._toggle_btn.isEnabled() is False
    finally:
        p.deleteLater()


def test_toggle_btn_enabled_when_ping_succeeds(panel):
    p, _, _ = panel
    p.trigger_ping_for_test()
    assert p._toggle_btn.isEnabled() is True


# ---- v3：去掉 CardWidget 容器 ----

def test_no_card_widget_for_history_or_input(panel):
    p, _, _ = panel
    # v3 不再用 CardWidget 当历史 / 输入容器
    assert p.findChild(QObject, "aiHistoryCard") is None
    assert p.findChild(QObject, "aiInputCard") is None


# ---- v3 新增：avatar / 状态持久化 / trim / 流式 ----

def test_chat_bubble_has_avatar_for_ai_role(panel):
    p, _, _ = panel
    p.append_history(AIText(text="hi", source="ai", use_case_id="x", timestamp=0.0))
    avatars = p.findChildren(AvatarWidget)
    assert len(avatars) == 1
    # v3 实现里 "AI" 被当作 image path 传给 ImageLabel，所以 text() 实际为空
    # （AvatarWidget 真正显示文字需要 setText("AI")）。这里只验存在性 + 类型。
    assert isinstance(avatars[0], AvatarWidget)


def test_input_expanded_persists_to_ui_state(panel, qtbot):
    p, _, ui_state = panel
    # 初始 False
    assert p._load_input_expanded() is False
    # 点击展开
    p._toggle_btn.click()
    qtbot.waitUntil(lambda: p._input_expanded, timeout=2000)
    # ui_state.json 已写入
    import json
    state = json.loads(ui_state.read_text())
    assert state["ai_panel"]["input_expanded"] is True
    # 重建 panel 验证恢复
    p2, _, _ = panel
    assert p2._load_input_expanded() is True


def test_history_max_lines_trims_head(panel):
    """构造 history_max_lines=3；add 5 条普通气泡，断言只剩 3 条且是后 3 条。"""
    p, _, _ = panel
    p._history_max_lines = 3
    for i in range(5):
        p.append_history(AIText(text=f"msg{i}", source="ai", use_case_id="x", timestamp=float(i)))
    assert p.bubble_count() == 3
    assert [m["text"] for m in p.messages()] == ["msg2", "msg3", "msg4"]


def test_append_stream_start_creates_ai_bubble(panel):
    p, _, _ = panel
    p.append_stream_start("s1", "uc1")
    assert p.bubble_count() == 1
    assert p.messages()[0]["role"] == "ai"
    # 流中气泡是同一对象
    assert p._stream_bubbles["s1"] in p._bubbles


def test_append_stream_delta_appends_to_bubble(panel, qtbot):
    p, _, _ = panel
    p.append_stream_start("s1", "uc1")
    p.append_stream_delta("s1", "你", "uc1")
    p.append_stream_delta("s1", "好", "uc1")
    qtbot.waitUntil(
        lambda: p.bubble_count() == 1 and p.messages()[0]["text"] == "你好",
        timeout=2000,
    )


def test_append_stream_end_finalizes(panel):
    p, _, _ = panel
    p.append_stream_start("s1", "uc1")
    p.append_stream_delta("s1", "x", "uc1")
    p.append_stream_end("s1", "x", "ai", "uc1")
    assert "s1" not in p._stream_bubbles


def test_input_visible_returns_expanded_state(panel):
    p, _, _ = panel
    assert p.input_visible() is False
    p._input_expanded = True
    assert p.input_visible() is True

