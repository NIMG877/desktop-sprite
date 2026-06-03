from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, FluentIcon as FIF, PrimaryPushButton, SubtitleLabel, TitleLabel


class DebugWidget(QWidget):
    def __init__(
        self,
        on_request_spirit_mark: Callable[[], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("debugPage")
        self.on_request_spirit_mark = on_request_spirit_mark or (lambda: "未接入调试请求。")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 72, 48, 32)
        layout.setSpacing(16)
        layout.addWidget(TitleLabel("调试", self))
        layout.addWidget(self._spirit_mark_card())
        layout.addStretch(1)

    def _spirit_mark_card(self) -> CardWidget:
        card = CardWidget(self)
        card.setObjectName("debugSpiritMarkCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(10)
        layout.addWidget(SubtitleLabel("请求生成灵痕", card))
        self.status_label = BodyLabel("通过正式授予流程写入背包和灵痕存档。", card)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        button = PrimaryPushButton(FIF.ADD, "生成", card)
        button.clicked.connect(self.request_spirit_mark)
        layout.addWidget(button)
        return card

    def request_spirit_mark(self) -> None:
        try:
            message = self.on_request_spirit_mark()
        except Exception as exc:
            message = f"请求失败：{exc}"
        self.status_label.setText(message)
