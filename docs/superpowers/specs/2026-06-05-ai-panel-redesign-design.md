# AI 互动面板 v3 — FluentUI 扁平化 + 流式输出

- **日期**：2026-06-05
- **状态**：待评审 / 待实施
- **范围**：AIPanelWidget UI 重构 + AIProvider 流式输出（涉及 orchestrator / channel / 三个 channel 子类）
- **上一版**：[2026-06-04-ai-interaction-system-design.md](../2026-06-04-ai-interaction-system-design.md)（v1 基础设施 + v2 聊天气泡 UI）

---

## 1. 背景与目标

v2 实现了基础聊天气泡（CardWidget 背景 + 圆形 + 按钮），但有两个不足：
1. **视觉风格偏重**——历史区 / 输入区都有 CardWidget 边框，与 FluentUI 扁平风格不搭；圆形 FAB 不在 FluentUI 控件库里
2. **AI 响应是一次性返回**——provider 阻塞调完才一次性把整段文本塞到气泡，桌宠气泡也是一次弹出，没有"打字"效果

**v3 目标**：
- 面板去 CardWidget 背景，输入区扁平化
- 圆形 FAB → FluentUI 风格 PushButton，文案显示当前状态（"展开"/"收起"）
- 按钮顺序固定：`清空` → `展开/收起` → `发送`（发送最右）
- 聊天消息用 FluentUI 风（AI 带头像）
- AI 输出改为 SSE 流式：UI 气泡边收边画、桌宠气泡边收边显示
- 输入区展开/收起状态写入 `config/user/ui_state.json`（跨重启保留）

**v3 不做**：
- 气泡持久化（关窗清空保持原状）
- 消息编辑 / 撤回 / 搜索
- 取消正在进行的流式生成（v4 再说）
- 多 provider failover / 厂商切换

---

## 2. 设计原则

1. **分层职责不变**——Provider 管网络协议、Orchestrator 管线程与扇出、Channel 管呈现；v3 只是在三层各加流式方法，不重写也不破坏抽象
2. **Channel 增量演进**——不重写 channel，只增加 `dispatch_stream_*` 三个钩子（默认 no-op）；OsNotificationChannel 不动
3. **状态分离**——流式消息状态存在 panel/orchestrator 内存里；UI 偏好（输入区展开）走 `ui_state.json` 持久化
4. **不破坏现有契约**——`append_history(AIText)` / `clear_history()` / `messages()` / `bubble_count()` / `status_text()` / `status_available()` / `input_visible()` / `trigger_ping_for_test()` 8 个测试用 API 全部保留
5. **异常隔离不变**——流式中途出错走现有 fallback 路径，调用 `dispatch(AIText(fallback_text, "fallback"))`，**不**抛给用户

---

## 3. UI 布局（最终态）

### 3.1 结构

```
AIPanelWidget (objectName="aiPanelPage")
├── 标题行 (QHBoxLayout)
│   ├── TitleLabel("AI 互动")
│   ├── addStretch(1)
│   └── _StatusDot（右上角）
│
├── 历史区 (QWidget, 无 CardWidget 外壳，setStyleSheet 透明)
│   └── SmoothScrollArea (enableTransparentBackground)
│       └── chatBubblesInner (QVBoxLayout, spacing=8, margin=4)
│           ├── 消息行 0  (QHBoxLayout, no margin)
│   AI 行:  [AvatarWidget("AI", 32px)] [ChatBubble]  [addStretch(1)]
│   User 行: [addStretch(1)] [ChatBubble]
│           ├── 消息行 1
│           ├── ...
│           └── addStretch(1)   ← 末尾 stretch，气泡贴顶
│
└── 输入区 (QWidget, 无 CardWidget 外壳，可折叠)
    ├── TextEdit (72px 高, 始终存在，setVisible 控制)
    │       [user input 框]
    └── 按钮行 (QHBoxLayout, 始终可见)
        ├── addStretch(1)
        ├── PushButton("清空历史", FIF.DELETE)
        ├── ToggleButton("展开"/"收起", FIF.UP/DOWN, checked=...)
        └── PrimaryPushButton("发送", FIF.SEND)
```

### 3.2 关键决定

