from desktop_sprite.ai.channel import AIText
from desktop_sprite.ai.channels.pet_bubble import PetBubbleChannel
from desktop_sprite.ai.channels.chat_panel import ChatPanelChannel
from desktop_sprite.ai.channels.os_notification import OsNotificationChannel
from PySide6.QtWidgets import QSystemTrayIcon


# --- PetBubbleChannel ---

class _FakeOverlay:
    def __init__(self):
        self.shown = []
    def show_message(self, text):
        self.shown.append(text)


def test_pet_bubble_channel_dispatches_to_overlay():
    overlay = _FakeOverlay()
    ch = PetBubbleChannel(bubble_provider=lambda: overlay)
    msg = AIText(text="hi", source="ai", use_case_id="x", timestamp=0.0)
    ch.dispatch(msg)
    assert overlay.shown == ["hi"]


def test_pet_bubble_channel_handles_overlay_error():
    """provider 返回 None 时不出错；真实 overlay 抛错由 orchestrator 兜底。"""
    ch = PetBubbleChannel(bubble_provider=lambda: None)
    ch.dispatch(AIText(text="x", source="ai", use_case_id="y", timestamp=0.0))  # 不应抛


# --- ChatPanelChannel ---

def test_chat_panel_channel_dispatches_to_panel_when_provided():
    panel = _FakePanel()
    ch = ChatPanelChannel(panel_provider=lambda: panel)
    msg = AIText(text="hi", source="ai", use_case_id="x", timestamp=0.0)
    ch.dispatch(msg)
    assert panel.appended == [msg]


def test_chat_panel_channel_noop_when_panel_none():
    calls = []
    ch = ChatPanelChannel(panel_provider=lambda: None)
    ch.dispatch(AIText(text="hi", source="ai", use_case_id="x", timestamp=0.0))
    assert calls == []  # 即没 panel、也没异常


# --- OsNotificationChannel ---

def test_os_notification_noop_when_tray_is_none():
    ch = OsNotificationChannel(tray_provider=lambda: None)
    ch.dispatch(AIText(text="hi", source="ai", use_case_id="x", timestamp=0.0))  # 不应抛


def test_os_notification_calls_show_message_when_tray_present():
    class FakeTray:
        def __init__(self):
            self.shown = []
        def showMessage(self, title, text, icon=QSystemTrayIcon.Information, msecs=5000):
            self.shown.append((title, text))
    tray = FakeTray()
    ch = OsNotificationChannel(tray_provider=lambda: tray)
    ch.dispatch(AIText(text="通知一下", source="ai", use_case_id="x", timestamp=0.0))
    assert len(tray.shown) == 1
    title, text = tray.shown[0]
    assert "通知一下" in text


# --- ChatPanelChannel 流式转发 ---


class _FakePanel:
    """替身 panel：只关心 stream_* 方法被调用的次数。"""
    def __init__(self):
        self.stream_starts: list[tuple[str, str]] = []
        self.stream_deltas: list[tuple[str, str, str]] = []
        self.stream_ends: list[tuple[str, str, str, str]] = []
        self.appended: list[AIText] = []

    def append_history(self, msg: AIText) -> None:
        self.appended.append(msg)

    def append_stream_start(self, stream_id: str, use_case_id: str) -> None:
        self.stream_starts.append((stream_id, use_case_id))

    def append_stream_delta(self, stream_id: str, delta: str, use_case_id: str) -> None:
        self.stream_deltas.append((stream_id, delta, use_case_id))

    def append_stream_end(self, stream_id: str, full_text: str, source: str, use_case_id: str) -> None:
        self.stream_ends.append((stream_id, full_text, source, use_case_id))


def test_chat_panel_channel_dispatches_stream_to_panel():
    panel = _FakePanel()
    ch = ChatPanelChannel(panel_provider=lambda: panel)
    ch.dispatch_stream_start("s1", "uc1")
    ch.dispatch_stream_delta("s1", "你", "uc1")
    ch.dispatch_stream_delta("s1", "好", "uc1")
    ch.dispatch_stream_end("s1", "你好", "ai", "uc1")
    assert panel.stream_starts == [("s1", "uc1")]
    assert panel.stream_deltas == [("s1", "你", "uc1"), ("s1", "好", "uc1")]
    assert panel.stream_ends == [("s1", "你好", "ai", "uc1")]


def test_chat_panel_channel_stream_noop_when_panel_none():
    """panel 不存在时 3 个 stream 方法都安全 no-op。"""
    ch = ChatPanelChannel(panel_provider=lambda: None)
    ch.dispatch_stream_start("s", "u")
    ch.dispatch_stream_delta("s", "x", "u")
    ch.dispatch_stream_end("s", "x", "ai", "u")
    # 不抛错即过


# --- PetBubbleChannel 流式转发 ---


class _FakeBubble:
    def __init__(self):
        self.messages: list[str] = []
        self.appends: list[str] = []
    def show_message(self, text: str) -> None:
        self.messages.append(text)
    def append_text(self, delta: str) -> None:
        self.appends.append(delta)


def test_pet_bubble_channel_dispatches_stream_to_bubble():
    """用 monkeypatch 把 BubbleOverlayWindow 替成 _FakeBubble 工厂。"""
    import desktop_sprite.ai.channels.pet_bubble as mod
    mod.BubbleOverlayWindow = _FakeBubble  # 类替身
    bubble = _FakeBubble()
    ch = PetBubbleChannel(bubble_provider=lambda: bubble)
    ch.dispatch_stream_start("s1", "uc1")
    ch.dispatch_stream_delta("s1", "你", "uc1")
    ch.dispatch_stream_delta("s1", "好", "uc1")
    ch.dispatch_stream_end("s1", "你好", "ai", "uc1")
    assert bubble.messages == [""]  # start → show_message("")
    assert bubble.appends == ["你", "好"]


def test_pet_bubble_channel_stream_noop_when_bubble_none():
    ch = PetBubbleChannel(bubble_provider=lambda: None)
    ch.dispatch_stream_start("s", "u")
    ch.dispatch_stream_delta("s", "x", "u")
    ch.dispatch_stream_end("s", "x", "ai", "u")


# --- OsNotificationChannel 流式转发 ---


class _FakeTray:
    def __init__(self):
        self.notified: list[tuple[str, str]] = []
    def showMessage(self, title: str, msg: str, icon: int = 0, msecs: int = 10000) -> None:
        self.notified.append((title, msg))


def test_os_notification_channel_stream_start_and_delta_are_noop():
    """start / delta 走基类默认 no-op；end 才真正弹通知。"""
    tray = _FakeTray()
    ch = OsNotificationChannel(tray_provider=lambda: tray)
    ch.dispatch_stream_start("s", "u")
    ch.dispatch_stream_delta("s", "a", "u")
    ch.dispatch_stream_delta("s", "b", "u")
    assert tray.notified == []  # 流期间没弹


def test_os_notification_channel_stream_end_dispatches_full_text():
    tray = _FakeTray()
    ch = OsNotificationChannel(tray_provider=lambda: tray)
    ch.dispatch_stream_end("s1", "完整文本", "ai", "uc1")
    assert len(tray.notified) == 1
    title, msg = tray.notified[0]
    assert msg == "完整文本"
