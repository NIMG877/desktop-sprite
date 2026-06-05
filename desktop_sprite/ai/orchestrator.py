"""AIOrchestrator——中央调度器。

事件订阅 → 查注册表 → 节流 → QThreadPool worker → 调 provider →
跨线程 invokeMethod 回主线程 → fan-out 到 channel。带重试 / 熔断 /
fallback / 异常隔离。
"""
from __future__ import annotations

import logging
import time
import uuid
import weakref
from typing import Any, Callable, Iterable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot

from desktop_sprite.ai.channel import AIText, Channel
from desktop_sprite.ai.event_bus import EventBus
from desktop_sprite.ai.persona import Persona
from desktop_sprite.ai.provider import (
    AIProvider, NetworkError, RateLimitError, TimeoutError,
)
from desktop_sprite.ai.use_case import UseCase, UseCaseRegistry


logger = logging.getLogger(__name__)

# 默认重试 backoff（秒）——可在构造时通过 `retry_backoff_overrides` 覆盖。
_RETRY_BACKOFF_S: dict[type, float] = {
    RateLimitError: 2.0,
    TimeoutError: 4.0,
}

# 计入熔断计数的错误类型（不重试但累计错误）。
_CIRCUIT_ERRORS: tuple[type, ...] = (RateLimitError, TimeoutError, NetworkError)
_CIRCUIT_THRESHOLD = 3
_CIRCUIT_OPEN_SECONDS = 30.0

# 测试事件专用 topic
_TEST_TOPIC = "ai.test.request"


class _GenerationWorker(QRunnable):
    """QRunnable 替身——直接继承 QRunnable。"""

    def __init__(
        self,
        orch_ref,
        use_case_id: str,
        system: str,
        user: str,
        attempt: int,
        payload_for_retry=None,
    ) -> None:
        super().__init__()
        self._orch_ref = orch_ref
        self._use_case_id = use_case_id
        self._system = system
        self._user = user
        self._attempt = attempt
        self._payload_for_retry = payload_for_retry  # for retry: original payload

    def submit_to(self, pool: QThreadPool) -> None:
        """便捷提交——外部也可以直接 `pool.start(worker)`。"""
        pool.start(self)

    def run(self) -> None:
        orch = self._orch_ref()
        if orch is None:
            return
        try:
            text = orch._provider.generate(
                self._system, self._user, timeout=orch._request_timeout_s
            )
            payload = (self._use_case_id, text, None, self._attempt, self._payload_for_retry)
        except Exception as e:  # noqa: BLE001 — 任意异常都通过 invokeMethod 投回主线程
            payload = (self._use_case_id, None, e, self._attempt, self._payload_for_retry)
        orch._worker_result.emit(payload)


class AIOrchestrator(QObject):
    """AI 中央调度器。

    订阅 EventBus 上的 use_case topic；事件到达时检查熔断/节流，
    把"调 provider"丢到 QThreadPool worker；worker 在子线程执行
    provider.generate（同步阻塞），通过 Signal 投回主线程；在主
    线程做错误处理、重试、fallback、fan-out。
    """

    # worker 完成后通过此信号把 (use_case_id, text, err, attempt, payload) 投回主线程
    _worker_result = Signal(object)

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
        retry_backoff_overrides: dict[type, float] | None = None,
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

        # 重试 backoff：复制默认 + 应用覆盖
        self._retry_backoff_s: dict[type, float] = dict(_RETRY_BACKOFF_S)
        if retry_backoff_overrides:
            self._retry_backoff_s.update(retry_backoff_overrides)

        # 节流状态：use_case_id -> 上次提交时间戳
        self._last_fire_ts: dict[str, float] = {}
        # 熔断状态：错误计数 + 开启截止时间
        self._error_streak = 0
        self._circuit_open_until = 0.0
        # 反订阅句柄
        self._unsubscribers: list[Callable[[], None]] = []

        # worker 结果信号 → 主线程 slot
        self._worker_result.connect(self._on_provider_done, Qt.QueuedConnection)

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

        worker = _GenerationWorker(
            weakref.ref(self), uc.use_case_id, system, user, attempt=1,
            payload_for_retry=payload,
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

    @Slot(object)
    def _on_provider_done(self, payload) -> None:
        """Worker 在子线程通过 Signal 把结果投回主线程。"""
        use_case_id, text, err, attempt, orig_payload = payload
        uc = self._use_cases.get(use_case_id)
        if uc is None:
            return

        # 熔断计数先做（错误就是错误，重试不掩盖它）。
        if err is not None and isinstance(err, _CIRCUIT_ERRORS):
            self._error_streak += 1
            if self._error_streak >= _CIRCUIT_THRESHOLD:
                self._circuit_open_until = time.monotonic() + _CIRCUIT_OPEN_SECONDS
                self._error_streak = 0
                logger.warning("circuit opened for %ss", _CIRCUIT_OPEN_SECONDS)

        # 重试：RateLimit / Timeout 各重试 1 次
        if err is not None and attempt == 1 and type(err) in self._retry_backoff_s:
            backoff = self._retry_backoff_s[type(err)]
            system = self._persona.system_prompt
            if orig_payload and isinstance(orig_payload, dict):
                try:
                    user = uc.prompt_template.format(
                        persona_name=self._persona.name, **orig_payload
                    )
                except KeyError:
                    user = uc.prompt_template
            else:
                user = uc.prompt_template
            # 用 QTimer 异步 backoff（不阻塞主线程）
            QTimer.singleShot(
                int(backoff * 1000),
                lambda s=system, u=user, ucid=use_case_id: self._resubmit_after_backoff(ucid, s, u),
            )
            return

        # 错误处理（AuthError / BadRequestError / ProviderDisabled 不计熔断但仍 fallback）
        if err is not None:
            self._fallback_or_skip(uc, f"err={type(err).__name__}: {err}")
            return

        # 成功 → 重置熔断 + fan-out
        self._error_streak = 0
        msg = AIText(
            text=text, source="ai",
            use_case_id=use_case_id, timestamp=time.time(),
        )
        self._fan_out(uc.target_channels, msg)

    def _resubmit_after_backoff(self, use_case_id: str, system: str, user: str) -> None:
        worker = _GenerationWorker(
            weakref.ref(self), use_case_id, system, user, attempt=2,
        )
        self._pool.start(worker)

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