| 项 | v2 现状 | v3 改动 | 原因 |
|---|---|---|---|
| 历史区容器 | `CardWidget("aiHistoryCard")` | `QWidget` + `setAttribute(Qt.WA_StyledBackground, False)` | 去背景 |
| 历史区 ScrollArea | `SmoothScrollArea` | 保留 | 不变 |
| 输入区容器 | `CardWidget("aiInputCard")` | `QWidget` + 透明 | 去外框 |
| 切换按钮 | 自定义 `_FabButton`（56×56 圆形，paintEvent 自画） | `ToggleButton` + 文字 | FluentUI 风格、状态可见 |
| 按钮顺序 | 清空 + 发送（同行） | 清空 / 展开/收起 / 发送（同行） | 用户要求：发送最右 |
| AI 气泡 | 左对齐 + 浅色 | 左对齐 + 浅色 + AvatarWidget 头像 | 区分发送方 |
| User 气泡 | 右对齐 + 主题色 | 保留 | 不变 |
| `history_max_lines` | 死字段 | 在 `_add_bubble` 头部 trim | 启用配置 |
| 主题色 | qfluentwidgets 主题 | 保留；走 `setTextColor` 不走 `setStyleSheet("color:...")` | `ui/README.md` 强制规范 |

### 3.3 动画保留

- 输入区展开/收起：`maximumHeight` 0 ↔ 160，`QPropertyAnimation` 200ms `OutCubic`（与 v2 相同）
- 切换按钮图标：`FIF.UP`（展开状态时显示"收起"） / `FIF.DOWN`（收起状态时显示"展开"）
- 气泡出现：不做动画（保持简单）

### 3.4 状态持久化

新增 `ui_state.json["ai_panel"]["input_expanded"]: bool`。

```
AIPanelWidget 构造:
  state = UiStateStore(ui_state_path).read()
  expanded = bool(state.get("ai_panel", {}).get("input_expanded", False))
  _apply_input_expanded(expanded, animate=False)   # 初始套用，不动画

_toggle_input 被点击:
  self._input_expanded = not self._input_expanded
  _animate_input(target)
  _save_input_expanded()   # 写盘

_save_input_expanded:
  UiStateStore.update(lambda s: s.setdefault("ai_panel", {})["input_expanded"] = self._input_expanded)
```

`ui_state_path` 由 `MainWindow` 在 `_ai_panel_page()` 懒构造时传入，路径解析与现有 `main_window.geometry` / `theme` 一致：
```python
self._ai_panel_widget = AIPanelWidget(
    orchestrator=self._ai_orchestrator,
    history_max_lines=self._ai_history_max_lines,
    ui_state_path=self.ui_state_path,   # ← 新增
)
```

---

## 4. 流式输出架构

### 4.1 三层职责再确认

| 层 | 职责 | v3 新增 |
|---|---|---|
| **Provider** | 唯一懂 HTTP/SSE 协议 | `generate_stream() -> Iterator[str]` |
| **Orchestrator** | 唯一管线程、跨线程、错误、扇出 | `_StreamWorker` + `_stream_event` Signal + `_on_stream_event` slot + `_dispatch_use_case_streaming()` |
| **Channel** | 唯一知道怎么呈现 | `dispatch_stream_start / delta / end`（默认 no-op） |

### 4.2 信号 / 事件协议

Orchestrator 用一个统一 Signal 投递所有流事件：
```python
_stream_event = Signal(str, str, str, object)
#  (stream_id, use_case_id, kind, payload)
#  kind ∈ {"start", "delta", "end", "error"}
#  - start: payload = None
#  - delta: payload = str (delta 文本)
#  - end:   payload = (full_text: str, source: str)
#  - error: payload = Exception
```

`_on_stream_event` slot（在主线程跑）：
```python
@Slot(str, str, str, object)
def _on_stream_event(self, stream_id, use_case_id, kind, payload):
    if kind == "start":
        for ch in self._channels: ch.dispatch_stream_start(stream_id, use_case_id)
    elif kind == "delta":
        # 累积 full_text 不在这里做，每个 channel 自己管自己的缓冲
        for ch in self._channels: ch.dispatch_stream_delta(stream_id, payload, use_case_id)
    elif kind == "end":
        full_text, source = payload
        for ch in self._channels: ch.dispatch_stream_end(stream_id, full_text, source, use_case_id)
    elif kind == "error":
        # 走 fallback 路径，channel 仍然收完整 AIText
        err = payload
        # 找原 use_case
        uc = self._use_cases.get(use_case_id)
        if uc is not None:
            self._fallback_or_skip(uc, f"stream err={type(err).__name__}")
```

### 4.3 Channel 抽象

