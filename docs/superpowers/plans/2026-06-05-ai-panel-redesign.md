# AI 互动面板 v3 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 AI 互动面板改成 FluentUI 扁平风（去 CardWidget / 去 _FabButton），并把 AI 输出从一次性同步改为 SSE 流式（UI 气泡与桌宠气泡逐字出现）。

**Architecture:** 三层各加方法——Provider 加 `generate_stream() -> Iterator[str]`（SSE 解析）、Orchestrator 加 `_StreamWorker` + Signal + 流式 dispatch 路径、Channel 加 3 个 `dispatch_stream_*` 钩子（默认 no-op）。面板 UI 用 `QWidget` 取代 `CardWidget`、`ToggleButton` 取代 `_FabButton`、`AvatarWidget` 给 AI 气泡加头像；输入区展开/收起状态写入 `ui_state.json` 跨重启保留。

**Tech Stack:** Python ≥ 3.10、PySide6 ≥ 6.7、httpx（流式 HTTP 客户端 `httpx.stream()`）、qfluentwidgets 1.11.2（`ToggleButton` / `AvatarWidget` / `BodyLabel`）、pytest。

**Spec:** [../specs/2026-06-05-ai-panel-redesign-design.md](../specs/2026-06-05-ai-panel-redesign-design.md)

---

## File Structure

### 修改既有（13 个文件）

| 文件 | 改动摘要 |
|---|---|
| `desktop_sprite/ai/channel.py` | `Channel` 加 3 个默认 no-op `dispatch_stream_*` 方法 |
| `desktop_sprite/ai/provider.py` | `AIProvider` 加 `generate_stream` 抽象；`OpenAIProvider` 实现 `httpx.stream` + SSE；`DisabledProvider` 抛 `ProviderDisabled` |
| `desktop_sprite/ai/orchestrator.py` | 新增 `_StreamWorker` / `_stream_event` Signal / `_on_stream_event` slot / `_dispatch_use_case_streaming()` |
| `desktop_sprite/ai/channels/chat_panel.py` | 重写 3 个 `dispatch_stream_*` → `panel.append_stream_*` |
| `desktop_sprite/ai/channels/pet_bubble.py` | 重写 3 个 `dispatch_stream_*` → `bubble.show_message` / `bubble.append_text` |
| `desktop_sprite/ai/channels/os_notification.py` | 重写 `dispatch_stream_end` → `self.dispatch(AIText(...))` |
| `desktop_sprite/ui/ai_panel.py` | **UI 重构**（去 CardWidget / 去 _FabButton / 加 ToggleButton / 加 AvatarWidget / 加 `append_stream_*` 3 方法 / 接入 `ui_state_path` / 启用 `history_max_lines` trim） |
| `desktop_sprite/ui/main_window.py` | `_ai_panel_page()` 多传 `ui_state_path` |
| `desktop_sprite/ui/bubble_overlay.py` | `BubbleOverlayWindow` 加 `append_text(delta)` + 重置 hide timer |
| `desktop_sprite/utils/config.py` | `AIConfig` 加 `streaming: bool = True` |
| `config/default.json` | `ai.streaming = true` |
| `tests/ai_fakes.py` | `FakeProvider` 加 `generate_stream` |
| `tests/test_ai_panel_widget.py` | 改 fab → toggle 断言 / 增 ui_state + stream + history_max_lines + no_card 等 7 测试 |
| `tests/test_ai_provider.py` | 增 6 个 stream 测试 |
| `tests/test_ai_orchestrator.py` | 增 4 个 streaming 测试 |
| `tests/test_ai_channels.py` | 增 3 个 stream 钩子测试 |
| `tests/test_ai_bubble_overlay.py` | 增 `append_text` 测试 |

**总计**：~+540 / -90 行。

---

## 任务依赖图

```
Task 1 (Channel 抽象加 3 个钩子)
  └─ Task 2 (AIProvider 加 generate_stream 抽象)
       └─ Task 3 (DisabledProvider 实现)
       └─ Task 4 (OpenAIProvider SSE 实现)
  └─ Task 5 (Orchestrator 流式 dispatch)
       ├─ Task 6 (ChatPanelChannel 钩子)
       ├─ Task 7 (BubbleOverlayWindow.append_text)
       │    └─ Task 8 (PetBubbleChannel 钩子)
       └─ Task 9 (OsNotificationChannel end 钩子)
  Task 10 (FakeProvider streaming)
Task 11-15 (AIPanelWidget UI 重构 5 个子任务)
  └─ Task 16 (MainWindow 传 ui_state_path)
Task 17 (Config streaming 字段)
Task 18 (更新测试 + 全量通过)
```

---

## Task 1: Channel 抽象加 3 个默认 no-op 钩子

**Files:**
- Modify: `desktop_sprite/ai/channel.py:26-33`
- Test: `tests/test_ai_channel.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_ai_channel.py —— 加到文件末尾
from desktop_sprite.ai.channel import AIText, Channel


def test_channel_default_dispatch_stream_methods_are_noop():
    """基类三个钩子默认 no-op；不抛错、不写任何状态。"""
    class _Empty(Channel):
        def dispatch(self, message: AIText) -> None:
            pass

    ch = _Empty(name="x")
    ch.dispatch_stream_start("s1", "uc1")
    ch.dispatch_stream_delta("s1", "hi", "uc1")
    ch.dispatch_stream_end("s1", "hi", "ai", "uc1")
    # 不抛错即过


def test_channel_subclass_can_override_only_delta():
    class _Partial(Channel):
        def __init__(self):
            super().__init__(name="p")
            self.deltas: list[str] = []
        def dispatch(self, message: AIText) -> None:
            pass
        def dispatch_stream_delta(self, stream_id, delta, use_case_id):
            self.deltas.append(delta)

    p = _Partial()
    p.dispatch_stream_start("s", "u")
    p.dispatch_stream_delta("s", "a", "u")
    p.dispatch_stream_delta("s", "b", "u")
    p.dispatch_stream_end("s", "ab", "ai", "u")
    assert p.deltas == ["a", "b"]
```

- [ ] **Step 2: 跑测试，期望失败**

Run:
```bash
pytest tests/test_ai_channel.py::test_channel_default_dispatch_stream_methods_are_noop -v
```
Expected: `AttributeError: 'Empty' object has no attribute 'dispatch_stream_start'`

- [ ] **Step 3: 实现**

修改 `desktop_sprite/ai/channel.py`，把 `Channel` 改成：

```python
# desktop_sprite/ai/channel.py
"""Channel 抽象与 AIText 数据对象。

Channel 是 LLM 文案的"呈现端"抽象；Orchestrator 不关心每个 channel
长啥样，只调 `dispatch(AIText)`（一次性）或
`dispatch_stream_start/delta/end`（流式）。子类必须实现 `dispatch`；
3 个流式钩子默认 no-op，按需重写。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AIText:
    """Orchestrator → Channel 的不可变数据单元。

    `source` 区分 `ai`（provider 正常返回）和 `fallback`（provider 失败
    走 use_case 的 fallback_text）。
    """

    text: str
    source: str  # "ai" / "fallback"
    use_case_id: str
    timestamp: float


class Channel(ABC):
    """呈现端抽象。所有 dispatch* 方法必须在主线程被调。"""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def dispatch(self, message: AIText) -> None:
        ...

    # 流式钩子（默认 no-op；Channel 选择性重写）

    def dispatch_stream_start(self, stream_id: str, use_case_id: str) -> None:
        pass

    def dispatch_stream_delta(
        self, stream_id: str, delta: str, use_case_id: str,
    ) -> None:
        pass

    def dispatch_stream_end(
        self, stream_id: str, full_text: str, source: str, use_case_id: str,
    ) -> None:
        pass
```

