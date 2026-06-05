# AI 互动面板 v4 — slim 栏 + 仅图标 toggle 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 v3 的"toggle 按钮在输入区按钮行 + 3 个按钮始终可见"改为 v4 的"slim 栏（整页底部）+ 仅图标 ToolButton + 收起时整个输入抽屉整段消失"，让"AI 互动"页面从"聊天页"语义真正变成"观察页"。

**Architecture:** 在 `AIPanelWidget` 内新增一个 `_slim_bar`（QWidget + 1px QFrame HLine 顶边线 + 右对齐 ToolButton），把 `_toggle_btn` 从输入区按钮行**完全迁出**。动画对象从 `_input_edit.maximumHeight`（只动内层 TextEdit）升级为 `_input_area.maximumHeight`（动整个抽屉），target=0 时动画结束后 `setVisible(False)`。ping 失败时 `_toggle_btn` 保持可用、`_input_area.setEnabled(False)` 禁用抽屉内控件。

**Tech Stack:** PySide6 + qfluentwidgets 1.11.2（`ToolButton` 替代 `ToggleButton`）。

**Spec:** [docs/superpowers/specs/2026-06-05-ai-panel-redesign-design.md](../specs/2026-06-05-ai-panel-redesign-design.md)（v3 已实施 + v4 微调）

**Base commit:** `cf94c23`（design doc 提交后）

---

## File Structure（v4 增量）

| 文件 | 改动 | v4 净行数 |
|---|---|---|
| `desktop_sprite/ui/ai_panel.py` | 新增 `_slim_bar` 字段 + 构造；迁出 toggle + 改 ToolButton；动画对象升级；ping 失败行为调整 | +35 / -25 |
| `tests/test_ai_panel_widget.py` | 改造 5 个 v3 测试 + 新增 6 个 v4 测试 | +20 / -10 |

整个 v4 集中在 2 个文件，**没有新文件**。

---

## Task 1: slim 栏 + ToolButton 切换按钮（v4 骨架）

**Files:**
- Modify: `desktop_sprite/ui/ai_panel.py:1-50`（imports + 常量）
- Modify: `desktop_sprite/ui/ai_panel.py:208-260`（构造 slim_bar、迁出 toggle）
- Modify: `tests/test_ai_panel_widget.py:1-15`（imports）
- Test: `tests/test_ai_panel_widget.py`（新增 4 个测试）

- [ ] **Step 1: 写失败的测试**——在 `tests/test_ai_panel_widget.py` 顶部 imports 加 `from qfluentwidgets import ToolButton, ToggleButton`（和现有的 `AvatarWidget, DotInfoBadge, InfoLevel, SmoothScrollArea, TitleLabel` 同一行扩展），并在文件末尾追加：

```python
# ---- v4: slim 栏 + ToolButton toggle ----

def test_slim_bar_exists_and_always_visible(panel, qtbot):
    """v4: 整页底部新增 _slim_bar，收起/展开两种状态下都可见。"""
    p, _, _ = panel
    assert hasattr(p, "_slim_bar"), "AIPanelWidget 应有 _slim_bar 字段"
    assert p._slim_bar.isVisible() is True
    # 展开后 slim_bar 仍然可见
    p._toggle_btn.click()
    qtbot.waitUntil(lambda: p._input_expanded, timeout=2000)
    assert p._slim_bar.isVisible() is True


def test_toggle_button_is_tool_button(panel):
    """v4: toggle 改为 ToolButton，不再是 ToggleButton。"""
    p, _, _ = panel
    assert isinstance(p._toggle_btn, ToolButton)
    assert not isinstance(p._toggle_btn, ToggleButton)


def test_toggle_button_has_no_text(panel):
    """v4: toggle 仅图标，文字为空。"""
    p, _, _ = panel
    assert p._toggle_btn.text() == ""


def test_toggle_button_has_tooltip(panel):
    """v4: 鼠标悬停 tooltip 补回可发现性。"""
    p, _, _ = panel
    assert p._toggle_btn.toolTip() != ""
```

- [ ] **Step 2: 跑测试看失败**