`desktop_sprite/ai/channel.py`：
```python
class Channel(ABC):
    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def dispatch(self, message: AIText) -> None:
        ...

    # v3 新增（默认 no-op，Channel 选择性重写）
    def dispatch_stream_start(self, stream_id: str, use_case_id: str) -> None:
        pass

    def dispatch_stream_delta(self, stream_id: str, delta: str, use_case_id: str) -> None:
        pass

    def dispatch_stream_end(
        self, stream_id: str, full_text: str, source: str, use_case_id: str,
    ) -> None:
        pass
```

### 4.4 各 Channel 行为

| Channel | 行为 |
|---|---|
| **ChatPanelChannel** | 重写 3 个方法，调 `panel.append_stream_start / delta / end` |
| **PetBubbleChannel** | 重写 3 个方法：start 调 `bubble.show_message("")` 创建气泡；delta 调 `bubble.append_text(delta)`；end 启动原 `_bubble_visible_seconds` 计时器 |
| **OsNotificationChannel** | **只重写 `dispatch_stream_end`**（start / delta 用默认 no-op）；end 内构造 `AIText(full_text, source, use_case_id, time.time())` 调 `self.dispatch(...)` 走原通知路径。统一走 orchestrator 的 end 事件，避免在 orchestrator 端对不同 channel 分流 |

### 4.5 Panel 端增量 API

`AIPanelWidget` 新增 3 个公开方法（仅 `ChatPanelChannel` 用）：
```python
def append_stream_start(self, stream_id: str, use_case_id: str) -> None:
    """新建空白 AI ChatBubble，存入 _stream_bubbles[stream_id]。"""

def append_stream_delta(self, stream_id: str, delta: str, use_case_id: str) -> None:
    """取 _stream_bubbles[stream_id]，调 bubble.append_text(delta)，自动滚到底。"""

def append_stream_end(self, stream_id: str, full_text: str, source: str, use_case_id: str) -> None:
    """从 _stream_bubbles 弹出，标记完成。"""
```

`ChatBubble` 扩展一个 `append_text(delta: str)` 方法：把 `delta` 拼到 `_body`（BodyLabel），调 `_body.adjustSize()`，触发 widget 重排。

`_stream_bubbles: dict[str, ChatBubble]` 用 stream_id 作 key。同一个 use_case 只会有一个进行中的流（节流 + max_inflight=1 兜底），不冲突。

### 4.6 PetBubble 端

`BubbleOverlayWindow` 新增 `append_text(delta: str) -> None`：
- 把 delta 拼到 `_label.setText(self._label.text() + delta)`
- 调 `_label.adjustSize()` 触发布局
- 调 `self._reset_hide_timer()` 重置自动隐藏计时器（保证流期间气泡不消失）

`PetBubbleChannel` 在 start/delta/end 调对应方法。

### 4.7 流式时序图

```
用户                  AIPanelWidget            Orchestrator              _StreamWorker              OpenAIProvider
 │  点击"发送"            │                          │                          │                          │
 ├──────────────────────►│ _on_send_clicked         │                          │                          │
 │                       │ trigger_test()           │                          │                          │
 │                       ├─────────────────────────►│ _on_event                │                          │
 │                       │                          │ _dispatch_use_case_      │                          │
 │                       │                          │   streaming()            │                          │
 │                       │                          │ 构造 _StreamWorker       │                          │
 │                       │                          ├─────────────────────────►│ run()                    │
 │                       │                          │                          │ provider.generate_stream()│
 │                       │                          │                          ├─────────────────────────►│
 │                       │                          │                          │                          │ httpx.stream(POST...)
 │                       │                          │                          │                          │ SSE: data: {...}
 │                       │                          │                          │ emit("start")            │ ◄─┐
 │                       │                          │ _on_stream_event(start)  │                          │   │
 │                       │                          ├──────────────────────────┤                          │   │
 │                       │ append_stream_start()    │                          │                          │   │
 │                       │◄─────────────────────────┤                          │                          │   │
 │                       │ (创建空 AI 气泡)         │                          │                          │   │
 │                       │                          │                          │ SSE: data: {...}         │   │
 │                       │                          │ emit("delta", "你")       │ ◄────────────────────────┘   │
 │                       │ append_stream_delta()    │                          │                          │
 │                       │ "你" 拼到气泡             │                          │                          │
 │                       │                          │ emit("delta", "好")       │ ◄──── ...                 │
 │                       │ append_stream_delta()    │                          │                          │
 │                       │ "好" 拼到气泡             │                          │                          │
 │                       │                          │                          │ SSE: data: [DONE]        │
 │                       │                          │ emit("end", full_text)   │ ◄──── 收尾                │
 │                       │ append_stream_end()      │                          │                          │
 │                       │ (标记完成)                │                          │                          │
 │                       │                          │ _on_stream_event(end)    │                          │
 │                       │                          ├── 3 channel 全 dispatch_stream_end ──────────────────────►│
 │                       │                          │  OsNotification 内转 dispatch(AIText) ─────────────────►│
```

