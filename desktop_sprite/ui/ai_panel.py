"""AI 互动面板（主窗子页）。

只读历史 QTextEdit + 状态指示 QLabel + "发送测试事件"按钮 + "清空"按钮。
**不**写盘；只通过 `orchestrator.trigger_test()` 触发框架验证。
"""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from desktop_sprite.ai.channel import AIText


_STATUS_LABEL: dict[str, str] = {
    "idle": "空闲",
    "thinking": "思考中...",
    "fallback": "已回退",
}


class AIPanelWidget(QWidget):
    def __init__(
        self,
        orchestrator,  # 实际类型：AIOrchestrator；这里避免循环 import 用 duck type
        history_max_lines: int = 200,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._orchestrator = orchestrator
        self._history_max_lines = history_max_lines

        self._history = QTextEdit(self)
        self._history.setReadOnly(True)
        self._history.document().setMaximumBlockCount(history_max_lines)

        self._status = QLabel("空闲", self)
        font = QFont()
        font.setPointSize(10)
        self._status.setFont(font)

        self._trigger_btn = QPushButton("发送测试事件", self)
        self._trigger_btn.clicked.connect(self._on_trigger_clicked)

        self._clear_btn = QPushButton("清空历史", self)
        self._clear_btn.clicked.connect(self.clear_history)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("AI 互动历史", self))
        layout.addWidget(self._history)
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("状态：", self))
        status_row.addWidget(self._status)
        status_row.addStretch(1)
        status_row.addWidget(self._clear_btn)
        status_row.addWidget(self._trigger_btn)
        layout.addLayout(status_row)

    # ---- public API（ChatPanelChannel 与测试用）----

    def append_history(self, message: AIText) -> None:
        from datetime import datetime
        ts = datetime.fromtimestamp(message.timestamp).strftime("%H:%M:%S")
        line = f"[{ts}] [{message.source}] {message.text}"
        self._history.append(line)

    def clear_history(self) -> None:
        self._history.clear()

    def set_status(self, status: str) -> None:
        """status 是任意字符串；'idle' / 'thinking' / 'fallback' 走映射，其它原样。"""
        label = _STATUS_LABEL.get(status, status)
        self._status.setText(label)

    def history_text(self) -> str:
        return self._history.toPlainText()

    def status_text(self) -> str:
        return self._status.text()

    def trigger_button_text(self) -> str:
        return self._trigger_btn.text()

    def click_trigger(self) -> None:
        """测试入口；等价于点击按钮。"""
        self._on_trigger_clicked()

    # ---- private ----

    def _on_trigger_clicked(self) -> None:
        if self._orchestrator is not None:
            self._orchestrator.trigger_test()