```bash
cd d:/PythonProjects/DesktopSprite
.venv/Scripts/python.exe -m pytest tests/test_ai_panel_widget.py::test_slim_bar_exists_and_always_visible tests/test_ai_panel_widget.py::test_toggle_button_is_tool_button tests/test_ai_panel_widget.py::test_toggle_button_has_no_text tests/test_ai_panel_widget.py::test_toggle_button_has_tooltip -v --basetemp=./.pytest_basetmp
```

预期：4 个全部 FAIL（`AttributeError: 'AIPanelWidget' object has no attribute '_slim_bar'`）

- [ ] **Step 3: 最小实现**——改 `desktop_sprite/ui/ai_panel.py`：

1) imports 改（第 26-30 行附近）：

```python
from qfluentwidgets import (
    AvatarWidget, BodyLabel, CardWidget, DotInfoBadge, FluentIcon as FIF,
    InfoLevel, PrimaryPushButton, PushButton, SmoothScrollArea,
    StrongBodyLabel, TextEdit, TitleLabel, ToggleButton, ToolButton, isDarkTheme,
    themeColor,
)
```

2) 模块级常量加一行（第 45 行附近）：

```python
_INPUT_EXPANDED_HEIGHT = 72  # v3 保留：TextEdit 内层高度（v4 仍用于 _input_edit）
_INPUT_DRAWER_HEIGHT = 120   # v4：整个输入抽屉展开时高度（TextEdit 72 + spacing 8 + 按钮行 32 + 8 余量）
_INPUT_ANIM_MS = 200
_SLIM_BAR_HEIGHT = 36        # v4：slim 栏固定高度
```

3) 删 `ToggleButton` 的 import（v4 改用 `ToolButton`，但保留 `ToggleButton` 不删，因为别的代码可能用——这里确认只有 AIPanelWidget 用，可删）。**先确认** `ToggleButton` 在仓库别处的使用：

```bash
cd d:/PythonProjects/DesktopSprite
grep -rn "ToggleButton" --include="*.py" .
```

如果只在 `ai_panel.py` 里 import，则可删 import 行里 `ToggleButton,`。

4) 删掉输入区按钮行（第 225-240 行附近）里的 `_toggle_btn` 构造 + `addWidget`：

```python
button_row = QHBoxLayout()
button_row.setSpacing(8)
button_row.addStretch(1)
self._clear_btn = PushButton("清空历史", self._input_area)
self._clear_btn.setIcon(FIF.DELETE)
self._clear_btn.clicked.connect(self.clear_history)
self._send_btn = PrimaryPushButton("发送", self._input_area)
self._send_btn.setIcon(FIF.SEND)
self._send_btn.clicked.connect(self._on_send_clicked)
button_row.addWidget(self._clear_btn)
button_row.addWidget(self._send_btn)
input_layout.addLayout(button_row)
```

5) **关键**：把 `_apply_input_expanded` 里的 `setText` 删掉（v4 toggle 无文字，只剩 setChecked + setIcon）。完整方法体改为：

```python
def _apply_input_expanded(self, expanded: bool, *, animate: bool) -> None:
    self._input_expanded = expanded
    self._toggle_btn.setChecked(expanded)
    # v4: 不再 setText（无文字）；setIcon 跟状态反转
    self._toggle_btn.setIcon(FIF.DOWN if expanded else FIF.UP)
    if animate:
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
```

> **注意**：Task 1 这一步只删 `setText` 行；动画逻辑（animate TextEdit 还是 animate _input_area）留给 Task 2。

6) 在 page layout（第 242-248 行）后追加 slim 栏构造，并把它加到 page layout：

