"""桌宠头顶气泡浮层（v1 简化版）。

单气泡：`show_message` 时取消上一个 timer，覆盖显示新消息；显示满
`visible_seconds` 后自动隐藏。不做 fade in/out / 队列。

参考 `ShowOverlayWindow` 的浮层做法，但只用 QTimer 不用 Qt 动画。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QWidget

from desktop_sprite.ai.channel import AIText


class BubbleOverlayWindow(QWidget):
    """桌宠头顶气泡；不抢占焦点、置顶、关闭时不退出 app。"""

    def __init__(self, visible_seconds: float = 3.0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._visible_seconds = visible_seconds
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_hide_timeout)

        self._label = QLabel("", self)
        self._label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(11)
        self._label.setFont(font)
        self._label.setStyleSheet("")  # 不走 stylesheet（qfluentwidgets 主题安全）

        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(220, 56)
        self._label.setGeometry(0, 0, 220, 56)
        self._current_text = ""

    def current_text(self) -> str:
        return self._current_text

    def show_message(self, message: AIText) -> None:
        """显示一条消息；已有 timer 被取消，新 timer 重新计时。"""
        self._current_text = message.text
        self._label.setText(message.text)
        self._hide_timer.stop()
        self.show()
        # 重新触发布局（首次显示时 sizeHint 未生效）
        self.adjustSize()
        self._hide_timer.start(int(self._visible_seconds * 1000))

    def append_text(self, delta: str) -> None:
        """流式增量：拼到 _label 末尾 + 重置 hide timer + adjustSize 触发布局。"""
        self._current_text += delta
        self._label.setText(self._current_text)
        self._label.adjustSize()
        self._reset_hide_timer()

    def _reset_hide_timer(self) -> None:
        if hasattr(self, "_hide_timer") and self._hide_timer is not None:
            self._hide_timer.stop()
            self._hide_timer.start()

    def _on_hide_timeout(self) -> None:
        """Timer 触发：隐藏窗口并清空当前文本。"""
        self._current_text = ""
        self._label.setText("")
        self.hide()
