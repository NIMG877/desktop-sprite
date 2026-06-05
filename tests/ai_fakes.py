"""AI 互动系统测试夹具。

`FakeProvider`：可预设 `responses`（文本或 ProviderError 子类实例），
按顺序弹出；记录所有 `calls`。
`RecordingChannel`：记录所有 `dispatch` 调用的 AIText。
`make_orchestrator(...)`：工厂，返回一个注入好 fakes 的 AIOrchestrator。
"""
from __future__ import annotations

from typing import Any, Iterable

from desktop_sprite.ai.channel import AIText, Channel
from desktop_sprite.ai.event_bus import EventBus
from desktop_sprite.ai.orchestrator import AIOrchestrator
from desktop_sprite.ai.persona import Persona
from desktop_sprite.ai.provider import AIProvider
from desktop_sprite.ai.use_case import UseCase, UseCaseRegistry


class FakeProvider(AIProvider):
    def __init__(
        self,
        responses: Iterable[Any] | None = None,
        ping_latency_ms: float = 12.0,
        ping_error: Exception | None = None,
    ) -> None:
        self._responses = list(responses or ["ok"])
        self._ping_latency = ping_latency_ms
        self._ping_error = ping_error
        self.calls: list[dict] = []
        self.ping_calls: int = 0

    def generate(self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0) -> str:
        self.calls.append({"system": system_prompt, "user": user_prompt, "timeout": timeout})
        if not self._responses:
            raise RuntimeError("FakeProvider: no more responses")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def generate_stream(self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0):
        """默认：把队首 response 切成单字符 chunks yield。

        行为对齐原 `generate()`：缺响应抛 RuntimeError；响应本身是
        Exception 实例时抛（保持测试可注入 NetworkError 等）。
        """
        self.calls.append({"system": system_prompt, "user": user_prompt, "timeout": timeout})
        if not self._responses:
            raise RuntimeError("FakeProvider: no more responses for stream")
        text = self._responses.pop(0)
        if isinstance(text, Exception):
            raise text
        for ch in text:
            yield ch

    def ping(self, *, timeout: float = 5.0) -> float:
        self.ping_calls += 1
        if self._ping_error is not None:
            raise self._ping_error
        return self._ping_latency


class RecordingChannel(Channel):
    """记录所有 dispatch* 调用。"""

    def __init__(self, name: str) -> None:
        super().__init__(name=name)
        # v1: AIText 一次性派发
        self.dispatched: list[AIText] = []
        # v3: 流式事件
        self.stream_starts: list[tuple[str, str]] = []
        self.stream_deltas: list[tuple[str, str, str]] = []
        self.stream_ends: list[tuple[str, str, str, str]] = []

    def dispatch(self, message: AIText) -> None:
        self.dispatched.append(message)

    def dispatch_stream_start(self, stream_id, use_case_id):
        self.stream_starts.append((stream_id, use_case_id))

    def dispatch_stream_delta(self, stream_id, delta, use_case_id):
        self.stream_deltas.append((stream_id, delta, use_case_id))

    def dispatch_stream_end(self, stream_id, full_text, source, use_case_id):
        self.stream_ends.append((stream_id, full_text, source, use_case_id))
        # 兼容旧测试：把 end 事件合成一条 AIText 写入 dispatched
        self.dispatched.append(AIText(
            text=full_text, source=source, use_case_id=use_case_id, timestamp=0.0,
        ))


TEST_PROBE = UseCase(
    use_case_id="test.probe",
    event_topic="ai.test.request",
    prompt_template="hint={user_hint}",
    target_channels=("pet_bubble", "chat_panel", "os_notification"),
    throttle_ms=0,
    fallback_text="(fallback)",
)


def make_orchestrator(
    *,
    provider: AIProvider | None = None,
    persona: Persona | None = None,
    use_cases: UseCaseRegistry | None = None,
    channel_names: tuple[str, ...] = ("pet_bubble", "chat_panel", "os_notification"),
    max_inflight: int = 1,
    request_timeout_s: float = 5.0,
    throttle_overrides: dict[str, int] | None = None,
):
    """构造一个 AIOrchestrator + EventBus + 默认 fakes。

    返回 `(orch, bus, channels, registry, provider)` 元组。
    默认会自动注册 `TEST_PROBE`；如果调用方传入了自定义 `use_cases`，
    则尊重调用方的注册内容（不再自动注册 TEST_PROBE），便于"只关心
    自定义 use_case"的隔离测试。
    """
    bus = EventBus()
    persona = persona or Persona(name="pet", system_prompt="sys", default_fallback="(silent)")
    provider = provider or FakeProvider()
    channels: dict[str, RecordingChannel] = {n: RecordingChannel(n) for n in channel_names}
    channel_objs = [channels[n] for n in channel_names]

    if use_cases is None:
        registry = UseCaseRegistry()
        registry.register(TEST_PROBE)
    else:
        registry = use_cases

    orch = AIOrchestrator(
        provider=provider,
        persona=persona,
        use_cases=registry,
        channels=channel_objs,
        max_inflight=max_inflight,
        request_timeout_s=request_timeout_s,
        throttle_overrides=throttle_overrides or {},
        event_bus=bus,
    )
    return orch, bus, channels, registry, provider
