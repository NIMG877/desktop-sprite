"""AI 互动面板（v2 聊天气泡 UI）。

布局（自顶向下）：
    TitleLabel("AI 互动")                       状态点(右上角，可点击刷新)
    SmoothScrollArea(聊天气泡历史)              [ + ] 圆形按钮
    输入卡片（默认收起，点 + 滑出）

状态点（_StatusDot）：
    不可用 → 红点常量（InfoLevel.ERROR）
    可用 & 延迟 < 800ms  → 绿点慢速脉冲 + "12 ms"
    可用 & 800~2000ms     → 黄点慢速脉冲 + "1234 ms"
    可用 & 延迟 ≥ 2000ms  → 黄点常量（不脉冲）+ "2345 ms"

圆形 + 按钮（_FabButton）：
    继承 PrimaryToolButton，paintEvent 重画圆形 + 大图标。
    展开时切到 FIF.CLOSE 图标。
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from PySide6.QtCore import (
    QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal, Slot,
)
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CardWidget, DotInfoBadge, FluentIcon as FIF,
    InfoLevel, PrimaryPushButton, PrimaryToolButton, PushButton,
    SmoothScrollArea, StrongBodyLabel, SubtitleLabel, TextEdit,
    TitleLabel, isDarkTheme, themeColor,
)

from desktop_sprite.ai.channel import AIText


# 状态点延迟阈值（毫秒）
_PING_LATENCY_OK_MS = 800.0
_PING_LATENCY_WARN_MS = 2000.0
_PING_INTERVAL_MS = 10_000
_PING_TIMEOUT_S = 5.0
_INPUT_EXPANDED_HEIGHT = 160
_INPUT_ANIM_MS = 200


# ---- 状态点 ----

class _StatusDot(QWidget):
    """右上角连通性指示：彩色点 + 延迟文字。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dot = DotInfoBadge(self, level=InfoLevel.SUCCESS)
        self._dot.setFixedSize(10, 10)
        self._label = CaptionLabel("—", self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._dot)
        layout.addWidget(self._label)

        # 当前点级别——DotInfoBadge 没有 level() getter，我们自己存一份
        self._level = InfoLevel.SUCCESS

        # 脉冲动画作用于 _dot 自己的 opacity（windowOpacity 会影响整个 widget）
        self._pulse = QPropertyAnimation(self._dot, b"windowOpacity", self)
        self._pulse.setDuration(900)
        self._pulse.setStartValue(0.4)
        self._pulse.setEndValue(1.0)
        self._pulse.setLoopCount(-1)
        self._pulse.setEasingCurve(QEasingCurve.InOutSine)

    def level(self) -> InfoLevel:
        return self._level

    def set_state(self, *, available: bool, latency_ms: float | None) -> None:
        """根据 ping 结果更新点颜色 + 文字 + 脉冲状态。"""
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
        """尚未 ping 过的初始态：灰色点 + '—'。"""
        self._dot.setLevel(InfoLevel.SUCCESS)
        self._level = InfoLevel.SUCCESS
        self._dot.setWindowOpacity(0.4)
        self._label.setText("—")
        self._pulse.stop()


# ---- 圆形 FAB ----

class _FabButton(QWidget):
    """圆形 + / × 按钮——纯 QWidget，paintEvent 自画圆 + 图标。

    用 QWidget 而非 PrimaryToolButton 是因为 qfluentwidgets 的 @overload
    在子类继承时会让 super().__init__ 派发到 self.__init__，陷入递归。
    """

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(56, 56)
        self._icon = FIF.ADD.icon()
        self._icon_size = QSize(28, 28)
        self._expanded = False
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, False)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._icon = (FIF.CLOSE if expanded else FIF.ADD).icon()
        self.update()

    def click(self) -> None:
        """测试 / 编程触发点击。"""
        if self.isEnabled():
            self.clicked.emit()

    def mousePressEvent(self, event):  # noqa: D401
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: D401
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        if self.isEnabled():
            bg = themeColor()
            icon_color = QColor("white")
        else:
            bg = QColor(150, 150, 150) if isDarkTheme() else QColor(200, 200, 200)
            icon_color = QColor(180, 180, 180)
        painter.setBrush(bg)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect)
        if not self._icon.isNull():
            # 用 pixmap + 颜色蒙版画图标，确保在彩色背景上可见
            from PySide6.QtGui import QIcon
            pixmap = self._icon.pixmap(self._icon_size)
            # 单色蒙版：把 pixmap 灰度作为 alpha，跟 icon_color 合成
            from PySide6.QtGui import QImage, QPainter as _QP
            mask = QImage(pixmap.size(), QImage.Format_ARGB32)
            mask.fill(Qt.transparent)
            mp = _QP(mask)
            mp.setCompositionMode(_QP.CompositionMode_Source)
            mp.drawPixmap(0, 0, pixmap)
            mp.end()
            # 在 mask 上把不透明区域染成 icon_color
            for y in range(mask.height()):
                for x in range(mask.width()):
                    a = mask.pixelColor(x, y).alpha()
                    if a > 0:
                        mask.setPixelColor(x, y, QColor(icon_color.red(), icon_color.green(), icon_color.blue(), a))
            x = (rect.width() - mask.width()) // 2
            y = (rect.height() - mask.height()) // 2
            painter.drawImage(x, y, mask)
        painter.end()


