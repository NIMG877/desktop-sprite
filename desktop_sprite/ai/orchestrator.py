"""AIOrchestrator——中央调度器。

事件订阅 → 查注册表 → 节流 → QThreadPool worker → 调 provider.generate_stream() →
Signal queued 跨线程回主线程 → fan-out 到 channel。带熔断 / fallback / 异常隔离。
"""
from __future__ import annotations

import logging
import time
import uuid
import weakref
from typing import Any, Callable, Iterable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot

from desktop_sprite.ai.channel import AIText, Channel
from desktop_sprite.ai.event_bus import EventBus
from desktop_sprite.ai.persona import Persona
from desktop_sprite.ai.provider import (
    AIProvider, NetworkError, RateLimitError, TimeoutError,
)
from desktop_sprite.ai.use_case import UseCase, UseCaseRegistry


logger = logging.getLogger(__name__)

# 计入熔断计数的错误类型（不重试但累计错误）。
_CIRCUIT_ERRORS: tuple[type, ...] = (RateLimitError, TimeoutError, NetworkError)
_CIRCUIT_THRESHOLD = 3
_CIRCUIT_OPEN_SECONDS = 30.0

# 测试事件专用 topic
_TEST_TOPIC = "ai.test.request"


class _StreamWorker(QRunnable):
    """流式 worker——在 QThreadPool 子线程调 `provider.generate_stream()`，
    每段 delta 通过 Signal 投回主线程。

    错误处理：
    - 流开始前异常（鉴权 / 超时 / provider 抛）→ emit(kind="error", exc)
    - 流中异常 → emit(kind="error", exc)；已 yield 的 delta 不重发
    - 流正常结束 → emit(kind="end", (full_text, "ai"))
    """

    def __init__(self, orch_ref, use_case_id: str, system: str, user: str) -> None:
        super().__init__()
        self._orch_ref = orch_ref
        self._use_case_id = use_case_id
        self._system = system
        self._user = user
        self._stream_id = str(uuid.uuid4())

    def run(self) -> None:
        orch = self._orch_ref()
        if orch is None:
            return
        # 先 emit start——channel 可以初始化"打字中"占位
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
            partial = "".join(accumulated)
            orch._stream_event.emit(
                self._stream_id, self._use_case_id, "error", exc,
            )
            # 仍然发 end 事件，让 channel 清理 in-progress 状态
            source = "ai" if accumulated else "fallback"
            orch._stream_event.emit(
                self._stream_id, self._use_case_id, "end", (partial, source),
            )
            return
        full_text = "".join(accumulated)
        orch._stream_event.emit(
            self._stream_id, self._use_case_id, "end", (full_text, "ai"),
        )


class _PingWorker(QRunnable):
    """无 token 消耗的连通性探针。调 `provider.ping()`，结果通过 callback
    抛回调用线程（通常是主线程的 panel）。"""

    def __init__(self, provider: AIProvider, callback: Callable[[float | None, Exception | None], None]) -> None:
        super().__init__()
        self._provider = provider
        self._callback = callback

    def run(self) -> None:
        try:
            latency_ms = self._provider.ping(timeout=5.0)
            self._callback(latency_ms, None)
        except Exception as e:  # noqa: BLE001 — 任何 ProviderError 都通过 callback 回传
            self._callback(None, e)