```python
# ---- slim 栏（v4：整页底部，1px 顶边线 + 右对齐 ToolButton）----
self._slim_bar = QWidget(self)
self._slim_bar.setObjectName("aiSlimBar")
self._slim_bar.setFixedHeight(_SLIM_BAR_HEIGHT)

# 1px 顶部分隔线
slim_layout = QVBoxLayout(self._slim_bar)
slim_layout.setContentsMargins(0, 0, 0, 0)
slim_layout.setSpacing(0)
divider = QFrame(self._slim_bar)
divider.setFrameShape(QFrame.HLine)
divider.setFrameShadow(QFrame.Plain)
# 半透明主题色（深色用白 40，浅色用黑 80）
divider.setStyleSheet(
    "color: rgba(255, 255, 255, 40);" if isDarkTheme()
    else "color: rgba(0, 0, 0, 80);"
)
divider.setFixedHeight(1)
slim_layout.addWidget(divider)

slim_row = QHBoxLayout()
slim_row.setContentsMargins(0, 4, 16, 4)  # 右边 16px 留白
slim_row.setSpacing(0)
slim_row.addStretch(1)
self._toggle_btn = ToolButton(self._slim_bar)
self._toggle_btn.setIcon(FIF.UP)
self._toggle_btn.setToolTip("展开输入")
self._toggle_btn.toggled.connect(self._on_toggle_changed)
slim_row.addWidget(self._toggle_btn)
slim_layout.addLayout(slim_row)
```

7) imports 加 `QFrame`（第 22-25 行附近）：

```python
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QWidget,
)
```

8) 把 slim_bar 加到 page layout（替换 `page.addWidget(self._input_area)` 那一段，最后加一行）：

```python
page = QVBoxLayout(self)
page.setContentsMargins(48, 80, 48, 32)
page.setSpacing(16)
page.addLayout(title_row)
page.addWidget(self._scroll, 1)
page.addWidget(self._input_area)
page.addWidget(self._slim_bar)  # v4：slim 栏永远在底部
```

- [ ] **Step 4: 跑新测试看通过**

```bash
cd d:/PythonProjects/DesktopSprite
.venv/Scripts/python.exe -m pytest tests/test_ai_panel_widget.py::test_slim_bar_exists_and_always_visible tests/test_ai_panel_widget.py::test_toggle_button_is_tool_button tests/test_ai_panel_widget.py::test_toggle_button_has_no_text tests/test_ai_panel_widget.py::test_toggle_button_has_tooltip -v --basetemp=./.pytest_basetmp
```

预期：4 个全部 PASS

- [ ] **Step 5: 跑全套确认 v3 测试是否仍能通过（预期会有部分 FAIL）**

```bash
cd d:/PythonProjects/DesktopSprite
.venv/Scripts/python.exe -m pytest tests/test_ai_panel_widget.py -v --basetemp=./.pytest_basetmp
```

预期：v3 中 `test_toggle_btn_click_expands_input` / `test_toggle_btn_click_again_collapses_input` / `test_toggle_btn_disabled_when_ping_fails` / `test_input_starts_collapsed` / `test_buttons_visible_even_when_input_collapsed` 5 个会 FAIL（因为 v3 断言基于旧结构，将在后续 Task 修复）

- [ ] **Step 6: 提交**

```bash
cd d:/PythonProjects/DesktopSprite
git add desktop_sprite/ui/ai_panel.py tests/test_ai_panel_widget.py
git commit -m "feat(ui): v4 slim 栏 + ToolButton toggle 骨架

- 整页底部新增 _slim_bar（fixed 36px + 1px QFrame HLine 顶边线）
- _toggle_btn 改为 ToolButton 仅图标 + tooltip
- 输入区按钮行不再含 toggle（迁出到 slim_bar）
- 4 个新测试通过；v3 部分旧测试将随 Task 2/3/4 修复"
```

---

## Task 2: 动画对象升级为整个 `_input_area`

**Files:**
- Modify: `desktop_sprite/ui/ai_panel.py:277-310`（`_apply_input_expanded` / `_animate_input_edit`）
- Modify: `tests/test_ai_panel_widget.py:70-78` / `119-148`（v3 测试改用 `_input_area`）

- [ ] **Step 1: 写失败的测试**——在 `tests/test_ai_panel_widget.py` 末尾追加：