- [ ] **Step 4: 跑测试，期望通过**

Run:
```bash
pytest tests/test_ai_channel.py -v
```
Expected: 全部通过（原有 4 + 新增 2 = 6 passed）

- [ ] **Step 5: 跑全量 ai 测试，确认没破坏其它测试**

Run:
```bash
pytest tests/test_ai_channel.py tests/test_ai_channels.py tests/test_ai_orchestrator.py -v
```
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add desktop_sprite/ai/channel.py tests/test_ai_channel.py
git commit -m "feat(ai): Channel 抽象加 3 个默认 no-op dispatch_stream_* 钩子"
```

---

## Task 2: AIProvider 抽象加 generate_stream

**Files:**
- Modify: `desktop_sprite/ai/provider.py:46-62`
- Test: `tests/test_ai_provider.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_ai_provider.py —— 加到文件末尾
import pytest
from desktop_sprite.ai.provider import AIProvider, ProviderError


def test_abstract_provider_must_implement_generate_stream():
    """未实现 generate_stream 不能实例化。"""
    with pytest.raises(TypeError):
        AIProvider()  # 触发 ABC 检查
```

- [ ] **Step 2: 跑测试，期望失败**

Run:
```bash
pytest tests/test_ai_provider.py::test_abstract_provider_must_implement_generate_stream -v
```
Expected: `TypeError`（旧版已存在，但断言信息是 "Can't instantiate abstract class" 而非 "generate_stream" 缺失）

- [ ] **Step 3: 修改 AIProvider 抽象**

`desktop_sprite/ai/provider.py`，把 `AIProvider` 改成：

```python
# desktop_sprite/ai/provider.py
class AIProvider(ABC):
    """LLM 调用抽象。**同步阻塞**——必须被 worker 线程调用。"""

    @abstractmethod
    def generate(
        self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0,
    ) -> str:
        ...

    @abstractmethod
    def generate_stream(
        self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0,
    ):
        """返回 Iterator[str]，每段是 SSE delta 文本。必须被 worker 线程调用。"""
        ...

    @abstractmethod
    def ping(self, *, timeout: float = 5.0) -> float:
        """无 token 消耗的连通性探针。

        命中 `GET {base_url}/models`（OpenAI 兼容标准）：不调 LLM，只列
        元数据，**不消耗 token**。同时验证 base_url 可达、api_key 有效。

        返回：响应往返延迟（ms，浮点）。失败时抛 ProviderError 子类。
        """
```

- [ ] **Step 4: 跑测试，期望通过**

Run:
```bash
pytest tests/test_ai_provider.py -v
```
Expected: 全部通过（**注意**：旧的 `DisabledProvider` 和 `OpenAIProvider` 也得跟着加 `generate_stream`，否则抽象实例化会失败——这步和 Step 5 一起处理）

- [ ] **Step 5: 给现有 `DisabledProvider` / `OpenAIProvider` 加占位 `generate_stream`**

```python
# desktop_sprite/ai/provider.py —— 加在 DisabledProvider 类里
def generate_stream(
    self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0,
):
    raise ProviderDisabled("AI is disabled in config")
    yield  # 让它成为 generator（不会被执行）


# OpenAIProvider 类里也加：
def generate_stream(
    self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0,
):
    raise NotImplementedError("to be implemented in Task 4")
    yield
```

- [ ] **Step 6: 跑测试，期望通过**

Run:
```bash
pytest tests/test_ai_provider.py -v
```
Expected: 全部通过

- [ ] **Step 7: 提交**

```bash
git add desktop_sprite/ai/provider.py tests/test_ai_provider.py
git commit -m "feat(ai): AIProvider 抽象加 generate_stream"
```

---

## Task 3: DisabledProvider 显式测 generate_stream 抛 ProviderDisabled

**Files:**
- Test: `tests/test_ai_provider.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_ai_provider.py —— 加到文件末尾
from desktop_sprite.ai.provider import DisabledProvider, ProviderDisabled


def test_disabled_provider_stream_raises_provider_disabled():
    p = DisabledProvider()
    with pytest.raises(ProviderDisabled):
        # generator 第一次 next() 时抛
        next(p.generate_stream("s", "u"))
```

- [ ] **Step 2: 跑测试，期望通过**（Task 2 已实现）

Run:
```bash
pytest tests/test_ai_provider.py::test_disabled_provider_stream_raises_provider_disabled -v
```
Expected: PASS

- [ ] **Step 3: 提交**（无功能改动，只是加测试）

```bash
git add tests/test_ai_provider.py
git commit -m "test(ai): DisabledProvider.generate_stream 抛 ProviderDisabled"
```

---

## Task 4: OpenAIProvider 实现 generate_stream（SSE 解析）

**Files:**
- Modify: `desktop_sprite/ai/provider.py:74-149`
- Test: `tests/test_ai_provider.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_ai_provider.py —— 加到文件末尾
import json
import pytest
from desktop_sprite.ai.provider import OpenAIProvider


class _FakeStreamChunk:
    """httpx 的 stream chunk 替身；iter_lines() 期望的是字节/str。"""
    def __init__(self, text: str):
        self.text = text

    def iter_lines(self):
        for line in self.text.split("\n"):
            yield line


class _FakeStreamContext:
    def __init__(self, chunks: list[str], status_code: int = 200):
        self._chunks = chunks
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send(self, request):
        # 模拟 httpx.stream 进入时发送请求，返回 response-like
        return _FakeResponse(self.status_code, self._chunks)


class _FakeResponse:
    def __init__(self, status_code, chunks):
        self.status_code = status_code
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self):
        for c in self._chunks:
            for line in c.split("\n"):
                yield line