class AIOrchestrator(QObject):
    """AI 中央调度器。

    订阅 EventBus 上的 use_case topic；事件到达时检查熔断/节流，
    把"调 provider"丢到 QThreadPool worker；worker 在子线程执行
    provider.generate（同步阻塞），通过 Signal 投回主线程；在主
    线程做错误处理、重试、fallback、fan-out。
    """

    # 流式事件信号——(stream_id, use_case_id, kind, payload) 投回主线程
    #   kind="start"  → payload = None
    #   kind="delta"  → payload = str（一段 delta 文本）
    #   kind="end"    → payload = (full_text, source)
    #   kind="error"  → payload = Exception
    _stream_event = Signal(str, str, str, object)

    def __init__(
        self,
        *,
        provider: AIProvider,
        persona: Persona,
        use_cases: UseCaseRegistry,
        channels: Iterable[Channel],
        max_inflight: int = 1,
        request_timeout_s: float = 30.0,
        throttle_overrides: dict[str, int] | None = None,
        event_bus: EventBus | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._provider = provider
        self._persona = persona
        self._use_cases = use_cases
        self._channels = list(channels)
        self._max_inflight = max_inflight
        self._request_timeout_s = request_timeout_s
        self._throttle_overrides = dict(throttle_overrides or {})
        self._bus = event_bus or EventBus()
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(max_inflight)

        # 节流状态：use_case_id -> 上次提交时间戳
        self._last_fire_ts: dict[str, float] = {}
        # 熔断状态：错误计数 + 开启截止时间
        self._error_streak = 0
        self._circuit_open_until = 0.0
        # 流错误标记：记录本轮已 error 的 stream_id，避免 end-after-error 把
        # 熔断计数清零（end 不再代表"成功完成"）。
        self._stream_errored: set[str] = set()
        # 反订阅句柄
        self._unsubscribers: list[Callable[[], None]] = []

        # 流式事件信号 → 主线程 slot
        self._stream_event.connect(self._on_stream_event, Qt.QueuedConnection)

    # ---- 生命周期 ----

    def start(self) -> None:
        """订阅所有已注册 use_case 的 topic。重复调用会重复订阅——只调一次。"""
        if self._unsubscribers:
            return  # idempotent
        seen: set[str] = set()
        for uc in self._use_cases._by_id.values():
            topic = uc.event_topic
            if topic in seen:
                continue
            seen.add(topic)
            u = self._bus.subscribe(topic, self._make_topic_handler(topic))
            self._unsubscribers.append(u)

    def stop(self) -> None:
        for u in self._unsubscribers:
            u()
        self._unsubscribers.clear()
        self._pool.waitForDone(2000)

    def _make_topic_handler(self, topic: str) -> Callable[[Any], None]:
        def handler(payload) -> None:
            self._on_event(topic, payload)
        return handler

    # ---- 公共触发入口（v1 手动测试）----

    def trigger_test(self, user_hint: str = "") -> None:
        """v1 简化入口：发一个 `ai.test.request` 事件。"""
        payload = {"probe_id": str(uuid.uuid4()), "user_hint": user_hint}
        self._bus.publish(_TEST_TOPIC, payload)

    def ping_async(self, callback: Callable[[float | None, Exception | None], None]) -> None:
        """不消耗 token 的连通性探针。

        把 `provider.ping()` 丢到线程池执行，结果通过 callback 传回。
        callback 签名：`(latency_ms: float | None, error: Exception | None)`。
        成功时 error=None；失败时 latency_ms=None。
        """
        if self._provider is None:
            return
        worker = _PingWorker(self._provider, callback)
        self._pool.start(worker)

    # ---- 事件派发 ----

    def _on_event(self, topic: str, payload) -> None:
        for uc in self._use_cases.for_topic(topic):
            self._dispatch_use_case(uc, payload)

    def _dispatch_use_case(self, uc: UseCase, payload) -> None:
        now = time.monotonic()
        # 熔断
        if now < self._circuit_open_until:
            self._fallback_or_skip(uc, "circuit open")
            return
        # 节流
        throttle_ms = self._throttle_overrides.get(uc.use_case_id, uc.throttle_ms)
        last = self._last_fire_ts.get(uc.use_case_id, 0.0)
        if (now - last) * 1000 < throttle_ms:
            return
        self._last_fire_ts[uc.use_case_id] = now

        # 拼 prompt
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

    def _fallback_or_skip(self, uc: UseCase, reason: str) -> None:
        if uc.fallback_text is not None:
            msg = AIText(
                text=uc.fallback_text, source="fallback",
                use_case_id=uc.use_case_id, timestamp=time.time(),
            )
            self._fan_out(uc.target_channels, msg)
        logger.info("orchestrator: use_case %s skipped (%s)", uc.use_case_id, reason)

    @Slot(str, str, str, object)
    def _on_stream_event(self, stream_id: str, use_case_id: str, kind: str, payload) -> None:
        """流式事件统一在主线程处理。

        - start  → 通知所有 channel "流开始"
        - delta  → 通知所有 channel 增量文本
        - end    → 通知所有 channel 流结束 + reset 熔断
        - error  → 熔断计数（如适用） + 走 fallback
        """
        if kind == "start":
            self._stream_errored.discard(stream_id)
            for ch in self._channels:
                try:
                    ch.dispatch_stream_start(stream_id, use_case_id)
                except Exception:
                    logger.warning("channel %s.dispatch_stream_start raised; isolating", ch.name, exc_info=True)
            return

        if kind == "delta":
            for ch in self._channels:
                try:
                    ch.dispatch_stream_delta(stream_id, payload, use_case_id)
                except Exception:
                    logger.warning("channel %s.dispatch_stream_delta raised; isolating", ch.name, exc_info=True)
            return

        if kind == "end":
            full_text, source = payload
            # 成功 → 重置熔断（仅当本流未 error 过；end-after-error 是清理，
            # 不应清掉熔断计数）。
            if stream_id not in self._stream_errored:
                self._error_streak = 0
            self._stream_errored.discard(stream_id)
            for ch in self._channels:
                try:
                    ch.dispatch_stream_end(stream_id, full_text, source, use_case_id)
                except Exception:
                    logger.warning("channel %s.dispatch_stream_end raised; isolating", ch.name, exc_info=True)
            return

        if kind == "error":
            exc = payload
            uc = self._use_cases.get(use_case_id)
            if uc is None:
                return
            # 标记本流已 error，避免随后的 end 把熔断计数清零
            self._stream_errored.add(stream_id)
            # 熔断计数先做（错误就是错误）
            if isinstance(exc, _CIRCUIT_ERRORS):
                self._error_streak += 1
                if self._error_streak >= _CIRCUIT_THRESHOLD:
                    self._circuit_open_until = time.monotonic() + _CIRCUIT_OPEN_SECONDS
                    self._error_streak = 0
                    logger.warning("circuit opened for %ss", _CIRCUIT_OPEN_SECONDS)
            self._fallback_or_skip(uc, f"stream err={type(exc).__name__}: {exc}")
            return

    def _fan_out(self, channel_names: tuple[str, ...], msg: AIText) -> None:
        name_to_ch = {ch.name: ch for ch in self._channels}
        for n in channel_names:
            ch = name_to_ch.get(n)
            if ch is None:
                continue
            try:
                ch.dispatch(msg)
            except Exception:
                logger.warning("channel %s.dispatch raised; isolating", n, exc_info=True)
