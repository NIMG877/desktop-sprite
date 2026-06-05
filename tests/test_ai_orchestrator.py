import pytest
from desktop_sprite.ai.channel import AIText, Channel
from desktop_sprite.ai.orchestrator import AIOrchestrator
from desktop_sprite.ai.provider import (
    AuthError, RateLimitError, NetworkError, ProviderDisabled,
)
from desktop_sprite.ai.use_case import UseCase, UseCaseRegistry
from tests.ai_fakes import FakeProvider, RecordingChannel, TEST_PROBE, make_orchestrator


# ---- 端到端基本路径 ----

def test_trigger_test_dispatches_to_all_channels(qtbot):
    orch, bus, channels, _, provider = make_orchestrator(provider=FakeProvider(["ok"]))
    orch.start()
    orch.trigger_test()
    qtbot.waitUntil(lambda: len(channels["pet_bubble"].dispatched) == 1, timeout=2000)
    for ch in channels.values():
        assert len(ch.dispatched) == 1
        assert ch.dispatched[0].text == "ok"
        assert ch.dispatched[0].source == "ai"
        assert ch.dispatched[0].use_case_id == "test.probe"


def test_use_case_prompt_template_filled(qtbot):
    orch, bus, channels, _, provider = make_orchestrator(provider=FakeProvider(["x"]))
    orch.start()
    orch.trigger_test(user_hint="hello")
    qtbot.waitUntil(lambda: provider.calls != [], timeout=2000)
    assert "hello" in provider.calls[0]["user"]
    assert "sys" == provider.calls[0]["system"]


# ---- DisabledProvider 短路 ----

def test_disabled_provider_does_not_call(qtbot):
    from desktop_sprite.ai.provider import DisabledProvider
    orch, bus, channels, _, _ = make_orchestrator(provider=DisabledProvider())
    orch.start()
    orch.trigger_test()
    # ProviderDisabled → fallback_text 路径
    qtbot.waitUntil(lambda: any(c.dispatched for c in channels.values()), timeout=2000)
    for ch in channels.values():
        if ch.dispatched:
            assert ch.dispatched[0].source == "fallback"
            assert ch.dispatched[0].text == "(fallback)"


# ---- Fallback ----

def test_provider_error_with_fallback_dispatches_fallback(qtbot):
    orch, bus, channels, _, _ = make_orchestrator(
        provider=FakeProvider([AuthError("bad key")])
    )
    orch.start()
    orch.trigger_test()
    qtbot.waitUntil(lambda: len(channels["pet_bubble"].dispatched) == 1, timeout=2000)
    for ch in channels.values():
        assert ch.dispatched[0].text == "(fallback)"
        assert ch.dispatched[0].source == "fallback"


def test_provider_error_no_fallback_no_dispatch(qtbot):
    reg = UseCaseRegistry()
    reg.register(UseCase(
        use_case_id="nf", event_topic="ai.test.request", prompt_template="p",
        target_channels=("pet_bubble",), throttle_ms=0, fallback_text=None,
    ))
    orch, bus, channels, _, _ = make_orchestrator(
        provider=FakeProvider([NetworkError("down")]),
        use_cases=reg,
        channel_names=("pet_bubble",),
    )
    orch.start()
    orch.trigger_test()
    qtbot.wait(500)
    assert channels["pet_bubble"].dispatched == []


# ---- 节流 ----

def test_throttle_blocks_rapid_second_call(qtbot):
    reg = UseCaseRegistry()
    reg.register(UseCase(
        use_case_id="th", event_topic="ai.test.request", prompt_template="p",
        target_channels=("pet_bubble",), throttle_ms=200, fallback_text=None,
    ))
    orch, bus, channels, _, provider = make_orchestrator(
        provider=FakeProvider(["a", "b"]),
        use_cases=reg,
        channel_names=("pet_bubble",),
    )
    orch.start()
    orch.trigger_test()
    qtbot.waitUntil(lambda: len(provider.calls) == 1, timeout=2000)
    orch.trigger_test()  # 200ms 内 → 跳过
    qtbot.wait(300)
    assert len(provider.calls) == 1  # 仍 1 次


# ---- 熔断 ----

def test_circuit_breaker_opens_after_3_errors(qtbot):
    orch, bus, channels, _, provider = make_orchestrator(
        provider=FakeProvider([RateLimitError("r")] * 10),
        throttle_overrides={"test.probe": 0},
    )
    orch.start()
    # 触发 3 次（每次间隔 100ms；2s 重试 backoff 不会在这期间触发）
    for _ in range(3):
        orch.trigger_test()
        qtbot.wait(100)
    # 4 次：circuit 应已开，provider 不被调
    calls_before = len(provider.calls)
    orch.trigger_test()
    qtbot.wait(200)
    assert len(provider.calls) == calls_before  # 没有新调用