```python
# ---- v4: 整抽屉动画 ----

def test_input_area_starts_hidden_with_zero_maximum_height(panel):
    """v4: 初始收起时 _input_area 高度=0 且隐藏。"""
    p, _, _ = panel
    assert p._input_area.isVisible() is False
    assert p._input_area.maximumHeight() == 0


def test_input_area_visible_with_full_height_when_expanded(panel, qtbot):
    """v4: 展开后 _input_area 高度=_INPUT_DRAWER_HEIGHT 且可见。"""
    p, _, _ = panel
    p._toggle_btn.click()
    qtbot.waitUntil(
        lambda: p._input_area.isVisible() and p._input_area.maximumHeight() == _INPUT_DRAWER_HEIGHT,
        timeout=2000,
    )


def test_input_area_hidden_after_collapse_animation(panel, qtbot):
    """v4: 收起动画结束后 _input_area.setVisible(False)。"""
    p, _, _ = panel
    # 先展开
    p._toggle_btn.click()
    qtbot.waitUntil(
        lambda: p._input_area.isVisible() and p._input_area.maximumHeight() == _INPUT_DRAWER_HEIGHT,
        timeout=2000,
    )
    # 再收起
    p._toggle_btn.click()
    qtbot.waitUntil(
        lambda: p._input_area.maximumHeight() == 0 and not p._input_area.isVisible(),
        timeout=2000,
    )
```

并 import（顶部）：

```python
from desktop_sprite.ui.ai_panel import (
    AIPanelWidget, ChatBubble, _INPUT_DRAWER_HEIGHT, _INPUT_EXPANDED_HEIGHT, _StatusDot,
)
```

- [ ] **Step 2: 跑测试看失败**

```bash
cd d:/PythonProjects/DesktopSprite
.venv/Scripts/python.exe -m pytest tests/test_ai_panel_widget.py::test_input_area_starts_hidden_with_zero_maximum_height tests/test_ai_panel_widget.py::test_input_area_visible_with_full_height_when_expanded tests/test_ai_panel_widget.py::test_input_area_hidden_after_collapse_animation -v --basetemp=./.pytest_basetmp
```

预期：3 个全部 FAIL（`_INPUT_DRAWER_HEIGHT` 没定义 / `_input_area.isVisible()` 初始为 True / 旧动画不会改 `_input_area` 高度）

- [ ] **Step 3: 最小实现**——改 `desktop_sprite/ui/ai_panel.py` 的 `_apply_input_expanded` 和动画方法（替换第 277-310 行）：

```python
def _apply_input_expanded(self, expanded: bool, *, animate: bool) -> None:
    self._input_expanded = expanded
    self._toggle_btn.setChecked(expanded)
    # v4: 图标只随状态反转；tooltip 也跟状态
    if expanded:
        self._toggle_btn.setIcon(FIF.DOWN)
        self._toggle_btn.setToolTip("收起输入")
    else:
        self._toggle_btn.setIcon(FIF.UP)
        self._toggle_btn.setToolTip("展开输入")
    if animate:
        # v4: 动画对象是 _input_area.maximumHeight（整抽屉），不再只动 TextEdit
        if expanded and not self._input_area.isVisible():
            self._input_area.setVisible(True)
        self._animate_input_area(_INPUT_DRAWER_HEIGHT if expanded else 0)
    else:
        self._input_area.setMaximumHeight(
            _INPUT_DRAWER_HEIGHT if expanded else 0
        )
        self._input_area.setVisible(expanded)


def _animate_input_area(self, target: int) -> None:
    """v4: 动画 _input_area.maximumHeight；target=0 时收起完成后隐藏。"""
    if target > 0 and not self._input_area.isVisible():
        self._input_area.setVisible(True)
    ani = QPropertyAnimation(self._input_area, b"maximumHeight", self)
    ani.setDuration(_INPUT_ANIM_MS)
    ani.setStartValue(self._input_area.maximumHeight())
    ani.setEndValue(target)
    ani.setEasingCurve(QEasingCurve.OutCubic)
    if target == 0:
        ani.finished.connect(lambda: self._input_area.setVisible(False))
    ani.start()
```

并删掉第 219-221 行附近的旧 TextEdit 高度限制 + 旧 _animate_input_edit 方法（替换为外层抽屉动画）：

