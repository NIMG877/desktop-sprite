import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from desktop_sprite.ui.debug_widget import DebugWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_debug_widget_requests_spirit_mark_through_callback():
    _app()
    calls: list[str] = []
    widget = DebugWidget(lambda: calls.append("grant") or "已生成灵痕")

    widget.request_spirit_mark()

    assert calls == ["grant"]
    assert widget.status_label.text() == "已生成灵痕"