---

## 5. 关键文件改动清单

| 文件 | 改动 | 行数估计 |
|---|---|---|
| `desktop_sprite/ai/provider.py` | `AIProvider` 加 `generate_stream` 抽象；`OpenAIProvider` 实现 `httpx.stream` + SSE 解析；`DisabledProvider` 抛 `ProviderDisabled` | +60 |
| `desktop_sprite/ai/orchestrator.py` | 新增 `_StreamWorker` / `_stream_event` Signal / `_on_stream_event` slot / `_dispatch_use_case_streaming()`；`_dispatch_use_case()` 改走流式路径 | +90 |
| `desktop_sprite/ai/channel.py` | `Channel` 加 3 个默认 no-op 方法 | +12 |
| `desktop_sprite/ai/channels/chat_panel.py` | 重写 3 个 `dispatch_stream_*` | +15 |
| `desktop_sprite/ai/channels/pet_bubble.py` | 重写 3 个 `dispatch_stream_*` | +20 |
| `desktop_sprite/ai/channels/os_notification.py` | 不改 | 0 |
| `desktop_sprite/ui/ai_panel.py` | **UI 重构**：去 CardWidget / 去 _FabButton / 改用 ToggleButton / 加 AvatarWidget / 加 `append_stream_*` 3 方法 / 接入 `ui_state_path` / `history_max_lines` 启用 trim | +120 / -80 |
| `desktop_sprite/ui/main_window.py` | `_ai_panel_page()` 多传 `ui_state_path` | +1 |
| `desktop_sprite/ui/bubble_overlay.py` | `BubbleOverlayWindow` 加 `append_text(delta)` | +8 |
| `desktop_sprite/utils/config.py` | `AIConfig` 加 `streaming: bool = True` | +3 |
| `config/default.json` | 加 `"streaming": true` 默认值 | +1 |
| `tests/ai_fakes.py` | `FakeProvider` 加 `generate_stream` 支持（接受 list[list[str]]，每个 use_case 一组分块） | +25 |
| `tests/test_ai_panel_widget.py` | 改：清空后不再断言 `_FabButton`；改按钮顺序断言；新增 `append_stream_*` 3 测试；新增 `ui_state_path` 持久化 1 测试；`history_max_lines` trim 1 测试 | +60 / -10 |
| `tests/test_ai_provider.py` | 新增 `generate_stream` 测试：SSE 解析 / 累积 / 多 delta / `[DONE]` 终止 / 错误处理 | +90 |
| `tests/test_ai_orchestrator.py` | 新增流式路径测试：delta 触达 channel / mid-stream error fallback / 跨 use_case 不冲突 | +70 |
| `tests/test_ai_channels.py` | 新增 3 个 `dispatch_stream_*` 测试 | +30 |
| `tests/test_ai_bubble_overlay.py` | 新增 `append_text` 测试 | +15 |

**总计估计**：约 +540 / -90 行净增，分布在 13 个文件。

---

## 6. 数据结构

### 6.1 AIText（**不变**）

```python
@dataclass(frozen=True, slots=True)
class AIText:
    text: str
    source: str  # "ai" / "fallback"
    use_case_id: str
    timestamp: float
```

流式结束时不另造新数据类；`dispatch_stream_end` 直接收到 `(full_text, source)` 元组，传给 channel。

### 6.2 新增模块级常量

`provider.py`：
```python
_STREAM_DONE_MARKER = "[DONE]"   # OpenAI SSE 终止符
_STREAM_KEEPALIVE = ": keep-alive"  # SSE 注释行
```

`orchestrator.py`：
```python
_STREAM_END_MARKER = "[DONE]"   # worker 内部用
```

### 6.3 ui_state.json 新 key

```json
{
  "theme": "深色",
  "main_window": { "geometry": "..." },
  "settings": { "expanded": {} },
  "ai_panel": { "input_expanded": true }
}
```

---

## 7. 错误处理