```python
# 旧（删除）:
self._input_edit.setMaximumHeight(72)
self._input_edit.setMinimumHeight(72)
# 初始可见性由 _apply_input_expanded 设置

# 改为（保持 TextEdit 锁 72 高，但动画改由外层 _input_area 控制）:
self._input_edit.setMinimumHeight(72)
self._input_edit.setMaximumHeight(72)
# 初始可见性由 _apply_input_expanded 设置（v4: 整个 _input_area 隐藏而非单 _input_edit）
```

并删掉原 `_animate_input_edit` 方法（v3 残留），改用外层抽屉动画见上面新方法 `_animate_input_area`。

> **注**：TextEdit 仍然锁 72 高（用户视觉习惯——单行输入）。抽屉从 0 ↔ 120 动画，120 = TextEdit 72 + spacing 8 + 按钮行 32 + 8 余量。抽屉外层 `maximumHeight` 限制配合 `setVisible(False)` 实现"整段消失"效果。

- [ ] **Step 4: 改 v3 测试用 `_input_area` 替代 `_input_edit`**

改 `tests/test_ai_panel_widget.py` 现有 3 个 v3 测试：

`test_input_starts_collapsed`（第 70-78 行）改为：

```python
def test_input_starts_collapsed(panel):
    p, _, _ = panel
    assert p.input_visible() is False
    # v4: 整个 _input_area 收起
    assert p._input_area.isVisible() is False
    assert p._input_area.maximumHeight() == 0
    assert p._toggle_btn.isChecked() is False
    assert p._toggle_btn.text() == ""  # v4: 无文字
```

`test_toggle_btn_click_expands_input`（第 119-131 行）改为：

```python
def test_toggle_btn_click_expands_input(panel, qtbot):
    p, _, _ = panel
    assert p.input_visible() is False
    p._toggle_btn.click()
    qtbot.waitUntil(
        lambda: p._input_area.isVisible() and p._input_area.maximumHeight() == _INPUT_DRAWER_HEIGHT,
        timeout=2000,
    )
    assert p.input_visible() is True
    assert p._toggle_btn.isChecked() is True
```

`test_toggle_btn_click_again_collapses_input`（第 134-148 行）改为：

```python
def test_toggle_btn_click_again_collapses_input(panel, qtbot):
    p, _, _ = panel
    p._toggle_btn.click()
    qtbot.waitUntil(
        lambda: p._input_area.isVisible() and p._input_area.maximumHeight() == _INPUT_DRAWER_HEIGHT,
        timeout=2000,
    )
    p._toggle_btn.click()
    qtbot.waitUntil(
        lambda: p._input_area.maximumHeight() == 0 and not p._input_area.isVisible(),
        timeout=2000,
    )
    assert p.input_visible() is False
```

- [ ] **Step 5: 跑新测试 + 改过的 v3 测试**

```bash
cd d:/PythonProjects/DesktopSprite
.venv/Scripts/python.exe -m pytest tests/test_ai_panel_widget.py::test_input_area_starts_hidden_with_zero_maximum_height tests/test_ai_panel_widget.py::test_input_area_visible_with_full_height_when_expanded tests/test_ai_panel_widget.py::test_input_area_hidden_after_collapse_animation tests/test_ai_panel_widget.py::test_input_starts_collapsed tests/test_ai_panel_widget.py::test_toggle_btn_click_expands_input tests/test_ai_panel_widget.py::test_toggle_btn_click_again_collapses_input -v --basetemp=./.pytest_basetmp
```

预期：6 个全部 PASS

- [ ] **Step 6: 提交**

```bash
cd d:/PythonProjects/DesktopSprite
git add desktop_sprite/ui/ai_panel.py tests/test_ai_panel_widget.py
git commit -m "feat(ui): v4 动画对象升级为整个 _input_area

- _apply_input_expanded 改动画 _input_area.maximumHeight（不再是 _input_edit）
- target=0 时动画结束后 setVisible(False)，整个抽屉消失
- TextEdit 拆掉 maxHeight 限制（外层抽屉统一管）
- toggle 文字/图标/tooltip 跟状态切换
- 3 个新测试 + 3 个 v3 测试改用 _input_area 断言"
```

