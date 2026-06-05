import pytest
from desktop_sprite.ai.provider import (
    AuthError, RateLimitError, NetworkError, ProviderDisabled,
)
from desktop_sprite.ai.use_case import UseCase, UseCaseRegistry
from tests.ai_fakes import FakeProvider, RecordingChannel, make_orchestrator


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

def test_rate_limit_retries_once(qtbot):
    # 用 0.05s backoff 覆盖默认 2s，让测试在 2s 超时内完成
    orch, bus, channels, _, provider = make_orchestrator(
        provider=FakeProvider([RateLimitError("r"), "ok"]),
        retry_backoff_overrides={RateLimitError: 0.05},
    )
    orch.start()
    orch.trigger_test()
    qtbot.waitUntil(lambda: len(channels["pet_bubble"].dispatched) == 1, timeout=2000)
    assert len(provider.calls) == 2  # 第 1 次失败、重试 1 次成功


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