| 错误 | 触发时机 | 处理 |
|---|---|---|
| 流开始前错误（鉴权、超时） | `_StreamWorker.run()` 第一段 | `emit("error", err)` → orchestrator 走 `fallback_or_skip` |
| 流中途网络断开 | SSE iter 抛异常 | worker 捕获，`emit("error", err)` → fallback；流已收到的 delta 仍**保留**在 panel 气泡（不丢） |
| 流中途服务返回 5xx | 解析时 status_code 检查 | 同上 |
| provider 是 `DisabledProvider` | `generate_stream()` 第一行 raise | `emit("error", ProviderDisabled)` → fallback |
| panel 不存在（懒构造未触发） | `ChatPanelChannel.dispatch_stream_*` 调 `panel.append_stream_*` | 内部 `panel = self._panel_provider(); if panel is None: return`（与现有 `dispatch` 一致） |
| 流期间 panel 被关闭 | `_stream_bubbles[stream_id]` 找不到 | `append_stream_delta` 静默 no-op；`_on_stream_event` 不抛 |
| `ui_state.json` 写盘失败 | `UiStateStore.write` 内部 try/except | 日志告警，不弹窗（与现有 `geometry` / `theme` 行为一致） |

---

## 8. 测试策略

### 8.1 现有测试保留

`test_ai_panel_widget.py` 中 18 个测试函数：
- `test_panel_has_title_and_status_dot` ✅
- `test_panel_uses_smoothscrollarea_and_history_card` → 改名为 `test_panel_uses_smoothscrollarea_for_history`
- `test_panel_has_fab_button` → **删除**（v3 没有 FAB）
- `test_input_card_starts_collapsed` → 改名为 `test_input_starts_collapsed`，断言改为 `_input_expanded is False`
- `test_append_history_creates_chat_bubble` ✅
- `test_user_message_renders_as_user_bubble` ✅
- `test_clear_history_removes_all_bubbles` ✅
- `test_bubble_role_object_name` ✅
- `test_fab_click_expands_input` → 改名为 `test_toggle_button_expands_input`
- `test_fab_click_again_collapses_input` → 改名为 `test_toggle_button_collapses_input`
- `test_send_button_dispatches_orchestrator_with_user_hint` ✅
- `test_send_with_empty_text_is_noop` ✅
- `test_status_dot_initial_state_idle` ✅
- `test_status_dot_green_after_successful_ping` ✅
- `test_status_dot_red_after_failed_ping` ✅
- `test_status_dot_yellow_for_warn_latency` ✅
- `test_fab_disabled_when_ping_fails` → 改名为 `test_toggle_button_disabled_when_ping_fails`
- `test_fab_enabled_when_ping_succeeds` → 改名为 `test_toggle_button_enabled_when_ping_succeeds`

### 8.2 新增测试

`test_ai_panel_widget.py`：
- `test_chat_bubble_has_avatar_for_ai_role` —— 断言 AI 气泡左侧有 AvatarWidget
- `test_input_expanded_persists_to_ui_state` —— 临时目录写 ui_state.json，构造 panel，断言初始状态；点击 toggle 再造 panel，断言恢复
- `test_history_max_lines_trims_head` —— 构造 panel `history_max_lines=3`，add 5 条，断言只剩 3 条且是后 3 条
- `test_append_stream_start_creates_ai_bubble` —— 调 `append_stream_start("s1", "uc")`，断言 `bubble_count() == 1` 且 role 是 "ai"
- `test_append_stream_delta_appends_to_bubble` —— start 后调 2 次 delta，断言 bubble text 是拼接结果
- `test_append_stream_end_finalizes` —— start/delta/delta/end，end 后断言 `_stream_bubbles` 为空
- `test_no_card_widget_for_history_or_input` —— 断言 panel 不再持有 `aiHistoryCard` / `aiInputCard` 这两个 objectName

`test_ai_provider.py`：
- `test_openai_provider_stream_yields_deltas`
- `test_openai_provider_stream_handles_done_marker`
- `test_openai_provider_stream_accumulates_full_text`
- `test_openai_provider_stream_401_raises_auth_error`
- `test_openai_provider_stream_timeout_raises_timeout_error`
- `test_disabled_provider_stream_raises_provider_disabled`

`test_ai_orchestrator.py`：
- `test_streaming_dispatch_fans_out_deltas_to_channels`
- `test_streaming_midstream_error_falls_back`
- `test_streaming_dispatch_emits_end_event`
- `test_streaming_disabled_provider_does_not_call_channels_with_delta`