class _FakeHttpxStream:
    def __init__(self, chunks, status_code=200):
        self._chunks = chunks
        self._status = status_code
        self.calls: list[dict] = []

    def stream(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append({
            "method": method, "url": url, "json": json,
            "headers": headers, "timeout": timeout,
        })
        return _FakeResponse(self._status, self._chunks)


def _patch_stream(monkeypatch, chunks, status_code=200):
    fake = _FakeHttpxStream(chunks, status_code)
    import desktop_sprite.ai.provider as provider_mod
    monkeypatch.setattr(provider_mod, "httpx", fake)
    return fake


def test_openai_provider_stream_yields_deltas(monkeypatch):
    sse = (
        'data: {"choices":[{"delta":{"content":"你"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'
        'data: [DONE]\n\n'
    )
    _patch_stream(monkeypatch, [sse])
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    deltas = list(p.generate_stream("sys", "usr"))
    assert deltas == ["你", "好"]


def test_openai_provider_stream_401_raises_auth_error(monkeypatch):
    sse = "data: [DONE]\n\n"
    _patch_stream(monkeypatch, [sse], status_code=401)
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    from desktop_sprite.ai.provider import AuthError
    with pytest.raises(AuthError):
        list(p.generate_stream("sys", "usr"))


def test_openai_provider_stream_sends_stream_flag(monkeypatch):
    sse = "data: [DONE]\n\n"
    fake = _patch_stream(monkeypatch, [sse])
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    list(p.generate_stream("sys", "usr"))
    body = fake.calls[0]["json"]
    assert body["stream"] is True
    assert body["model"] == "m"
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
```

- [ ] **Step 2: 跑测试，期望失败**

Run:
```bash
pytest tests/test_ai_provider.py::test_openai_provider_stream_yields_deltas -v
```
Expected: `NotImplementedError: to be implemented in Task 4`

- [ ] **Step 3: 实现 OpenAIProvider.generate_stream**

替换 `desktop_sprite/ai/provider.py` 里 `OpenAIProvider.generate` 上方的 `_FakeResponse` 等无关类（这些是测试用的，不动）。在 `OpenAIProvider` 类里把 `generate_stream` 实现替换占位：

```python
# desktop_sprite/ai/provider.py —— OpenAIProvider 类内
def generate_stream(
    self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0,
):
    """SSE 流式生成；yield 每一段 delta 文本。

    用 httpx.stream() 走 HTTP chunked + SSE 协议。请求体加 `stream=True`。
    终止：服务端发 `data: [DONE]` 行（OpenAI 约定）。
    错误：HTTP 状态码 >= 400 抛对应 ProviderError（与 generate 行为一致）。
    """
    url = f"{self.base_url}/chat/completions"
    body = {
        "model": self.model,
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {self.api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.stream(
            "POST", url, json=body, headers=headers, timeout=timeout,
        ) as response:
            if response.status_code in (401, 403):
                raise AuthError(f"auth failed: {response.status_code}")
            if response.status_code == 429:
                raise RateLimitError("rate limited")
            if response.status_code == 400:
                raise BadRequestError(f"bad request: {response.status_code}")
            if response.status_code >= 500:
                raise NetworkError(f"server error: {response.status_code}")
            if response.status_code >= 400:
                raise NetworkError(f"http error: {response.status_code}")

            for line in response.iter_lines():
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    return
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                try:
                    delta = data["choices"][0]["delta"].get("content") or ""
                except (KeyError, IndexError, TypeError):
                    continue
                if delta:
                    yield delta
    except httpx.TimeoutException as exc:
        raise TimeoutError(str(exc)) from exc
    except Exception as exc:
        # httpx 在 stream 期间的网络错误
        if isinstance(exc, ProviderError):
            raise
        raise NetworkError(str(exc)) from exc
```

- [ ] **Step 4: 跑测试，期望通过**

Run:
```bash
pytest tests/test_ai_provider.py -v
```
Expected: 全部通过（旧的 14 + 新增 3 = 17 passed）

- [ ] **Step 5: 提交**

```bash
git add desktop_sprite/ai/provider.py tests/test_ai_provider.py
git commit -m "feat(ai): OpenAIProvider 实现 SSE 流式 generate_stream"
```

---

## Task 5: Orchestrator 加流式 dispatch 路径

**Files:**
- Modify: `desktop_sprite/ai/orchestrator.py`
- Test: `tests/test_ai_orchestrator.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_ai_orchestrator.py —— 加到文件末尾
import pytest
from desktop_sprite.ai.channel import AIText, Channel
from desktop_sprite.ai.orchestrator import AIOrchestrator
from desktop_sprite.ai.provider import AIProvider
from desktop_sprite.ai.use_case import UseCase, UseCaseRegistry
from tests.ai_fakes import FakeProvider, RecordingChannel, TEST_PROBE


class _ChunkedProvider(FakeProvider):
    """FakeProvider 子类，generate_stream 返回预置 chunks。"""
    def __init__(self, stream_chunks: list[str], ping_latency_ms=12.0):
        super().__init__(responses=[], ping_latency_ms=ping_latency_ms)
        self._stream_chunks = stream_chunks
        self.stream_calls: list[dict] = []

    def generate_stream(self, system, user, *, timeout=30.0):
        self.stream_calls.append({"system": system, "user": user})
        for c in self._stream_chunks:
            yield c


class _StreamRecordingChannel(Channel):
    def __init__(self, name: str = "stream_test") -> None:
        super().__init__(name=name)
        self.starts: list[str] = []
        self.deltas: list[tuple[str, str]] = []  # (stream_id, delta)
        self.ends: list[tuple[str, str, str, str]] = []  # (stream_id, full, source, uc)

    def dispatch(self, message: AIText) -> None:
        pass

    def dispatch_stream_start(self, stream_id, use_case_id):
        self.starts.append(stream_id)

    def dispatch_stream_delta(self, stream_id, delta, use_case_id):
        self.deltas.append((stream_id, delta))

    def dispatch_stream_end(self, stream_id, full_text, source, use_case_id):
        self.ends.append((stream_id, full_text, source, use_case_id))


def _make_streaming_orch(provider, channel_name="stream_test"):
    bus_publish_log = []
    registry = UseCaseRegistry()
    registry.register(TEST_PROBE)
    ch = _StreamRecordingChannel(name=channel_name)
    orch = AIOrchestrator(
        provider=provider,
        persona=__import__("desktop_sprite.ai.persona", fromlist=["Persona"]).Persona(
            name="x", system_prompt="sys",
        ),
        use_cases=registry,
        channels=[ch],
        max_inflight=1,
        throttle_overrides={"test.probe": 0},
    )
    return orch, ch


def test_streaming_dispatch_fans_out_deltas_to_channels(qtbot):
    provider = _ChunkedProvider(["你", "好", "！"])
    orch, ch = _make_streaming_orch(provider)
    orch.start()
    orch.trigger_test(user_hint="hi")
    qtbot.waitUntil(lambda: len(ch.ends) == 1, timeout=2000)
    assert ch.starts == [ch.ends[0][0]]  # start 与 end 用同一 stream_id
    assert ch.deltas == [(ch.ends[0][0], "你"), (ch.ends[0][0], "好"), (ch.ends[0][0], "！")]
    assert ch.ends[0][1] == "你好！"
    assert ch.ends[0][2] == "ai"


def test_streaming_midstream_error_falls_back(qtbot):
    """generate_stream 抛异常 → 走 fallback_text 一次性发。"""
    from desktop_sprite.ai.provider import NetworkError

    class _BoomProvider(_ChunkedProvider):
        def generate_stream(self, system, user, *, timeout=30.0):
            raise NetworkError("net down")
            yield  # never

    provider = _BoomProvider([])
    orch, ch = _make_streaming_orch(provider)
    # TEST_PROBE.fallback_text = "(fallback)"
    orch.start()
    orch.trigger_test(user_hint="hi")
    # 不应 throw；dispatch(AIText) 走 fallback
    qtbot.waitUntil(lambda: len(ch.deltas) == 0, timeout=500)
    # 验证 panel/channel 收到 fallback
    # （上面 ch.deltas 应为空；fallback 走 dispatch 路径不进 ch.deltas）
    # 进一步断言：ch 没收到任何 stream 事件
    assert ch.starts == []
    assert ch.ends == []


def test_streaming_dispatch_emits_end_event(qtbot):
    provider = _ChunkedProvider(["x"])
    orch, ch = _make_streaming_orch(provider)
    orch.start()
    orch.trigger_test(user_hint="hi")
    qtbot.waitUntil(lambda: len(ch.ends) == 1, timeout=2000)
    assert ch.ends[0][3] == "test.probe"  # use_case_id
```

- [ ] **Step 2: 跑测试，期望失败**

Run:
```bash
pytest tests/test_ai_orchestrator.py::test_streaming_dispatch_fans_out_deltas_to_channels -v
```
Expected: `_ChunkedProvider` 报错 `Can't instantiate abstract class`（因为 `generate_stream` 在基类里没实现），或 `AttributeError`

- [ ] **Step 3: 给 FakeProvider 加 generate_stream（基类）**

修改 `tests/ai_fakes.py`：

```python
# tests/ai_fakes.py —— FakeProvider 类内
def generate_stream(self, system_prompt, user_prompt, *, timeout=30.0):
    """FakeProvider 默认实现：把每个 response 拆成单字符 chunks yield。"""
    if not self._responses_iter:
        # 行为对齐 generate：从 responses 队列取下一个
        pass
    raise NotImplementedError(
        "FakeProvider.generate_stream 默认未实现；"
        "请在 tests 里继承并 override（如 _ChunkedProvider）"
    )
    yield
```

- [ ] **Step 4: 实现 Orchestrator 流式路径**

修改 `desktop_sprite/ai/orchestrator.py`：

```python
# desktop_sprite/ai/orchestrator.py —— 加在 _PingWorker 类之后

class _StreamWorker(QRunnable):
    """调 provider.generate_stream()，每段 delta 通过 Signal 投回主线程。

    错误处理：
    - 流开始前异常（鉴权 / 超时 / provider 抛）→ emit("error", exc)
    - 流中异常 → emit("error", exc)；已 yield 的 delta 不重发
    - 流正常结束 → emit("end", (full_text, "ai"))
    """

    def __init__(self, orch_ref, use_case_id: str, system: str, user: str):
        super().__init__()
        self._orch_ref = orch_ref
        self._use_case_id = use_case_id
        self._system = system
        self._user = user
        import uuid as _uuid
        self._stream_id = str(_uuid.uuid4())

    def submit_to(self, pool: QThreadPool) -> None:
        pool.start(self)

    def run(self) -> None:
        orch = self._orch_ref()
        if orch is None:
            return
        # emit start
        orch._stream_event.emit(self._stream_id, self._use_case_id, "start", None)
        accumulated: list[str] = []
        try:
            for delta in orch._provider.generate_stream(
                self._system, self._user, timeout=orch._request_timeout_s,
            ):
                accumulated.append(delta)
                orch._stream_event.emit(
                    self._stream_id, self._use_case_id, "delta", delta,
                )
        except Exception as exc:  # noqa: BLE001
            orch._stream_event.emit(
                self._stream_id, self._use_case_id, "error", exc,
            )
            return
        full_text = "".join(accumulated)
        orch._stream_event.emit(
            self._stream_id, self._use_case_id, "end", (full_text, "ai"),
        )
```

然后在 `AIOrchestrator` 类里：

```python
# desktop_sprite/ai/orchestrator.py —— AIOrchestrator 类内
_stream_event = Signal(str, str, str, object)  # (stream_id, use_case_id, kind, payload)

def __init__(self, ...):  # 不变
    ...
    self._stream_event.connect(self._on_stream_event, Qt.QueuedConnection)

@Slot(str, str, str, object)
def _on_stream_event(self, stream_id, use_case_id, kind, payload) -> None:
    if kind == "start":
        for ch in self._channels:
            ch.dispatch_stream_start(stream_id, use_case_id)
    elif kind == "delta":
        for ch in self._channels:
            ch.dispatch_stream_delta(stream_id, payload, use_case_id)
    elif kind == "end":
        full_text, source = payload
        for ch in self._channels:
            ch.dispatch_stream_end(stream_id, full_text, source, use_case_id)
    elif kind == "error":
        uc = self._use_cases.get(use_case_id)
        if uc is not None:
            self._fallback_or_skip(uc, f"stream err={type(payload).__name__}")
```

把 `_dispatch_use_case` 改为默认走流式路径（保留旧的 fallback 行为）：

```python
# desktop_sprite/ai/orchestrator.py —— _dispatch_use_case 方法
def _dispatch_use_case(self, uc: UseCase, payload) -> None:
    now = time.monotonic()
    if now < self._circuit_open_until:
        self._fallback_or_skip(uc, "circuit open")
        return
    throttle_ms = self._throttle_overrides.get(uc.use_case_id, uc.throttle_ms)
    last = self._last_fire_ts.get(uc.use_case_id, 0.0)
    if (now - last) * 1000 < throttle_ms:
        return
    self._last_fire_ts[uc.use_case_id] = now

    try:
        user = uc.prompt_template.format(persona_name=self._persona.name, **payload)
    except KeyError:
        user = uc.prompt_template
    system = self._persona.system_prompt

    # v3: 默认走流式路径（DisabledProvider 在 stream 第一段就 raise → 走 fallback）
    worker = _StreamWorker(
        weakref.ref(self), uc.use_case_id, system, user,
    )
    self._pool.start(worker)
```

- [ ] **Step 5: 跑新测试，期望通过**

Run:
```bash
pytest tests/test_ai_orchestrator.py -v
```
Expected: 旧测试可能因 `_dispatch_use_case` 改流式而失败（旧 FakeProvider 无 stream 实现）——先看是否 break

如果旧测试 break：在 `tests/ai_fakes.py` 给 `FakeProvider` 加上"自动把 response 切成单字符"的 `generate_stream`：

```python
# tests/ai_fakes.py —— FakeProvider.generate_stream
def generate_stream(self, system_prompt, user_prompt, *, timeout=30.0):
    """默认：把队首 response 切成单字符 chunks yield。"""
    if not self._responses:
        raise RuntimeError("no more fake responses for stream")
    text = self._responses.pop(0)
    if isinstance(text, Exception):
        raise text
    for ch in text:
        yield ch
```

- [ ] **Step 6: 跑全量 ai 测试，期望通过**

Run:
```bash
pytest tests/test_ai_orchestrator.py tests/test_ai_channels.py tests/test_ai_panel_widget.py -v
```
Expected: 全部通过

- [ ] **Step 7: 提交**

```bash
git add desktop_sprite/ai/orchestrator.py tests/ai_fakes.py tests/test_ai_orchestrator.py
git commit -m "feat(ai): Orchestrator 加 _StreamWorker + 流式 dispatch 路径"
```

---

## Task 6: ChatPanelChannel 重写 3 个 dispatch_stream_* 方法

**Files:**
- Modify: `desktop_sprite/ai/channels/chat_panel.py`
- Test: `tests/test_ai_channels.py`

注意：本 Task 写测试时调 `panel.append_stream_*` 方法——这些方法在 Task 12 才实现。先在 `ChatPanelChannel` 里**写桩**（直接调不存在的 panel 方法，测试用 `_FakePanel` 替身），Task 12 再做真 panel。

- [ ] **Step 1: 写测试**

```python
# tests/test_ai_channels.py —— 加到文件末尾
from desktop_sprite.ai.channels.chat_panel import ChatPanelChannel
from desktop_sprite.ai.channel import AIText


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
```

- [ ] **Step 2: 跑测试，期望失败**

Run:
```bash
pytest tests/test_ai_channels.py::test_chat_panel_channel_dispatches_stream_to_panel -v
```
Expected: `AttributeError: 'ChatPanelChannel' object has no attribute 'dispatch_stream_start'`

- [ ] **Step 3: 实现 ChatPanelChannel**

替换 `desktop_sprite/ai/channels/chat_panel.py`：

```python
"""ChatPanelChannel——把 AIText 追加到 AIPanelWidget。

panel 由外部 lazy 构造（主窗首次打开时才建），所以 channel 持有一个
`Callable[[], AIPanelWidget | None]` provider，dispatch 时取一下。
panel 未开 → no-op。
"""
from __future__ import annotations

from typing import Callable

from desktop_sprite.ai.channel import AIText, Channel


class ChatPanelChannel(Channel):
    def __init__(self, panel_provider: Callable[[], "object | None"]) -> None:
        super().__init__(name="chat_panel")
        self._panel_provider = panel_provider

    def dispatch(self, message: AIText) -> None:
        panel = self._panel_provider()
        if panel is None:
            return
        panel.append_history(message)

    def dispatch_stream_start(self, stream_id: str, use_case_id: str) -> None:
        panel = self._panel_provider()
        if panel is None:
            return
        panel.append_stream_start(stream_id, use_case_id)

    def dispatch_stream_delta(
        self, stream_id: str, delta: str, use_case_id: str,
    ) -> None:
        panel = self._panel_provider()
        if panel is None:
            return
        panel.append_stream_delta(stream_id, delta, use_case_id)

    def dispatch_stream_end(
        self, stream_id: str, full_text: str, source: str, use_case_id: str,
    ) -> None:
        panel = self._panel_provider()
        if panel is None:
            return
        panel.append_stream_end(stream_id, full_text, source, use_case_id)
```

- [ ] **Step 4: 跑测试，期望通过**

Run:
```bash
pytest tests/test_ai_channels.py -v
```
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add desktop_sprite/ai/channels/chat_panel.py tests/test_ai_channels.py
git commit -m "feat(ai): ChatPanelChannel 重写 3 个 dispatch_stream_* 方法"
```

---

## Task 7: BubbleOverlayWindow 加 append_text

**Files:**
- Modify: `desktop_sprite/ui/bubble_overlay.py`
- Test: `tests/test_ai_bubble_overlay.py`

- [ ] **Step 1: 读 bubble_overlay.py 了解当前 API**

先用 Read 工具看 `desktop_sprite/ui/bubble_overlay.py` 的现有结构（找 `_label` 字段、`show_message` 方法、hide timer）。

- [ ] **Step 2: 写测试**

```python
# tests/test_ai_bubble_overlay.py —— 加到文件末尾
import pytest
from desktop_sprite.ui.bubble_overlay import BubbleOverlayWindow


@pytest.fixture
def bubble(qtbot):
    b = BubbleOverlayWindow()
    qtbot.addWidget(b)
    return b


def test_bubble_append_text_extends_label(bubble):
    bubble.show_message("你好")
    bubble.append_text("世界")
    assert bubble._label.text() == "你好世界"


def test_bubble_append_text_resets_hide_timer(bubble, qtbot):
    """append_text 重置 hide timer，气泡不会中途消失。"""
    bubble.show_message("hi")
    # 直接验证 _hide_timer 是否重置（不依赖真实时间）
    assert bubble._hide_timer.isActive()
    bubble.append_text(".")
    # 重新 active
    assert bubble._hide_timer.isActive()


def test_bubble_show_message_with_empty_text(bubble):
    """流开始时 show_message("") 创建空气泡；后续 append_text 累加。"""
    bubble.show_message("")
    assert bubble._label.text() == ""
    bubble.append_text("流")
    bubble.append_text("式")
    assert bubble._label.text() == "流式"
```

- [ ] **Step 3: 跑测试，期望失败**

Run:
```bash
pytest tests/test_ai_bubble_overlay.py::test_bubble_append_text_extends_label -v
```
Expected: `AttributeError: 'BubbleOverlayWindow' object has no attribute 'append_text'`

- [ ] **Step 4: 实现 append_text**

在 `BubbleOverlayWindow` 类内加方法：

```python
# desktop_sprite/ui/bubble_overlay.py —— BubbleOverlayWindow 类内
def append_text(self, delta: str) -> None:
    """流式增量：拼到 _label 末尾 + 重置 hide timer + adjustSize 触发布局。"""
    self._label.setText(self._label.text() + delta)
    self._label.adjustSize()
    self._reset_hide_timer()
```

确保 `_reset_hide_timer` 是已存在的方法（看 bubble_overlay.py 现状），不是的话改为：

```python
def _reset_hide_timer(self) -> None:
    if hasattr(self, "_hide_timer") and self._hide_timer is not None:
        self._hide_timer.stop()
        self._hide_timer.start()
```

- [ ] **Step 5: 跑测试，期望通过**

Run:
```bash
pytest tests/test_ai_bubble_overlay.py -v
```
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add desktop_sprite/ui/bubble_overlay.py tests/test_ai_bubble_overlay.py
git commit -m "feat(ui): BubbleOverlayWindow 加 append_text 流式增量接口"
```

---

## Task 8: PetBubbleChannel 重写 3 个 dispatch_stream_* 方法

**Files:**
- Modify: `desktop_sprite/ai/channels/pet_bubble.py`
- Test: `tests/test_ai_channels.py`

- [ ] **Step 1: 读 pet_bubble.py 了解当前 API**

用 Read 工具看 `desktop_sprite/ai/channels/pet_bubble.py` 的 `dispatch` 实现（它怎么调 bubble、bubble 字段名）。

- [ ] **Step 2: 写测试**

```python
# tests/test_ai_channels.py —— 加到文件末尾
from desktop_sprite.ai.channels.pet_bubble import PetBubbleChannel


class _FakeBubble:
    def __init__(self):
        self.messages: list[str] = []
        self.appends: list[str] = []
    def show_message(self, text: str) -> None:
        self.messages.append(text)
    def append_text(self, delta: str) -> None:
        self.appends.append(delta)


def test_pet_bubble_channel_dispatches_stream_to_bubble():
    """用 monkeypatch 把 BubbleOverlayWindow 替成 _FakeBubble 工厂。"""
    import desktop_sprite.ai.channels.pet_bubble as mod
    mod.BubbleOverlayWindow = _FakeBubble  # 类替身
    bubble = _FakeBubble()
    ch = PetBubbleChannel(bubble_provider=lambda: bubble)
    ch.dispatch_stream_start("s1", "uc1")
    ch.dispatch_stream_delta("s1", "你", "uc1")
    ch.dispatch_stream_delta("s1", "好", "uc1")
    ch.dispatch_stream_end("s1", "你好", "ai", "uc1")
    assert bubble.messages == [""]  # start → show_message("")
    assert bubble.appends == ["你", "好"]


def test_pet_bubble_channel_stream_noop_when_bubble_none():
    ch = PetBubbleChannel(bubble_provider=lambda: None)
    ch.dispatch_stream_start("s", "u")
    ch.dispatch_stream_delta("s", "x", "u")
    ch.dispatch_stream_end("s", "x", "ai", "u")
```

- [ ] **Step 3: 跑测试，期望失败**

Run:
```bash
pytest tests/test_ai_channels.py::test_pet_bubble_channel_dispatches_stream_to_bubble -v
```
Expected: 旧 PetBubbleChannel 无 `dispatch_stream_*` 方法

- [ ] **Step 4: 实现 PetBubbleChannel**

替换 `desktop_sprite/ai/channels/pet_bubble.py`：

```python
"""PetBubbleChannel——把 AIText 推到桌宠头顶 BubbleOverlayWindow。

bubble 由外部构造（桌宠启动时建），channel 持 callable lazy 拿。
"""
from __future__ import annotations

from typing import Callable

from desktop_sprite.ai.channel import AIText, Channel


class PetBubbleChannel(Channel):
    def __init__(self, bubble_provider: Callable[[], "object | None"]) -> None:
        super().__init__(name="pet_bubble")
        self._bubble_provider = bubble_provider

    def dispatch(self, message: AIText) -> None:
        bubble = self._bubble_provider()
        if bubble is None:
            return
        bubble.show_message(message.text)

    def dispatch_stream_start(self, stream_id: str, use_case_id: str) -> None:
        bubble = self._bubble_provider()
        if bubble is None:
            return
        bubble.show_message("")

    def dispatch_stream_delta(
        self, stream_id: str, delta: str, use_case_id: str,
    ) -> None:
        bubble = self._bubble_provider()
        if bubble is None:
            return
        bubble.append_text(delta)

    def dispatch_stream_end(
        self, stream_id: str, full_text: str, source: str, use_case_id: str,
    ) -> None:
        # 不主动关；BubbleOverlayWindow 自己有 hide timer 流期间被 append_text
        # 不断 reset；end 后没有新 delta，timer 走完自动隐藏。
        pass
```

- [ ] **Step 5: 跑测试，期望通过**

Run:
```bash
pytest tests/test_ai_channels.py -v
```
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add desktop_sprite/ai/channels/pet_bubble.py tests/test_ai_channels.py
git commit -m "feat(ai): PetBubbleChannel 重写 3 个 dispatch_stream_* 方法"
```

---

## Task 9: OsNotificationChannel 重写 dispatch_stream_end

**Files:**
- Modify: `desktop_sprite/ai/channels/os_notification.py`
- Test: `tests/test_ai_channels.py`

- [ ] **Step 1: 读 os_notification.py 了解 dispatch 实现**

用 Read 工具看 `desktop_sprite/ai/channels/os_notification.py` 现有 `dispatch` 方法（tray 调用方式）。

- [ ] **Step 2: 写测试**

```python
# tests/test_ai_channels.py —— 加到文件末尾
import time
from desktop_sprite.ai.channel import AIText
from desktop_sprite.ai.channels.os_notification import OsNotificationChannel


class _FakeTray:
    def __init__(self):
        self.notified: list[tuple[str, str]] = []
    def showMessage(self, title: str, msg: str, icon: int = 0, msecs: int = 10000) -> None:
        self.notified.append((title, msg))


def test_os_notification_channel_stream_start_and_delta_are_noop():
    """start / delta 走基类默认 no-op；end 才真正弹通知。"""
    tray = _FakeTray()
    ch = OsNotificationChannel(tray_provider=lambda: tray)
    ch.dispatch_stream_start("s", "u")
    ch.dispatch_stream_delta("s", "a", "u")
    ch.dispatch_stream_delta("s", "b", "u")
    assert tray.notified == []  # 流期间没弹


def test_os_notification_channel_stream_end_dispatches_full_text():
    tray = _FakeTray()
    ch = OsNotificationChannel(tray_provider=lambda: tray)
    ch.dispatch_stream_end("s1", "完整文本", "ai", "uc1")
    assert len(tray.notified) == 1
    title, msg = tray.notified[0]
    assert msg == "完整文本"
```

- [ ] **Step 3: 跑测试，期望失败**

Run:
```bash
pytest tests/test_ai_channels.py::test_os_notification_channel_stream_end_dispatches_full_text -v
```
Expected: 旧 OsNotificationChannel `dispatch_stream_end` 是 no-op，不调 tray

- [ ] **Step 4: 实现 OsNotificationChannel 重写 end**

修改 `desktop_sprite/ai/channels/os_notification.py`：

```python
# desktop_sprite/ai/channels/os_notification.py —— OsNotificationChannel 类内加：
def dispatch_stream_end(
    self, stream_id: str, full_text: str, source: str, use_case_id: str,
) -> None:
    """流结束时把完整文本走 dispatch → tray.showMessage。"""
    import time as _time
    self.dispatch(AIText(
        text=full_text, source=source,
        use_case_id=use_case_id, timestamp=_time.time(),
    ))
```

- [ ] **Step 5: 跑测试，期望通过**

Run:
```bash
pytest tests/test_ai_channels.py -v
```
Expected: 全部通过

- [ ] **Step 6: 跑全量测试确认**

Run:
```bash
pytest tests/ -v
```
Expected: 全部通过（除旧的 fab 断言测试，下面 Task 11-15 会改）

- [ ] **Step 7: 提交**

```bash
git add desktop_sprite/ai/channels/os_notification.py tests/test_ai_channels.py
git commit -m "feat(ai): OsNotificationChannel dispatch_stream_end 转 AIText 通知"
```

---

## Task 10: FakeProvider 流式默认实现（让旧测试不 break）

**Files:**
- Modify: `tests/ai_fakes.py`

注意：此 Task 实际已在 Task 5 Step 5 完成（`generate_stream` 默认从队列取单字符 chunks）。验证一下并跑测试。

- [ ] **Step 1: 跑全量 ai 测试，确认无 break**

Run:
```bash
pytest tests/test_ai_orchestrator.py tests/test_ai_panel_widget.py tests/test_ai_end_to_end.py -v
```
Expected: 全部通过（如果 break，看 traceback 调 FakeProvider 行为）

- [ ] **Step 2: 如果 break，在 FakeProvider 调整 generate_stream 默认实现**

已在 Task 5 Step 5 提供代码。重跑确认通过。

---

## Task 11: AIPanelWidget UI 重构——去 CardWidget + 去 _FabButton + ToggleButton

**Files:**
- Modify: `desktop_sprite/ui/ai_panel.py`
- Test: `tests/test_ai_panel_widget.py`

这是最大改动，分成 5 个子任务（Task 11-15），逐个 TDD。

- [ ] **Step 1: 读 ai_panel.py 现有结构**

用 Read 工具通读 `desktop_sprite/ui/ai_panel.py`，理解：
- `_StatusDot` 类（保留）
- `_FabButton` 类（删除）
- `ChatBubble` 类（保留，Task 13 加 `append_text`）
- `AIPanelWidget.__init__` 构造（重写）
- `_add_bubble` / `_scroll_to_bottom` / `_toggle_input`（改写）

- [ ] **Step 2: 写失败的测试（断言不再有 aiHistoryCard / aiInputCard CardWidget）**

```python
# tests/test_ai_panel_widget.py —— 加到文件末尾
def test_no_card_widget_for_history_or_input(panel):
    p, _, _ = panel
    # v3 不再用 CardWidget 当历史 / 输入容器
    assert p.findChild(QObject, "aiHistoryCard") is None
    assert p.findChild(QObject, "aiInputCard") is None
```

需要 import：`from PySide6.QtCore import QObject`

- [ ] **Step 3: 跑测试，期望失败**

Run:
```bash
pytest tests/test_ai_panel_widget.py::test_no_card_widget_for_history_or_input -v
```
Expected: `findChild` 找到 `aiHistoryCard`（断言失败）

- [ ] **Step 4: 重构 ai_panel.py——替换整个文件**

完整重写 `desktop_sprite/ui/ai_panel.py`：

```python
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
    QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget,
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
_INPUT_EXPANDED_HEIGHT = 160
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
        self._scroll_inner = QWidget(self._scroll)
        self._scroll_inner.setObjectName("chatBubblesInner")
        self._scroll_layout = QVBoxLayout(self._scroll_inner)
        self._scroll_layout.setContentsMargins(4, 4, 4, 4)
        self._scroll_layout.setSpacing(8)
        self._scroll_layout.addStretch(1)
        self._scroll.setWidget(self._scroll_inner)

        # ---- 输入区（QWidget，去 CardWidget；可折叠）----
        self._input_area = QWidget(self)
        self._input_area.setObjectName("aiInputArea")
        self._input_area.setMaximumHeight(0)
        self._input_area.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        input_layout = QVBoxLayout(self._input_area)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        self._input_edit = TextEdit(self._input_area)
        self._input_edit.setObjectName("aiInputEdit")
        self._input_edit.setPlaceholderText("说点什么…")
        self._input_edit.setFixedHeight(72)
        self._input_edit.setVisible(False)  # 收起时不显示
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
        self._input_edit.setVisible(expanded)
        if animate:
            target = _INPUT_EXPANDED_HEIGHT if expanded else 0
            self._animate_input(target)
        else:
            self._input_area.setMaximumHeight(
                _INPUT_EXPANDED_HEIGHT if expanded else 0
            )

    def _on_toggle_changed(self, checked: bool) -> None:
        self._apply_input_expanded(checked, animate=True)
        self._save_input_expanded()

    def _animate_input(self, target: int) -> None:
        ani = QPropertyAnimation(self._input_area, b"maximumHeight", self)
        ani.setDuration(_INPUT_ANIM_MS)
        ani.setStartValue(self._input_area.maximumHeight())
        ani.setEndValue(target)
        ani.setEasingCurve(QEasingCurve.OutCubic)
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
            avatar = AvatarWidget("AI", self._scroll_inner)
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
```

- [ ] **Step 5: 跑测试，看哪些 break**

Run:
```bash
pytest tests/test_ai_panel_widget.py -v
```
Expected: 多数旧测试因 `_FabButton` / `_input_card` 字段不存在而 break。下面 Task 12-15 改测试。

---

## Task 12: 更新 test_ai_panel_widget.py——适配 v3 UI

**Files:**
- Modify: `tests/test_ai_panel_widget.py`

- [ ] **Step 1: 改 fixture 加 ui_state_path**

```python
# tests/test_ai_panel_widget.py 顶部 fixture 区
@pytest.fixture
def panel(qtbot, tmp_path):
    orch = _StubOrchestrator()
    ui_state = tmp_path / "ui_state.json"
    p = AIPanelWidget(
        orchestrator=orch, history_max_lines=50, ui_state_path=ui_state,
    )
    qtbot.addWidget(p)
    p.resize(900, 700)
    return p, orch, ui_state
```

- [ ] **Step 2: 替换所有 `p._fab` 引用为 `p._toggle_btn`**

```python
# 全文替换：
# p._fab.isEnabled()  →  p._toggle_btn.isEnabled()
# p._fab.setEnabled  →  p._toggle_btn.setEnabled
# p._fab.click()  →  p._toggle_btn.click()  (用 checked 翻转更直接)
```

- [ ] **Step 3: 改 `test_fab_click_expands_input` 等**

把 `p._fab.click()` 改为：

```python
p._toggle_btn.click()  # 或 p._toggle_btn.toggle()
qtbot.waitUntil(lambda: p._input_expanded, timeout=500)
```

`test_input_card_starts_collapsed` 改为：

```python
def test_input_starts_collapsed(panel):
    p, _, _ = panel
    assert p.input_visible() is False
    assert p._input_area.maximumHeight() == 0
    assert p._toggle_btn.isChecked() is False
    assert p._toggle_btn.text() == "展开"
```

- [ ] **Step 4: 跑测试，期望大部分通过**

Run:
```bash
pytest tests/test_ai_panel_widget.py -v
```
Expected: 改过的测试通过；旧 fab 相关测试如果没改全会 fail

- [ ] **Step 5: 删 / 改剩余 fab 相关测试**

把 `test_panel_has_fab_button` 整段删掉（v3 没有 FAB）。其它 `test_fab_*` 改 `test_toggle_*`。

- [ ] **Step 6: 跑测试，期望全过**

Run:
```bash
pytest tests/test_ai_panel_widget.py -v
```
Expected: 17 个旧测试改完 + Task 11 加的 `test_no_card_widget_for_history_or_input` = 18 passed

- [ ] **Step 7: 提交**

```bash
git add desktop_sprite/ui/ai_panel.py tests/test_ai_panel_widget.py
git commit -m "refactor(ui): AIPanelWidget v3 UI 重构 + 流式方法 + ui_state 持久化"
```

---

## Task 13: 加 AvatarWidget / ui_state 持久化 / history_max_lines trim / stream 方法的测试

**Files:**
- Test: `tests/test_ai_panel_widget.py`

- [ ] **Step 1: 写 4 个新测试**

```python
# tests/test_ai_panel_widget.py —— 加到文件末尾
from qfluentwidgets import AvatarWidget


def test_chat_bubble_has_avatar_for_ai_role(panel):
    p, _, _ = panel
    p.append_history(AIText(text="hi", source="ai", use_case_id="x", timestamp=0.0))
    avatar = p.findChild(AvatarWidget)
    assert avatar is not None
    assert avatar.text() == "AI"


def test_input_expanded_persists_to_ui_state(panel, qtbot):
    p, _, ui_state = panel
    # 初始 False
    assert p._load_input_expanded() is False
    # 点击展开
    p._toggle_btn.click()
    qtbot.waitUntil(lambda: p._input_expanded, timeout=500)
    # ui_state.json 已写入
    import json
    state = json.loads(ui_state.read_text())
    assert state["ai_panel"]["input_expanded"] is True
    # 重建 panel 验证恢复
    p2, _, _ = panel
    assert p2._load_input_expanded() is True


def test_history_max_lines_trims_head(panel):
    """构造 history_max_lines=3；add 5 条普通气泡，断言只剩 3 条且是后 3 条。"""
    p, _, _ = panel
    p._history_max_lines = 3
    for i in range(5):
        p.append_history(AIText(text=f"msg{i}", source="ai", use_case_id="x", timestamp=float(i)))
    assert p.bubble_count() == 3
    assert [m["text"] for m in p.messages()] == ["msg2", "msg3", "msg4"]


def test_append_stream_start_creates_ai_bubble(panel):
    p, _, _ = panel
    p.append_stream_start("s1", "uc1")
    assert p.bubble_count() == 1
    assert p.messages()[0]["role"] == "ai"
    assert p._stream_bubbles["s1"] is p.messages()[0] and True  # 同一对象


def test_append_stream_delta_appends_to_bubble(panel, qtbot):
    p, _, _ = panel
    p.append_stream_start("s1", "uc1")
    p.append_stream_delta("s1", "你", "uc1")
    p.append_stream_delta("s1", "好", "uc1")
    qtbot.waitUntil(lambda: p.bubble_count() == 1 and p.messages()[0]["text"] == "你好", timeout=500)


def test_append_stream_end_finalizes(panel):
    p, _, _ = panel
    p.append_stream_start("s1", "uc1")
    p.append_stream_delta("s1", "x", "uc1")
    p.append_stream_end("s1", "x", "ai", "uc1")
    assert "s1" not in p._stream_bubbles


def test_input_visible_returns_expanded_state(panel):
    p, _, _ = panel
    assert p.input_visible() is False
    p._input_expanded = True
    assert p.input_visible() is True
```

- [ ] **Step 2: 跑测试，期望通过**

Run:
```bash
pytest tests/test_ai_panel_widget.py -v
```
Expected: 全部通过（~25 tests）

- [ ] **Step 3: 提交**

```bash
git add tests/test_ai_panel_widget.py
git commit -m "test(ui): AIPanelWidget v3 新增 6 个测试（avatar / ui_state / trim / stream）"
```

---

## Task 14: MainWindow 传 ui_state_path 给 AIPanelWidget

**Files:**
- Modify: `desktop_sprite/ui/main_window.py:381-384`

- [ ] **Step 1: 改 _ai_panel_page()**

```python
# desktop_sprite/ui/main_window.py
def _ai_panel_page(self) -> QWidget:
    if self._ai_panel_widget is not None:
        return self._ai_panel_widget
    if self._ai_orchestrator is None:
        self._ai_panel_widget = self._create_placeholder_page(
            "AI 互动",
            "AI orchestrator 未启动。检查 `ai.enabled` / `ai.api_key` 配置后重启应用。",
        )
        return self._ai_panel_widget
    self._ai_panel_widget = AIPanelWidget(
        orchestrator=self._ai_orchestrator,
        history_max_lines=self._ai_history_max_lines,
        ui_state_path=self.ui_state_path,  # ← 新增
    )
    return self._ai_panel_widget
```

- [ ] **Step 2: 跑 main_window 集成测试**

Run:
```bash
pytest tests/test_ai_main_window_integration.py tests/test_main_window.py -v
```
Expected: 全部通过

- [ ] **Step 3: 提交**

```bash
git add desktop_sprite/ui/main_window.py
git commit -m "feat(ui): MainWindow 把 ui_state_path 传给 AIPanelWidget"
```

---

## Task 15: Config 加 streaming 字段

**Files:**
- Modify: `desktop_sprite/utils/config.py`
- Modify: `config/default.json`
- Test: `tests/test_ai_config.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_ai_config.py —— 加到文件末尾
import json
from pathlib import Path


def test_ai_config_default_streaming_is_true(tmp_path):
    from desktop_sprite.utils.config import load_config
    # 临时写一个最小 default config
    default_path = tmp_path / "default.json"
    default_path.write_text(json.dumps({
        "ai": {"enabled": True, "base_url": "https://x/v1", "api_key": "k",
               "model": "m", "streaming": True},
    }), encoding="utf-8")
    cfg = load_config(default_path)
    assert cfg.ai.streaming is True
```

- [ ] **Step 2: 跑测试，期望失败**

Run:
```bash
pytest tests/test_ai_config.py::test_ai_config_default_streaming_is_true -v
```
Expected: `AttributeError: 'AIConfig' object has no attribute 'streaming'`

- [ ] **Step 3: 给 AIConfig 加 streaming 字段**

`desktop_sprite/utils/config.py`，在 `AIConfig` dataclass 加：

```python
@dataclass
class AIConfig:
    ...
    history_max_lines: int = 200
    streaming: bool = True  # ← 新增
```

- [ ] **Step 4: 更新 config/default.json**

找到 `ai` 段，加 `"streaming": true`：

```json
{
  "ai": {
    "enabled": false,
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o-mini",
    "request_timeout_s": 30,
    "max_inflight": 1,
    "throttle_overrides": {},
    "history_max_lines": 200,
    "bubble_visible_seconds": 5,
    "streaming": true
  },
  ...
}
```

- [ ] **Step 5: 跑全量 config 测试**

Run:
```bash
pytest tests/test_ai_config.py tests/test_ai_runtime_wiring.py -v
```
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add desktop_sprite/utils/config.py config/default.json tests/test_ai_config.py
git commit -m "feat(config): AIConfig 加 streaming 字段（默认 true）"
```

---

## Task 16: 全量 pytest + 手动验证

- [ ] **Step 1: 跑全量 pytest**

Run:
```bash
pytest tests/ -v
```
Expected: 全部通过；旧 18 个 panel 测试 + 14 provider 测试 + orchestrator + channels + ... 总计约 80+ tests

- [ ] **Step 2: 跑带 coverage 的全量**

Run:
```bash
pytest tests/ --cov=desktop_sprite.ai --cov=desktop_sprite.ui.ai_panel --cov-report=term-missing
```
Expected: ai 包覆盖率 ≥ 80%

- [ ] **Step 3: 手动验证（可选）**

```bash
# 启动应用
python -m desktop_sprite
# 1. 打开"AI 互动"页
# 2. 看到无 CardWidget 边框
# 3. 点击"展开"→ 输入区滑出 → 关闭应用 → 重启 → 仍展开
# 4. 输入消息点"发送"→ 气泡内容逐字出现（需要 ai.enabled=true + 真实 API）
# 5. 桌宠头顶气泡也逐字出现
```

- [ ] **Step 4: 最终提交（如有 dirty）**

```bash
git status
# 若有未提交：
git add -A
git commit -m "chore: 实施完成全部 task 后的小修"
```

---

## Self-Review

### Spec 覆盖

| Spec 章节 | 对应 Task |
|---|---|
| §3.1 UI 结构 | Task 11 |
| §3.2 关键决定（去 CardWidget / ToggleButton / AvatarWidget / history_max_lines / setTextColor） | Task 11 + 13 |
| §3.3 动画保留 | Task 11（保留 `_animate_input`） |
| §3.4 状态持久化 | Task 12 (`_load_input_expanded` / `_save_input_expanded`) + Task 14 (MainWindow 传参) + Task 13 (测试) |
| §4.1 三层职责 | Task 1 (Channel) + Task 2 (Provider) + Task 5 (Orchestrator) |
| §4.2 信号协议 | Task 5 |
| §4.3 Channel 抽象 | Task 1 |
| §4.4 各 Channel 行为 | Task 6 (ChatPanel) + Task 7-8 (PetBubble) + Task 9 (OsNotification) |
| §4.5 Panel 增量 API | Task 11 + Task 13 (测试) |
| §4.6 PetBubble 端 | Task 7 + Task 8 |
| §5 关键文件改动清单 | 全部 Task 覆盖 |
| §6 数据结构 | Task 2 (`generate_stream` 签名) |
| §7 错误处理 | Task 4 (status code → ProviderError) + Task 5 (worker 异常 → emit error) |
| §8 测试策略 | Task 1-13 各测试 + Task 16 全量 |
| §9 风险点 | Task 4 (SSE 解析) + Task 5 (异常处理) + Task 7 (timer reset) + Task 12 (fixture 改) |
| §11 实施顺序 | Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 11 → 12 → 13 → 14 → 15 → 16 |
| §12 验收标准 | Task 16 |

无遗漏。

### 占位符扫描

- 无 "TBD" / "TODO" / "implement later"
- 无 "add appropriate error handling"（每个 try/except 都给出具体处理）
- 测试代码全部完整
- 类型与签名：`_stream_event` Signal 在 Task 5 引入 + Task 6/7/8/9 一致使用；`append_stream_*` 在 Task 11 panel 端定义 + Task 6 channel 端调用一致

### 类型一致性

- `ChatPanelChannel.append_stream_start(stream_id, use_case_id)` 与 `AIPanelWidget.append_stream_start(stream_id, use_case_id)` 签名一致 ✓
- `BubbleOverlayWindow.append_text(delta)` 在 Task 7 定义，Task 8 `PetBubbleChannel` 调用一致 ✓
- `OpenAIProvider.generate_stream(system, user, *, timeout)` 在 Task 4 定义，Task 5 orchestrator 调用一致 ✓
- `_stream_event = Signal(str, str, str, object)` 在 Task 5 定义，slot `_on_stream_event(stream_id, use_case_id, kind, payload)` 一致 ✓

无类型不一致。