---

## Task 3: 收起时"只有 toggle 可见"的可见性契约

**Files:**
- Modify: `tests/test_ai_panel_widget.py:316-333`（删 v3 的 `test_buttons_visible_even_when_input_collapsed`）
- Test: `tests/test_ai_panel_widget.py`（新增 3 个测试）

- [ ] **Step 1: 写失败的测试**——在 `tests/test_ai_panel_widget.py` 末尾追加：

```python
# ---- v4: 收起时只有 toggle 可见 ----

def test_only_toggle_visible_when_input_collapsed(panel):
    """v4: 收起时整个抽屉消失，只有 slim 栏里的 toggle 可见。"""
    p, _, _ = panel
    assert p.input_visible() is False
    # toggle 永远可见
    assert p._toggle_btn.isVisible() is True
    # 抽屉内控件全部隐藏
    assert p._input_edit.isVisible() is False
    assert p._clear_btn.isVisible() is False
    assert p._send_btn.isVisible() is False
    # 整个抽屉 widget 也隐藏
    assert p._input_area.isVisible() is False


def test_all_drawer_widgets_visible_when_input_expanded(panel, qtbot):
    """v4: 展开时抽屉内所有控件可见。"""
    p, _, _ = panel
    p._toggle_btn.click()
    qtbot.waitUntil(
        lambda: p._input_area.isVisible() and p._input_area.maximumHeight() == _INPUT_DRAWER_HEIGHT,
        timeout=2000,
    )
    assert p._input_edit.isVisible() is True
    assert p._clear_btn.isVisible() is True
    assert p._send_btn.isVisible() is True
    # toggle 仍然可见（slim 栏不受抽屉状态影响）
    assert p._toggle_btn.isVisible() is True


def test_slim_bar_has_top_divider(panel):
    """v4: slim 栏内部有 1px QFrame 顶边线。"""
    p, _, _ = panel
    frames = p._slim_bar.findChildren(QFrame)
    # 至少有一个 HLine 1px 高的 frame
    hlines = [
        f for f in frames
        if f.frameShape() == QFrame.HLine and f.height() == 1
    ]
    assert len(hlines) >= 1
```

并 import（顶部）：

```python
from PySide6.QtWidgets import QApplication, QFrame
```

- [ ] **Step 2: 跑测试看失败**

```bash
cd d:/PythonProjects/DesktopSprite
.venv/Scripts/python.exe -m pytest tests/test_ai_panel_widget.py::test_only_toggle_visible_when_input_collapsed tests/test_ai_panel_widget.py::test_all_drawer_widgets_visible_when_input_expanded tests/test_ai_panel_widget.py::test_slim_bar_has_top_divider -v --basetemp=./.pytest_basetmp
```

预期：3 个全部 FAIL（`_input_edit` 仍可见 / 旧 v3 行为：clear+send 仍可见）

- [ ] **Step 3: 删旧 v3 测试 + 改 `_input_area` 初始可见性**

1) 删 `tests/test_ai_panel_widget.py` 第 316-333 行整个 `test_buttons_visible_even_when_input_collapsed` 函数（v3 行为与 v4 矛盾）。

2) 改 `desktop_sprite/ui/ai_panel.py` 构造函数末尾（第 250-252 行附近）：

```python
# 旧（删除）:
# ---- 初始状态 ----
self._input_expanded = False
self._apply_input_expanded(self._load_input_expanded(), animate=False)

# 改为:
# ---- 初始状态 ----
self._input_expanded = False
# v4: 初始 _input_area 隐藏（不依赖 _apply_input_expanded 副作用）
self._input_area.setVisible(False)
self._input_area.setMaximumHeight(0)
self._apply_input_expanded(self._load_input_expanded(), animate=False)
```

> **关键**：`__init__` 阶段 _input_area 默认 `isVisible()=True`（QWidget 默认），新加的 `setVisible(False)` 保证初始就是隐藏。

- [ ] **Step 4: 跑新测试 + 删后全套确认**

```bash
cd d:/PythonProjects/DesktopSprite
.venv/Scripts/python.exe -m pytest tests/test_ai_panel_widget.py -v --basetemp=./.pytest_basetmp
```

