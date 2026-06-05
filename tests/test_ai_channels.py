from desktop_sprite.ai.channel import AIText
from desktop_sprite.ai.channels.pet_bubble import PetBubbleChannel
from desktop_sprite.ai.channels.chat_panel import ChatPanelChannel
from desktop_sprite.ai.channels.os_notification import OsNotificationChannel
from PySide6.QtWidgets import QSystemTrayIcon


# --- PetBubbleChannel ---

class _FakeOverlay:
    def __init__(self):
        self.shown = []
    def show_message(self, msg):
        self.shown.append(msg)


def test_pet_bubble_channel_dispatches_to_overlay():
    overlay = _FakeOverlay()
    ch = PetBubbleChannel(overlay=overlay)
    msg = AIText(text="hi", source="ai", use_case_id="x", timestamp=0.0)
    ch.dispatch(msg)
    assert overlay.shown == [msg]


def test_pet_bubble_channel_handles_overlay_error():
    class BadOverlay:
        def show_message(self, msg):
            raise RuntimeError("boom")
    ch = PetBubbleChannel(overlay=BadOverlay())
    ch.dispatch(AIText(text="x", source="ai", use_case_id="y", timestamp=0.0))  # 不应抛


# --- ChatPanelChannel ---

class _FakePanel:
    def __init__(self):
        self.appended = []
    def append_history(self, msg):
        self.appended.append(msg)


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