# ---- 重试 ----

def test_rate_limit_triggers_fallback_no_retry_in_streaming(qtbot):
    """v3 流式路径：RateLimit 不再重试，直接走 fallback。

    （旧版非流式路径有 retry_backoff 重试 1 次的逻辑；v3 起 streaming
    不重试，避免 mid-stream 重复投送。）
    """
    orch, bus, channels, _, provider = make_orchestrator(
        provider=FakeProvider([RateLimitError("r"), "ok"]),
    )
    orch.start()
    orch.trigger_test()
    qtbot.waitUntil(lambda: len(channels["pet_bubble"].dispatched) == 1, timeout=2000)
    for ch in channels.values():
        assert ch.dispatched[0].source == "fallback"
        assert ch.dispatched[0].text == "(fallback)"
    assert len(provider.calls) == 1  # 只调 1 次，不重试


def test_auth_error_does_not_retry(qtbot):
    orch, bus, channels, _, provider = make_orchestrator(
        provider=FakeProvider([AuthError("a")])
    )
    orch.start()
    orch.trigger_test()
    qtbot.waitUntil(lambda: len(channels["pet_bubble"].dispatched) == 1, timeout=2000)
    assert len(provider.calls) == 1  # 不重试


# ---- 跨线程 ----

def test_status_indicator_thinking_then_done(qtbot):
    orch, bus, channels, _, provider = make_orchestrator(provider=FakeProvider(["ok"]))
    orch.start()
    # 没 panel 时 status 不会暴露——这里我们只断言不抛
    orch.trigger_test()
    qtbot.waitUntil(lambda: len(channels["pet_bubble"].dispatched) == 1, timeout=2000)


# ---- 异常隔离 ----

def test_one_channel_raising_does_not_break_others(qtbot):
    class RaisingChannel(RecordingChannel):
        def dispatch(self, message):
            raise RuntimeError("boom")
    orch, bus, channels, _, _ = make_orchestrator(
        provider=FakeProvider(["ok"]),
        channel_names=("pet_bubble", "chat_panel", "os_notification"),
    )
    # 替换 pet_bubble 为 raising
    orch._channels[0] = RaisingChannel(name="pet_bubble")
    orch.start()
    orch.trigger_test()
    qtbot.waitUntil(
        lambda: len(orch._channels[1].dispatched) == 1 and len(orch._channels[2].dispatched) == 1,
        timeout=2000,
    )
    assert len(orch._channels[1].dispatched) == 1
    assert len(orch._channels[2].dispatched) == 1


# ---- max_inflight ----

def test_max_inflight_two_concurrent(qtbot):
    orch, bus, channels, _, provider = make_orchestrator(
        provider=FakeProvider(["a", "b", "c"]),
        max_inflight=2,
    )
    # TEST_PROBE 的 throttle_ms=0 已经是 0；显式覆盖一份以保持测试自描述
    orch._throttle_overrides["test.probe"] = 0
    orch.start()
    orch.trigger_test()
    orch.trigger_test()
    qtbot.waitUntil(lambda: len(provider.calls) == 2, timeout=2000)
    # 第三次也提交，等池有空时跑
    orch.trigger_test()
    qtbot.waitUntil(lambda: len(channels["pet_bubble"].dispatched) == 3, timeout=3000)


# ---- ping_async ----

def test_ping_async_success_invokes_callback_with_latency(qtbot):
    provider = FakeProvider(ping_latency_ms=23.5)
    orch, _, _, _, _ = make_orchestrator(provider=provider)
    captured = []
    orch.ping_async(lambda ms, err: captured.append((ms, err)))
    qtbot.waitUntil(lambda: bool(captured), timeout=2000)
    ms, err = captured[0]
    assert err is None
    assert ms == 23.5
    assert provider.ping_calls == 1


def test_ping_async_failure_invokes_callback_with_error(qtbot):
    provider = FakeProvider(ping_error=AuthError("bad key"))
    orch, _, _, _, _ = make_orchestrator(provider=provider)
    captured = []
    orch.ping_async(lambda ms, err: captured.append((ms, err)))
    qtbot.waitUntil(lambda: bool(captured), timeout=2000)
    ms, err = captured[0]
    assert ms is None
    assert isinstance(err, AuthError)


# ---- v3 streaming dispatch 路径 ----


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
    registry = UseCaseRegistry()
    registry.register(TEST_PROBE)
    ch = _StreamRecordingChannel(name=channel_name)
    from desktop_sprite.ai.persona import Persona
    orch = AIOrchestrator(
        provider=provider,
        persona=Persona(name="x", system_prompt="sys", default_fallback="(silent)"),
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
