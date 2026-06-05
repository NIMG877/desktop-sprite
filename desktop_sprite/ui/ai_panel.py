"""AI 互动面板（v3 FluentUI 扁平 + 流式输出）。

布局（自顶向下）：
    TitleLabel("AI 互动")                  _StatusDot (右上)
    SmoothScrollArea(聊天气泡历史)           气泡逐字增量
    输入行（默认收起，点切换按钮滑出）
        TextEdit (72px, 展开时显示)
        按钮行: [清空历史] [展开/收起] [发送]   ← 发送最右

切换按钮文案根据当前状态显示 "展开" / "收起"。
展开/收起状态写入 config/user/ui_state.json 跨重启保留。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import (
    QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal, Slot,
)
from PySide6.QtGui import QColor, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    AvatarWidget, BodyLabel, CardWidget, DotInfoBadge, FluentIcon as FIF,
    InfoLevel, PrimaryPushButton, PushButton, SmoothScrollArea,
    StrongBodyLabel, TextEdit, TitleLabel, ToggleButton, isDarkTheme, themeColor,
)

from desktop_sprite.ai.channel import AIText
from desktop_sprite.ui.ui_state_store import UiStateStore


logger = logging.getLogger(__name__)


# 状态点延迟阈值（毫秒）
_PING_LATENCY_OK_MS = 800.0
_PING_LATENCY_WARN_MS = 2000.0
_PING_INTERVAL_MS = 10_000
_PING_TIMEOUT_S = 5.0
_INPUT_EXPANDED_HEIGHT = 72
_INPUT_ANIM_MS = 200


# ---- 状态点（保留）----

class _StatusDot(QWidget):
    """右上角连通性指示：彩色点 + 延迟文字。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dot = DotInfoBadge(self, level=InfoLevel.SUCCESS)
        self._dot.setFixedSize(10, 10)
        self._label = BodyLabel("—", self)
        self._label.setObjectName("statusDotLabel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._dot)
        layout.addWidget(self._label)

        self._level = InfoLevel.SUCCESS
        self._pulse = QPropertyAnimation(self._dot, b"windowOpacity", self)
        self._pulse.setDuration(900)
        self._pulse.setStartValue(0.4)
        self._pulse.setEndValue(1.0)
        self._pulse.setLoopCount(-1)
        self._pulse.setEasingCurve(QEasingCurve.InOutSine)

    def level(self) -> InfoLevel:
        return self._level

    def set_state(self, *, available: bool, latency_ms: float | None) -> None:
        if not available:
            self._dot.setLevel(InfoLevel.ERROR)
            self._level = InfoLevel.ERROR
            self._label.setText("不可用")
            self._pulse.stop()
            self._dot.setWindowOpacity(1.0)
            return

        label = f"{latency_ms:.0f} ms" if latency_ms is not None else "可用"
        self._label.setText(label)

        if latency_ms is None or latency_ms < _PING_LATENCY_OK_MS:
            self._dot.setLevel(InfoLevel.SUCCESS)
            self._level = InfoLevel.SUCCESS
            self._pulse.start()
        elif latency_ms < _PING_LATENCY_WARN_MS:
            self._dot.setLevel(InfoLevel.WARNING)
            self._level = InfoLevel.WARNING
            self._pulse.start()
        else:
            self._dot.setLevel(InfoLevel.WARNING)
            self._level = InfoLevel.WARNING
            self._pulse.stop()
            self._dot.setWindowOpacity(1.0)

    def set_idle(self) -> None:
        self._dot.setLevel(InfoLevel.SUCCESS)
        self._level = InfoLevel.SUCCESS
        self._dot.setWindowOpacity(0.4)
        self._label.setText("—")
        self._pulse.stop()


# ---- 聊天气泡（保留 + 扩展）----

class ChatBubble(CardWidget):
    """聊天气泡基类。AI: 左对齐浅色；user: 右对齐主题色。"""

    def __init__(self, text: str, role: str, parent: QWidget | None = None) -> None:
        self._role = role
        self._message_text = text
        self._compute_bg_color()
        super().__init__(parent)
        self.setObjectName(f"chatBubble_{role}")
        self.setBorderRadius(14)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        body = BodyLabel(text, self)
        body.setWordWrap(True)
        body.setObjectName(f"chatBubbleBody_{role}")
        layout.addWidget(body)
        self._body = body

    def _compute_bg_color(self) -> None:
        if self._role == "ai":
            self._normal_bg = QColor(255, 255, 255, 13) if isDarkTheme() else QColor(0, 0, 0, 8)
        else:
            self._normal_bg = themeColor()

    def _normalBackgroundColor(self):
        return self._normal_bg

    def _hoverBackgroundColor(self):
        return self._normal_bg

    def text(self) -> str:
        return self._message_text

    def role(self) -> str:
        return self._role

    def append_text(self, delta: str) -> None:
        """流式增量：拼接 + adjustSize 触发布局。"""
        self._message_text += delta
        self._body.setText(self._message_text)
        self._body.adjustSize()


# ---- 主面板 ----

class AIPanelWidget(QWidget):
    """AI 互动子页（v3 FluentUI 扁平 + 流式）。"""

    def __init__(
        self,
        orchestrator,
        history_max_lines: int = 200,
        ui_state_path: Path | str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("aiPanelPage")
        self._orchestrator = orchestrator
        self._history_max_lines = history_max_lines
        self._bubbles: list[ChatBubble] = []
        self._stream_bubbles: dict[str, ChatBubble] = {}
        self._ui_state = (
            UiStateStore(Path(ui_state_path)) if ui_state_path else None
        )

        # ---- 标题行 ----
        self._title = TitleLabel("AI 互动", self)
        self._status = _StatusDot(self)
        self._status.set_idle()

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(self._title)
        title_row.addStretch(1)
        title_row.addWidget(self._status)

        # ---- 历史区（QWidget，去 CardWidget）----
        self._scroll = SmoothScrollArea(self)
        self._scroll.setObjectName("aiHistoryScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.enableTransparentBackground()
        # 防止 viewport 默认填充白色背景
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll_inner = QWidget(self._scroll)
        self._scroll_inner.setObjectName("chatBubblesInner")
        # 内层 widget 透明背景
        self._scroll_inner.setAttribute(Qt.WA_StyledBackground, False)
        self._scroll_inner.setStyleSheet("background: transparent;")
        self._scroll_layout = QVBoxLayout(self._scroll_inner)
        self._scroll_layout.setContentsMargins(4, 4, 4, 4)
        self._scroll_layout.setSpacing(8)
        self._scroll_layout.addStretch(1)
        self._scroll.setWidget(self._scroll_inner)

        # ---- 输入区（始终可见；只 TextEdit 折叠，buttons 始终在）----
        self._input_area = QWidget(self)
        self._input_area.setObjectName("aiInputArea")
        # 不再 setMaximumHeight(0)；input area 本身始终存在
        input_layout = QVBoxLayout(self._input_area)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        self._input_edit = TextEdit(self._input_area)
        self._input_edit.setObjectName("aiInputEdit")
        self._input_edit.setPlaceholderText("说点什么…")
        # 用 maxHeight 控制折叠；min 不锁，便于动画 0→72
        self._input_edit.setMaximumHeight(72)
        self._input_edit.setMinimumHeight(72)
        # 初始可见性由 _apply_input_expanded 设置
        input_layout.addWidget(self._input_edit)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch(1)
        self._clear_btn = PushButton("清空历史", self._input_area)
        self._clear_btn.setIcon(FIF.DELETE)
        self._clear_btn.clicked.connect(self.clear_history)
        self._toggle_btn = ToggleButton("展开", self._input_area)
        self._toggle_btn.setIcon(FIF.UP)
        self._toggle_btn.toggled.connect(self._on_toggle_changed)
        self._send_btn = PrimaryPushButton("发送", self._input_area)
        self._send_btn.setIcon(FIF.SEND)
        self._send_btn.clicked.connect(self._on_send_clicked)
        button_row.addWidget(self._clear_btn)
        button_row.addWidget(self._toggle_btn)
        button_row.addWidget(self._send_btn)
        input_layout.addLayout(button_row)

        # ---- 页面布局 ----
        page = QVBoxLayout(self)
        page.setContentsMargins(48, 80, 48, 32)
        page.setSpacing(16)
        page.addLayout(title_row)
        page.addWidget(self._scroll, 1)
        page.addWidget(self._input_area)

        # ---- 初始状态 ----
        self._input_expanded = False
        self._apply_input_expanded(self._load_input_expanded(), animate=False)

        # ---- Ping 调度 ----
        self._ping_timer = QTimer(self)
        self._ping_timer.setInterval(_PING_INTERVAL_MS)
        self._ping_timer.timeout.connect(self._run_ping)
        self._ping_busy = False
        if self._orchestrator is not None:
            self._ping_timer.start()

    # ---- UI 状态持久化 ----

    def _load_input_expanded(self) -> bool:
        if self._ui_state is None:
            return False
        state = self._ui_state.read()
        return bool(state.get("ai_panel", {}).get("input_expanded", False))

    def _save_input_expanded(self) -> None:
        if self._ui_state is None:
            return
        def mutate(s: dict) -> None:
            s.setdefault("ai_panel", {})["input_expanded"] = self._input_expanded
        self._ui_state.update(mutate)

    def _apply_input_expanded(self, expanded: bool, *, animate: bool) -> None:
        self._input_expanded = expanded
        self._toggle_btn.setChecked(expanded)
        self._toggle_btn.setText("收起" if expanded else "展开")
        self._toggle_btn.setIcon(FIF.DOWN if expanded else FIF.UP)
        if animate:
            # 动画只动 input_edit 的 maximumHeight；input_area 始终存在
            if expanded:
                self._input_edit.setVisible(True)
                self._animate_input_edit(_INPUT_EXPANDED_HEIGHT)
            else:
                self._animate_input_edit(0)
        else:
            self._input_edit.setMaximumHeight(
                _INPUT_EXPANDED_HEIGHT if expanded else 0
            )
            self._input_edit.setVisible(expanded)

    def _on_toggle_changed(self, checked: bool) -> None:
        self._apply_input_expanded(checked, animate=True)
        self._save_input_expanded()

    def _animate_input_edit(self, target: int) -> None:
        """动画 input_edit 的 maximumHeight；target=0 时收起完成后隐藏。"""
        if target > 0 and not self._input_edit.isVisible():
            self._input_edit.setVisible(True)
        ani = QPropertyAnimation(self._input_edit, b"maximumHeight", self)
        ani.setDuration(_INPUT_ANIM_MS)
        ani.setStartValue(self._input_edit.maximumHeight())
        ani.setEndValue(target)
        ani.setEasingCurve(QEasingCurve.OutCubic)
        if target == 0:
            ani.finished.connect(lambda: self._input_edit.setVisible(False))
        ani.start()

    # ---- 公开 API（ChatPanelChannel 与测试用）----

    def append_history(self, message: AIText) -> None:
        role = "user" if message.source == "user" else "ai"
        self._add_bubble(message.text, role=role)

    def append_stream_start(self, stream_id: str, use_case_id: str) -> None:
        bubble = self._add_bubble("", role="ai")
        self._stream_bubbles[stream_id] = bubble

    def append_stream_delta(self, stream_id: str, delta: str, use_case_id: str) -> None:
        bubble = self._stream_bubbles.get(stream_id)
        if bubble is None:
            return
        bubble.append_text(delta)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def append_stream_end(
        self, stream_id: str, full_text: str, source: str, use_case_id: str,
    ) -> None:
        bubble = self._stream_bubbles.pop(stream_id, None)
        if bubble is None:
            return
        # 如果 source 是 fallback 之类，可以加视觉标记（v3 不做）

    def clear_history(self) -> None:
        while self._scroll_layout.count() > 1:
            item = self._scroll_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._bubbles.clear()
        self._stream_bubbles.clear()

    def messages(self) -> list[dict]:
        return [{"role": b.role(), "text": b.text()} for b in self._bubbles]

    def bubble_count(self) -> int:
        return len(self._bubbles)

    def status_text(self) -> str:
        return self._status._label.text()

    def status_available(self) -> bool:
        return self._status.level() != InfoLevel.ERROR

    def input_visible(self) -> bool:
        return self._input_expanded

    def trigger_ping_for_test(self) -> None:
        self._run_ping_sync()

    # ---- 私有 ----

    def _add_bubble(self, text: str, *, role: str) -> ChatBubble:
        bubble = ChatBubble(text, role=role, parent=self._scroll_inner)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        if role == "ai":
            avatar = AvatarWidget(self._scroll_inner)
            avatar.setText("AI")
            avatar.setRadius(16)  # 32px 直径
            row.addWidget(avatar)
            row.addWidget(bubble, 0)
            row.addStretch(1)
        else:
            row.addStretch(1)
            row.addWidget(bubble, 0)
        bubble.setMaximumWidth(int(self.width() * 0.75) if self.width() > 0 else 600)
        self._scroll_layout.insertLayout(self._scroll_layout.count() - 1, row)
        self._bubbles.append(bubble)
        # history_max_lines trim
        self._trim_history()
        QTimer.singleShot(0, self._scroll_to_bottom)
        return bubble

    def _trim_history(self) -> None:
        """保留最后 history_max_lines 个气泡（仅 trim 普通气泡，不动流中气泡）。"""
        if self._history_max_lines <= 0:
            return
        while len(self._bubbles) - len(self._stream_bubbles) > self._history_max_lines:
            bubble = self._bubbles[0]
            if bubble in self._stream_bubbles.values():
                break  # 保护流中气泡
            self._bubbles.pop(0)
            # 找 row layout 删掉（含 avatar）
            for i in range(self._scroll_layout.count()):
                item = self._scroll_layout.itemAt(i)
                if item.layout() is None:
                    continue
                if item.layout().count() > 0:
                    last_widget = item.layout().itemAt(item.layout().count() - 1).widget()
                    if last_widget is bubble:
                        # 删整行
                        while item.layout().count():
                            child = item.layout().takeAt(0)
                            w = child.widget()
                            if w is not None:
                                w.deleteLater()
                        self._scroll_layout.removeItem(item)
                        break

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_send_clicked(self) -> None:
        text = self._input_edit.toPlainText().strip()
        if not text:
            return
        self._add_bubble(text, role="user")
        if self._orchestrator is not None:
            self._orchestrator.trigger_test(user_hint=text)
        self._input_edit.clear()
        self._apply_input_expanded(False, animate=True)
        self._save_input_expanded()

    def _run_ping(self) -> None:
        if self._ping_busy or self._orchestrator is None:
            return
        self._ping_busy = True
        self._orchestrator.ping_async(self._on_ping_done)

    def _run_ping_sync(self) -> None:
        if self._orchestrator is None:
            return
        provider = self._orchestrator._provider
        if provider is None:
            return
        try:
            ms = provider.ping(timeout=_PING_TIMEOUT_S)
            self._on_ping_done(ms, None)
        except Exception as e:
            self._on_ping_done(None, e)

    @Slot(float, object)
    def _on_ping_done(self, latency_ms, error) -> None:
        self._ping_busy = False
        if error is not None:
            self._status.set_state(available=False, latency_ms=None)
            self._toggle_btn.setEnabled(False)
            self._input_area.setEnabled(False)
            return
        self._status.set_state(available=True, latency_ms=latency_ms)
        if self._orchestrator is not None:
            self._toggle_btn.setEnabled(True)
            self._input_area.setEnabled(True)