# ---- 聊天气泡 ----

class ChatBubble(CardWidget):
    """聊天气泡基类。AI: 左对齐浅色；user: 右对齐主题色。"""

    def __init__(self, text: str, role: str, parent: QWidget | None = None) -> None:
        # 必须在 super().__init__ 之前计算 _normal_bg——qfluentwidgets 的
        # BackgroundColorObject 会在父类构造里调 _normalBackgroundColor()
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

    def _normalBackgroundColor(self):  # type: ignore[override]
        return self._normal_bg

    def _hoverBackgroundColor(self):  # type: ignore[override]
        return self._normal_bg

    def text(self) -> str:
        return self._message_text

    def role(self) -> str:
        return self._role


# ---- 主面板 ----

class AIPanelWidget(QWidget):
    """AI 互动子页（v2 FluentUI 聊天气泡）。"""

    def __init__(
        self,
        orchestrator,  # 实际类型：AIOrchestrator；duck type 避免循环 import
        history_max_lines: int = 200,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("aiPanelPage")
        self._orchestrator = orchestrator
        self._history_max_lines = history_max_lines
        self._bubbles: list[ChatBubble] = []

        # ---- 顶部：标题 + 状态点 ----
        self._title = TitleLabel("AI 互动", self)
        self._status = _StatusDot(self)
        self._status.set_idle()

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(self._title)
        title_row.addStretch(1)
        title_row.addWidget(self._status)

        # ---- 历史卡片（含 SmoothScrollArea）----
        self._history_card = CardWidget(self)
        self._history_card.setObjectName("aiHistoryCard")
        history_layout = QVBoxLayout(self._history_card)
        history_layout.setContentsMargins(12, 12, 12, 12)
        history_layout.setSpacing(0)

        self._scroll = SmoothScrollArea(self._history_card)
        self._scroll.setWidgetResizable(True)
        self._scroll.enableTransparentBackground()
        self._scroll_inner = QWidget(self._scroll)
        self._scroll_inner.setObjectName("chatBubblesInner")
        self._scroll_layout = QVBoxLayout(self._scroll_inner)
        self._scroll_layout.setContentsMargins(4, 4, 4, 4)
        self._scroll_layout.setSpacing(8)
        # 末尾加 stretch，气泡贴顶
        self._scroll_layout.addStretch(1)
        self._scroll.setWidget(self._scroll_inner)
        history_layout.addWidget(self._scroll, 1)

        # ---- + 按钮（右下浮动）----
        self._fab = _FabButton(self)
        self._fab.setObjectName("aiFab")
        self._fab.clicked.connect(self._toggle_input)

        # ---- 输入卡片（默认收起）----
        self._input_card = CardWidget(self)
        self._input_card.setObjectName("aiInputCard")
        self._input_card.setMaximumHeight(0)
        self._input_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        input_layout = QVBoxLayout(self._input_card)
        input_layout.setContentsMargins(16, 12, 16, 12)
        input_layout.setSpacing(8)
        input_layout.addWidget(SubtitleLabel("发送消息", self._input_card))

        self._input_edit = TextEdit(self._input_card)
        self._input_edit.setObjectName("aiInputEdit")
        self._input_edit.setPlaceholderText("说点什么…")
        self._input_edit.setFixedHeight(72)
        input_layout.addWidget(self._input_edit)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch(1)
        self._clear_btn = PushButton("清空历史", self._input_card)
        self._clear_btn.setIcon(FIF.DELETE)
        self._clear_btn.clicked.connect(self.clear_history)
        self._send_btn = PrimaryPushButton("发送", self._input_card)
        self._send_btn.setIcon(FIF.SEND)
        self._send_btn.clicked.connect(self._on_send_clicked)
        button_row.addWidget(self._clear_btn)
        button_row.addWidget(self._send_btn)
        input_layout.addLayout(button_row)

        # ---- 页面布局 ----
        page = QVBoxLayout(self)
        page.setContentsMargins(48, 80, 48, 32)
        page.setSpacing(16)
        page.addLayout(title_row)
        page.addWidget(self._history_card, 1)
        page.addWidget(self._input_card)

        # FAB 浮在历史卡片右下：用绝对定位（无 layout）
        # 注意：layout 系统会把 FAB 算进 children，所以这里用手动 geometry
        self._fab.setParent(self)
        self._fab.show()
        self._fab.raise_()

        # ---- Ping 调度 ----
        self._ping_timer = QTimer(self)
        self._ping_timer.setInterval(_PING_INTERVAL_MS)
        self._ping_timer.timeout.connect(self._run_ping)
        self._ping_busy = False
        if self._orchestrator is not None:
            self._ping_timer.start()

    # ---- 几何 / 浮动 FAB 位置 ----

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: D401
        super().resizeEvent(event)
        self._reposition_fab()

    def _reposition_fab(self) -> None:
        # FAB 浮在历史卡片右下角内嵌 16px
        if not hasattr(self, "_history_card") or not hasattr(self, "_fab"):
            return
        history_geo = self._history_card.geometry()
        margin = 16
        fab_size = self._fab.size()
        x = history_geo.right() - fab_size.width() - margin
        y = history_geo.bottom() - fab_size.height() - margin
        self._fab.move(x, y)
        self._fab.raise_()

    def showEvent(self, event):  # noqa: D401
        super().showEvent(event)
        # 几何稳定后定位 FAB
        QTimer.singleShot(0, self._reposition_fab)

    # ---- 公开 API（ChatPanelChannel 与测试用）----

    def append_history(self, message: AIText) -> None:
        role = "user" if message.source == "user" else "ai"
        self._add_bubble(message.text, role=role)

    def clear_history(self) -> None:
        # 移除除末尾 stretch 外的所有 bubble
        while self._scroll_layout.count() > 1:
            item = self._scroll_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._bubbles.clear()

    def messages(self) -> list[dict]:
        """测试用：返回所有气泡的 (role, text) 列表。"""
        return [{"role": b.role(), "text": b.text()} for b in self._bubbles]

    def bubble_count(self) -> int:
        return len(self._bubbles)

    def status_text(self) -> str:
        return self._status._label.text()

    def status_available(self) -> bool:
        """测试用：True 表示最近一次 ping 成功（status 点不是 ERROR）。"""
        return self._status.level() != InfoLevel.ERROR

    def input_visible(self) -> bool:
        """测试用：输入卡片是否展开。"""
        return self._input_card.maximumHeight() > 0

    def trigger_ping_for_test(self) -> None:
        """测试用：同步触发一次 ping（不走 QThreadPool）。"""
        self._run_ping_sync()

    # ---- 私有 ----

    def _add_bubble(self, text: str, *, role: str) -> None:
        bubble = ChatBubble(text, role=role, parent=self._scroll_inner)
        # 用 QHBoxLayout 容器控制左右对齐
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        if role == "user":
            row.addStretch(1)
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch(1)
        # 限制气泡最大宽度为页面 75%
        bubble.setMaximumWidth(int(self.width() * 0.75) if self.width() > 0 else 600)
        # 插入到末尾 stretch 之前
        self._scroll_layout.insertLayout(self._scroll_layout.count() - 1, row)
        self._bubbles.append(bubble)
        # 自动滚到底
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _toggle_input(self) -> None:
        if self._input_card.maximumHeight() == 0:
            target = _INPUT_EXPANDED_HEIGHT
        else:
            target = 0
        self._animate_input(target)

    def _animate_input(self, target: int) -> None:
        ani = QPropertyAnimation(self._input_card, b"maximumHeight", self)
        ani.setDuration(_INPUT_ANIM_MS)
        ani.setStartValue(self._input_card.maximumHeight())
        ani.setEndValue(target)
        ani.setEasingCurve(QEasingCurve.OutCubic)
        ani.start()
        # FAB 图标切换
        self._fab.set_expanded(target > 0)

    def _on_send_clicked(self) -> None:
        text = self._input_edit.toPlainText().strip()
        if not text:
            return
        # 1) 先把用户消息画到历史
        self._add_bubble(text, role="user")
        # 2) 触发 use case，把 text 作为 user_hint
        if self._orchestrator is not None:
            self._orchestrator.trigger_test(user_hint=text)
        # 3) 清空输入框并收起
        self._input_edit.clear()
        self._animate_input(0)

    def _run_ping(self) -> None:
        if self._ping_busy or self._orchestrator is None:
            return
        self._ping_busy = True
        self._orchestrator.ping_async(self._on_ping_done)

    def _run_ping_sync(self) -> None:
        """测试用：直接在主线程调 ping（不走线程池）。"""
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
            # 失败时禁用 FAB
            self._fab.setEnabled(False)
            self._input_card.setEnabled(False)
            return
        self._status.set_state(available=True, latency_ms=latency_ms)
        # 可用时启用 FAB（若 orchestrator 不为 None）
        if self._orchestrator is not None:
            self._fab.setEnabled(True)
            self._input_card.setEnabled(True)