预期：v4 全部通过；v3 中 `test_buttons_visible_even_when_input_collapsed` 已删；其余 v3 测试若涉及 `_input_edit.isVisible()` 的（`test_input_starts_collapsed`）已在 Task 2 改用 `_input_area`

- [ ] **Step 5: 提交**

```bash
cd d:/PythonProjects/DesktopSprite
git add desktop_sprite/ui/ai_panel.py tests/test_ai_panel_widget.py
git commit -m "feat(ui): v4 收起时只有 toggle 可见

- 初始 _input_area.setVisible(False) + setMaximumHeight(0)
- 抽屉消失时 _input_edit / _clear_btn / _send_btn 全部隐藏
- 新增 test_only_toggle_visible_when_input_collapsed 等 3 个测试
- 删 v3 的 test_buttons_visible_even_when_input_collapsed（行为矛盾）"
```

---

## Task 4: ping 失败时 toggle 保持可用、抽屉禁用

**Files:**
- Modify: `desktop_sprite/ui/ai_panel.py:448-459`（`_on_ping_done`）
- Modify: `tests/test_ai_panel_widget.py:214-223`（v3 的 `test_toggle_btn_disabled_when_ping_fails`）
- Test: `tests/test_ai_panel_widget.py`（新增 1 个测试）

- [ ] **Step 1: 写失败的测试**——在 `tests/test_ai_panel_widget.py` 末尾追加：

```python
# ---- v4: ping 失败时 toggle 仍可用，抽屉禁用 ----

def test_toggle_still_enabled_when_ping_fails():
    """v4: ping 失败时 _toggle_btn 保持可用，让用户能展开看到禁用状态。"""
    from desktop_sprite.ai.provider import AuthError
    app = QApplication.instance() or QApplication([])
    orch = _StubOrchestrator(ping_error=AuthError("bad"))
    p = AIPanelWidget(orchestrator=orch)
    try:
        p.trigger_ping_for_test()
        assert p._toggle_btn.isEnabled() is True
    finally:
        p.deleteLater()


def test_input_area_disabled_when_ping_fails():
    """v4: ping 失败时 _input_area 禁用（TextEdit / clear / send 一起禁用）。"""
    from desktop_sprite.ai.provider import AuthError
    app = QApplication.instance() or QApplication([])
    orch = _StubOrchestrator(ping_error=AuthError("bad"))
    p = AIPanelWidget(orchestrator=orch)
    try:
        p.trigger_ping_for_test()
        assert p._input_area.isEnabled() is False
        # 抽屉内子控件跟着禁用
        assert p._input_edit.isEnabled() is False
        assert p._clear_btn.isEnabled() is False
        assert p._send_btn.isEnabled() is False
    finally:
        p.deleteLater()
```

- [ ] **Step 2: 跑测试看失败**

```bash
cd d:/PythonProjects/DesktopSprite
.venv/Scripts/python.exe -m pytest tests/test_ai_panel_widget.py::test_toggle_still_enabled_when_ping_fails tests/test_ai_panel_widget.py::test_input_area_disabled_when_ping_fails -v --basetemp=./.pytest_basetmp
```

预期：2 个全部 FAIL（`_toggle_btn` 在 v3 行为下被禁用 / `_input_area` 在 v3 行为下保持 enabled）

- [ ] **Step 3: 改 `_on_ping_done`**——替换 `desktop_sprite/ui/ai_panel.py` 第 448-459 行：

```python
@Slot(float, object)
def _on_ping_done(self, latency_ms, error) -> None:
    self._ping_busy = False
    if error is not None:
        self._status.set_state(available=False, latency_ms=None)
        # v4: toggle 保持可用（让用户能展开看到禁用态）；只禁抽屉
        self._toggle_btn.setEnabled(True)
        self._input_area.setEnabled(False)
        return
    self._status.set_state(available=True, latency_ms=latency_ms)
    if self._orchestrator is not None:
        self._toggle_btn.setEnabled(True)
        self._input_area.setEnabled(True)
```

