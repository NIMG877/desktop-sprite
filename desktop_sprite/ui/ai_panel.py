"""AI 互动面板（主窗子页，FluentUI 风格）。

布局与其它子页一致：48/80/48/32 边距、CardWidget 包段落、SubtitleLabel
做小标题。历史区用 qfluentwidgets.PlainTextEdit（只读、带行数上限），
状态用 BodyLabel 实时反映 idle / thinking / fallback。底部一行
`清空历史`（次要）+ `发送测试事件`（主要）。
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    FluentIcon as FIF,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    SubtitleLabel,
    TitleLabel,
)

from desktop_sprite.ai.channel import AIText


_STATUS_LABEL: dict[str, str] = {
    "idle": "空闲",
    "thinking": "思考中…",
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
        self.setObjectName("aiPanelPage")
        self._orchestrator = orchestrator
        self._history_max_lines = history_max_lines

        # ---- 顶部标题 ----
        self._title = TitleLabel("AI 互动", self)
        self._subtitle = BodyLabel(
            "和小翼的对话历史。v1 暂只读 LLM 真实输出，后续再扩展交互。",
            self,
        )
        self._subtitle.setWordWrap(True)

        # ---- 历史卡片 ----
        self._history_card = CardWidget(self)
        self._history_card.setObjectName("aiHistoryCard")
        history_layout = QVBoxLayout(self._history_card)
        history_layout.setContentsMargins(24, 18, 24, 18)
        history_layout.setSpacing(10)
        history_layout.addWidget(SubtitleLabel("对话历史", self._history_card))
        self._history = PlainTextEdit(self._history_card)
        self._history.setReadOnly(True)
        self._history.setMinimumHeight(280)
        self._history.document().setMaximumBlockCount(history_max_lines)
        history_layout.addWidget(self._history, 1)

        # ---- 状态 + 操作卡片 ----
        self._status_card = CardWidget(self)
        self._status_card.setObjectName("aiStatusCard")
        status_layout = QVBoxLayout(self._status_card)
        status_layout.setContentsMargins(24, 18, 24, 18)
        status_layout.setSpacing(10)
        status_layout.addWidget(SubtitleLabel("运行状态", self._status_card))

        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        status_label = BodyLabel("状态：", self._status_card)
        self._status = StrongBodyLabel("空闲", self._status_card)
        status_row.addWidget(status_label)
        status_row.addWidget(self._status, 1)
        status_layout.addLayout(status_row)

        status_layout.addWidget(
            BodyLabel(
                "「发送测试事件」会向 orchestrator 投递一次 test.probe 用例，"
                "结果会同时落到气泡、这里的历史和系统通知。",
                self._status_card,
            )
        )

        button_row = QHBoxLayout()
        button_row.setSpacing(12)
        button_row.addStretch(1)
        self._clear_btn = PushButton("清空历史", self._status_card)
        self._clear_btn.setIcon(FIF.DELETE)
        self._clear_btn.clicked.connect(self.clear_history)
        self._trigger_btn = PrimaryPushButton("发送测试事件", self._status_card)
        self._trigger_btn.setIcon(FIF.SEND)
        self._trigger_btn.clicked.connect(self._on_trigger_clicked)
        button_row.addWidget(self._clear_btn)
        button_row.addWidget(self._trigger_btn)
        status_layout.addLayout(button_row)

        # ---- 页面布局 ----
        page = QVBoxLayout(self)
        page.setContentsMargins(48, 80, 48, 32)
        page.setSpacing(16)
        page.addWidget(self._title)
        page.addWidget(self._subtitle)
        page.addWidget(self._history_card, 1)
        page.addWidget(self._status_card)

    # ---- public API（ChatPanelChannel 与测试用）----

    def append_history(self, message: AIText) -> None:
        ts = datetime.fromtimestamp(message.timestamp).strftime("%H:%M:%S")
        line = f"[{ts}] [{message.source}] {message.text}"
        self._history.appendPlainText(line)

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