`test_ai_channels.py`：
- `test_chat_panel_channel_dispatches_stream_to_panel`
- `test_pet_bubble_channel_dispatches_stream_to_bubble`
- `test_os_notification_channel_stream_methods_are_noop`

### 8.3 测试 fixture 改动

`tests/test_ai_panel_widget.py` fixture 接受可选 `ui_state_path`：
```python
@pytest.fixture
def panel(qtbot, tmp_path):
    orch = _StubOrchestrator()
    ui_state = tmp_path / "ui_state.json"
    p = AIPanelWidget(orchestrator=orch, history_max_lines=50, ui_state_path=ui_state)
    qtbot.addWidget(p)
    p.resize(900, 700)
    return p, orch, ui_state
```

---

## 9. 风险点 & 缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| `httpx.stream()` 在子线程里长时间占用 | 中 | `request_timeout_s` 已生效（OpenAIProvider 在 stream 上下文也设 timeout） |
| SSE 多行 / chunked 边界 | 中 | 严格按 `data: ` 前缀切行，跳过空行 / 注释行；遇 `[DONE]` 终止；`json.loads` 失败 skip 不抛 |
| 流期间多次 emit 造成 UI 卡顿 | 低 | Qt 主线程 queued signal 已串行化；delta 字符串一般 < 100 字节，label.adjustSize 不卡 |
| `history_max_lines` 改动后动画错位 | 低 | trim 头部时不打断动画；只在 `_add_bubble` 末尾同步 trim |
| 主题切换时已存在的流气泡颜色不一致 | 低 | 流气泡与一次性气泡共用同一个 `ChatBubble` 类，主题切换走 qfluentwidgets 内置机制 |
| `OsNotificationChannel` 流期间空文本触发空通知 | 低 | `dispatch_stream_start / delta` 默认 no-op；`dispatch_stream_end` 内构造完整 AIText 走原通知路径，**不**在流期间触发空通知 |
| 旧测试 `test_fab_*` 系列断言失败 | 中 | 同步更新测试函数名 / 断言（§8.1） |
| `BubbleOverlayWindow` 没现成 `append_text` | 中 | 加 8 行方法 + 重置 hide timer |
| Pet bubble 在流期间累积文本过长 | 低 | panel 端 75% 宽度上限同款；pet bubble 由 overlay 自己控制最大宽度 |

---

## 10. 不在范围内（v4 候选）

- 取消正在进行的流式生成（`AIOrchestrator.cancel_current()`）
- 流式状态指示（AI 正在打字时光标 / "..." 占位）
- 消息编辑 / 撤回 / 删除单条
- 历史持久化（关窗后恢复）
- 多 provider failover / 厂商切换
- 真实事件源接入（v1 spec 已留 v2 接入点）
- Anthropic / Gemini 流式格式适配

---

## 11. 实施顺序建议

1. `channel.py` 加 3 个 no-op 方法（最小风险先行）
2. `provider.py` 加 `generate_stream` 抽象 + OpenAIProvider 实现 + 单元测试
3. `orchestrator.py` 加 `_StreamWorker` / Signal / slot / 流式 dispatch 路径
4. `chat_panel.py` / `pet_bubble.py` 重写 3 个流式方法 + `bubble_overlay.py` 加 `append_text`
5. `ai_panel.py` UI 重构（去 CardWidget / 去 FAB / 加 AvatarWidget / 加 `append_stream_*`）
6. `main_window.py` 传 `ui_state_path`
7. `config.py` / `default.json` 加 `streaming` 字段
8. 更新 `tests/ai_fakes.py` + 全部测试用例
9. 全量 pytest 通过
10. 手动跑一次：发消息看面板打字效果、看桌宠气泡打字效果、看通知一次性弹

---

## 12. 验收标准

- ✅ pytest 全部通过（现有 18 个测试 + 新增 ~20 个）
- ✅ 面板视觉上无 CardWidget 边框（手动确认）
- ✅ 发送消息后，气泡内容是逐字出现而不是一次性显示
- ✅ 桌宠气泡内容是逐字出现
- ✅ 输入区展开后关闭应用，重启时仍保持展开
- ✅ `append_history(AIText)` / `clear_history()` / `messages()` / `bubble_count()` / `status_text()` / `status_available()` / `input_visible()` / `trigger_ping_for_test()` 8 个测试用 API 签名不变
- ✅ `OsNotificationChannel` 行为不变（流期间 no-op，end 触发一次性通知）
- ✅ provider 关闭时（`ai.enabled=false`）流式路径走 fallback，UI 收到 fallback 文本气泡