- [ ] **Step 4: 删 v3 旧测试 `test_toggle_btn_disabled_when_ping_fails`（第 214-223 行）**

```python
# 删除整个函数 test_toggle_btn_disabled_when_ping_fails 及其上方
# "# ---- API 不可用时禁用切换按钮 ----" 注释保留（v4 行为类似）
```

- [ ] **Step 5: 跑全套**

```bash
cd d:/PythonProjects/DesktopSprite
.venv/Scripts/python.exe -m pytest tests/test_ai_panel_widget.py -v --basetemp=./.pytest_basetmp
```

预期：所有 panel 测试 PASS（约 27+ 个：v3 改造后 22 + v4 新增 7 - 删 1 ≈ 28）

- [ ] **Step 6: 跑项目级回归**（确保没破坏流式 / orchestrator / channel 等模块）

```bash
cd d:/PythonProjects/DesktopSprite
.venv/Scripts/python.exe -m pytest tests/ -v --basetemp=./.pytest_basetmp -x
```

预期：全部通过

- [ ] **Step 7: 提交**

```bash
cd d:/PythonProjects/DesktopSprite
git add desktop_sprite/ui/ai_panel.py tests/test_ai_panel_widget.py
git commit -m "feat(ui): v4 ping 失败时 toggle 保持可用、抽屉禁用

- _on_ping_done 失败时只 setEnabled(False) on _input_area
- toggle 保持 setEnabled(True)，让用户能展开抽屉看到禁用态
- 删 v3 的 test_toggle_btn_disabled_when_ping_fails
- 新增 test_toggle_still_enabled_when_ping_fails + test_input_area_disabled_when_ping_fails"
```

---

## Task 5: 手动验证 + 文档收尾

**Files:** 无（手动 + 可选 README）

- [ ] **Step 1: 启动应用，肉眼确认 v4 视觉**

```bash
cd d:/PythonProjects/DesktopSprite
.venv/Scripts/python.exe -m desktop_sprite
```

肉眼检查：
- 收起态：整页只有"AI 互动"标题 + 历史区 + 底部 slim 栏（右上角一个 ⬆ 图标按钮 + 1px 灰线）
- 点击 ⬆：输入抽屉从 slim 栏**上方**滑出（72px 高的输入框 + 按钮行：清空 / 发送）
- 点击 ⬇：抽屉收起，slim 栏图标变回 ⬆
- 在抽屉里输入文字，点"发送"：用户气泡出现，抽屉自动收起
- 关闭应用、重新打开：抽屉状态保持
- 关闭 AI 模拟器 / 改 config 关掉 AI：右下角状态点变红；点 ⬆ 仍能展开抽屉，但里面 3 个控件全灰

- [ ] **Step 2:（可选）更新 CLAUDE.md / README**——如果项目根有 `CLAUDE.md` 或 `desktop_sprite/ui/README.md`，在 "AI 互动面板" 段补一句"slim 栏设计 + 仅图标 toggle"。

- [ ] **Step 3: 提交文档收尾（如有）**

```bash
cd d:/PythonProjects/DesktopSprite
git add CLAUDE.md docs/README.md desktop_sprite/ui/README.md 2>/dev/null || true
git diff --cached --quiet || git commit -m "docs: AI 互动面板 v4 slim 栏 + 仅图标 toggle 备注"
```

---

## 验收清单

- [ ] `pytest tests/test_ai_panel_widget.py -v` 全部通过
- [ ] `pytest tests/ -v` 全部通过
- [ ] 收起态只剩历史区 + slim 栏（图标 toggle）
- [ ] 展开时输入抽屉从 slim 栏上方滑出
- [ ] toggle 仅图标 + tooltip
- [ ] slim 栏 1px 顶边线
- [ ] 发送消息后自动收起
- [ ] 重启后抽屉状态保持
- [ ] ping 失败时 toggle 可点开抽屉，抽屉内禁用

## 不在本计划范围内

- 取消正在进行的流式生成（v5 候选）
- 流式状态指示（打字光标 / "..." 占位）
- 历史持久化
- 多 provider failover
- Anthropic / Gemini 流式适配
